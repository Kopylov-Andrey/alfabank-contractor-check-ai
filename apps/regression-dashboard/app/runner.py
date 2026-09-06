from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select, update

from .algorithmic_validation import combine_evaluations, validate_answer
from .clients import JudgeClient, YandexAgentClient
from .config import settings
from .database import Result, Run, SessionLocal
from .evaluation import JUDGE_SYSTEM, judge_payload, normalize_evaluation


RUN_TASKS: dict[int, asyncio.Task] = {}


class RunTechnicalError(RuntimeError):
    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_cancelled(run_id: int) -> bool:
    with SessionLocal() as db:
        run = db.get(Run, run_id)
        return run is None or run.status not in {"queued", "running"} or bool(run.cancel_requested)


async def execute_run(run_id: int) -> None:
    agent = judge = None
    children: list[asyncio.Task] = []
    claimed = False
    error = None
    interrupted = False
    try:
        with SessionLocal() as db:
            changed = db.execute(update(Run).where(Run.id == run_id, Run.status == "queued")
                                 .values(status="running", started_at=_now()))
            db.commit()
            if not changed.rowcount:
                return
            claimed = True
            db.expire_all()
            run = db.get(Run, run_id)
            if run.cancel_requested:
                return
            model = run.judge_model
            ordered = db.scalars(
                select(Result).where(Result.run_id == run_id).order_by(Result.position)
            ).all()
            groups: dict[str, list[int]] = {}
            for row in ordered:
                groups.setdefault(row.dialogue_key, []).append(row.id)

        agent = YandexAgentClient()
        judge = JudgeClient()
        semaphore = asyncio.Semaphore(settings.max_concurrency)
        children = [asyncio.create_task(process_dialogue(run_id, ids, model, semaphore, agent, judge))
                    for ids in groups.values()]
        # A failed dialogue must not leave siblings writing after terminal status.
        outcomes = await asyncio.gather(*children, return_exceptions=True)
        failures = [value for value in outcomes if isinstance(value, BaseException)]
        if failures:
            error = str(failures[0])[:4000] or "Работа диалога прервана"
    except asyncio.CancelledError:
        interrupted = True
        error = "Worker остановлен до окончания прогона. Автоматического возобновления нет."
    except Exception as exc:
        error = str(exc)[:4000]
    finally:
        for child in children:
            if not child.done():
                child.cancel()
        await asyncio.gather(*children, return_exceptions=True)
        for client in (agent, judge):
            if client:
                try:
                    await client.close()
                except Exception as exc:
                    error = error or str(exc)[:4000]
        if claimed:
            with SessionLocal() as db:
                run = db.get(Run, run_id)
                if run and run.status == "running":
                    run.status = "cancelled" if run.cancel_requested else "failed" if error else "completed"
                    run.finished_at = _now()
                    run.error = error
                    db.execute(update(Result).where(Result.run_id == run_id, Result.state == "running")
                               .values(state="interrupted" if interrupted or error else "cancelled"))
                    db.commit()
        if RUN_TASKS.get(run_id) is asyncio.current_task():
            RUN_TASKS.pop(run_id, None)


