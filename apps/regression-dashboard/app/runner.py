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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_cancelled(run_id: int) -> bool:
    with SessionLocal() as db:
        run = db.get(Run, run_id)
        return run is None or bool(run.cancel_requested)


async def execute_run(run_id: int) -> None:
    agent = YandexAgentClient()
    judge = JudgeClient()
    try:
        with SessionLocal() as db:
            run = db.get(Run, run_id)
            if not run:
                return
            if run.cancel_requested:
                run.status = "cancelled"
                run.finished_at = _now()
                db.commit()
                return
            run.status = "running"
            run.started_at = _now()
            db.commit()
            model = run.judge_model
            ordered = db.scalars(
                select(Result).where(Result.run_id == run_id).order_by(Result.position)
            ).all()
            groups: dict[str, list[int]] = {}
            for row in ordered:
                groups.setdefault(row.dialogue_key, []).append(row.id)

        semaphore = asyncio.Semaphore(settings.max_concurrency)
        await asyncio.gather(
            *(process_dialogue(run_id, ids, model, semaphore, agent, judge) for ids in groups.values())
        )

        finished_at = _now()
        with SessionLocal() as db:
            completed = db.execute(
                update(Run)
                .where(
                    Run.id == run_id,
                    Run.status == "running",
                    Run.cancel_requested.is_(False),
                )
                .values(status="completed", finished_at=finished_at)
            )
            if not completed.rowcount:
                db.execute(
                    update(Run)
                    .where(Run.id == run_id, Run.cancel_requested.is_(True))
                    .values(status="cancelled", finished_at=finished_at)
                )
            db.commit()
    except Exception as exc:
        finished_at = _now()
        with SessionLocal() as db:
            failed = db.execute(
                update(Run)
                .where(Run.id == run_id, Run.cancel_requested.is_(False))
                .values(status="failed", error=str(exc)[:4000], finished_at=finished_at)
            )
            if not failed.rowcount:
                db.execute(
                    update(Run)
                    .where(Run.id == run_id, Run.cancel_requested.is_(True))
                    .values(status="cancelled", finished_at=finished_at)
                )
            db.commit()
    finally:
        await agent.close()
        await judge.close()
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
                row.state = "running"
                db.commit()
                setup = (
                    f"Выбери контрагента {company_name(row.company_code)}, "
                    f"ИНН {next_inn(row)}. Подтверди выбранную компанию."
                )
            try:
                if not previous_id:
                    setup_response = await agent.ask(setup)
                    previous_id = setup_response.response_id
                    if _is_cancelled(run_id):
                        return
                with SessionLocal() as db:
                    row = db.get(Result, result_id)
                    question = row.question
                response = await agent.ask(question, previous_id)
                previous_id = response.response_id
                with SessionLocal() as db:
                    row = db.get(Result, result_id)
                    row.answer = response.text
                    row.response_id = response.response_id
                    row.latency_ms = response.latency_ms
                    row.usage = response.usage
                    row.citations = response.citations
                    row.tool_calls = response.tool_calls
                    row.raw_response = response.raw
                    db.commit()
                    case = case_from_row(row)
                try:
                    algorithmic_evaluation = validate_answer(case, response.text)
                except Exception as exc:
                    algorithmic_evaluation = {
                        "status": "FAIL",
                        "reason": f"Техническая ошибка алгоритмического валидатора: {exc}",
                        "checks": [],
                        "required_facts_total": 0,
                        "required_facts_matched": 0,
                        "forbidden_matches": [],
                        "critical_flags": [],
                        "critical_checks_inconclusive": False,
                        "inconclusive_critical_checks": [],
                        "requires_manual_review": True,
                    }
                evaluation_raw = await judge.evaluate(
                    model=model,
                    system=JUDGE_SYSTEM,
                    user=judge_payload(
                        case, response.text, citations=response.citations, tool_calls=response.tool_calls
                    ),
                )
                evaluation = normalize_evaluation(evaluation_raw)
                evaluation, final_status = combine_evaluations(evaluation, algorithmic_evaluation)
                with SessionLocal() as db:
                    row = db.get(Result, result_id)
                    row.auto_evaluation = evaluation
                    row.auto_status = final_status
                    row.evaluated_at = _now()
                    row.state = "completed"
                    db.commit()
            except Exception as exc:
                previous_id = None
                with SessionLocal() as db:
                    row = db.get(Result, result_id)
                    row.state = "error"
                    row.technical_error = str(exc)[:4000]
                    row.auto_status = None
                    row.auto_evaluation = {
                        "reason": "Техническая ошибка при вызове агента или LLM-судьи",
                        "critical_flags": [],
                    }
                    if algorithmic_evaluation is not None:
                        row.auto_evaluation["algorithmic"] = algorithmic_evaluation
                        if algorithmic_evaluation.get("status") == "CRITICAL":
                            row.auto_status = "CRITICAL"
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