async def process_dialogue(
    run_id: int,
    result_ids: list[int],
    model: str,
    semaphore: asyncio.Semaphore,
    agent: YandexAgentClient,
    judge: JudgeClient,
) -> None:
    async with semaphore:
        previous_id: str | None = None
        for result_id in result_ids:
            algorithmic_evaluation: dict | None = None
            if _is_cancelled(run_id):
                return
            with SessionLocal() as db:
                row = db.get(Result, result_id)
                if row is None:
                    return
                row.state = "running"
                db.commit()
                setup = (
                    f"Выбери контрагента {company_name(row.company_code)}, "
                    f"ИНН {next_inn(row)}. Подтверди выбранную компанию."
                )
            try:
                if not previous_id:
                    if _is_cancelled(run_id):
                        return
                    try:
                        setup_response = await agent.ask(setup)
                    except Exception as exc:
                        raise RunTechnicalError(f"Техническая ошибка агента: {exc}", kind="agent") from exc
                    previous_id = setup_response.response_id
                    if _is_cancelled(run_id):
                        return
                with SessionLocal() as db:
                    row = db.get(Result, result_id)
                    if row is None:
                        return
                    question = row.question
                if _is_cancelled(run_id):
                    return
                try:
                    response = await agent.ask(question, previous_id)
                except Exception as exc:
                    raise RunTechnicalError(f"Техническая ошибка агента: {exc}", kind="agent") from exc
                previous_id = response.response_id
                with SessionLocal() as db:
                    row = db.get(Result, result_id)
                    if row is None:
                        return
                    row.answer = response.text
                    row.response_id = response.response_id
                    row.latency_ms = response.latency_ms
                    row.usage = response.usage
                    row.citations = response.citations
                    row.tool_calls = response.tool_calls
                    row.raw_response = response.raw
                    db.commit()
                    case = case_from_row(row)
                if _is_cancelled(run_id):
                    return
                try:
                    algorithmic_evaluation = validate_answer(case, response.text)
                except Exception as exc:
                    raise RunTechnicalError(
                        f"Техническая ошибка алгоритмического валидатора: {exc}", kind="integration"
                    ) from exc
                if _is_cancelled(run_id):
                    return
                evaluation_raw = await judge.evaluate(
                    model=model,
                    system=JUDGE_SYSTEM,
                    user=judge_payload(
                        case, response.text, citations=response.citations, tool_calls=response.tool_calls
                    ),
                    should_cancel=lambda: _is_cancelled(run_id),
                )
                evaluation = normalize_evaluation(evaluation_raw)
                evaluation, final_status = combine_evaluations(evaluation, algorithmic_evaluation)
                with SessionLocal() as db:
                    row = db.get(Result, result_id)
                    if row is None:
                        return
                    row.auto_evaluation = evaluation
                    row.auto_status = final_status
                    row.evaluated_at = _now()
                    row.state = "completed"
                    db.commit()
            except Exception as exc:
                if getattr(exc, "kind", None) == "cancelled":
                    return
                previous_id = None
                with SessionLocal() as db:
                    row = db.get(Result, result_id)
                    if row is None:
                        return
                    row.state = "error"
                    row.technical_error = str(exc)[:4000]
                    row.technical_error_kind = getattr(exc, "kind", "integration")

                    if algorithmic_evaluation is not None and algorithmic_evaluation.get("status") == "CRITICAL":
                        row.auto_status = "CRITICAL"
                    else:
                        row.auto_status = None

                    row.auto_evaluation = {
                        "reason": "Техническая ошибка при вызове агента или LLM-судьи",
                        "critical_flags": [],
                        "technical_error": True,
                        "technical_error_kind": row.technical_error_kind,
                        "technical_diagnostics": getattr(exc, "diagnostics", {}),
                    }
                    if algorithmic_evaluation is not None:
                        row.auto_evaluation["algorithmic"] = algorithmic_evaluation
                    db.commit()


def next_inn(row: Result) -> str:
    from .cases import COMPANIES
    return COMPANIES[row.company_code]["inn"]


def company_name(company_code: str) -> str:
    from .cases import COMPANIES
    return COMPANIES[company_code]["name"]


def case_from_row(row: Result):
    from .cases import TestCase, COMPANIES
    company = COMPANIES[row.company_code]
    return TestCase(
        id=row.case_id, base_case_id=row.base_case_id, attempt=row.attempt,
        company_code=row.company_code, company_name=company["name"], inn=company["inn"],
        category=row.category, question=row.question, answerability=row.answerability,
        expected=row.expected, evidence=row.evidence, forbidden=row.forbidden,
        critical_if=row.critical_if, is_main=row.is_main, is_boundary=row.is_boundary,
        is_web=row.is_web, dialogue_key=row.dialogue_key,
    )


def start_run(run_id: int) -> None:
    if run_id in RUN_TASKS:
        return
    RUN_TASKS[run_id] = asyncio.create_task(execute_run(run_id))


async def shutdown_runs() -> None:
    tasks = list(RUN_TASKS.values())
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
