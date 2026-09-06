from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .cases import build_suite, public_cases
from .config import settings
from .database import Result, Run, get_db, init_db
from .export import generate_csv, generate_html_report
from .metrics import execution_summary, gate_explanation, run_metrics
from .lifecycle import ACTIVE as ACTIVE_RUN_STATUSES, DELETABLE as DELETABLE_RUN_STATUSES, recover_interrupted_runs, worker_guard
from .provenance import capture_provenance, public_provenance
from .runner import RUN_TASKS, case_from_row, shutdown_runs, start_run
from .judge_models import public_profiles


@asynccontextmanager
async def lifespan(_: FastAPI):
    with worker_guard():
        init_db()
        recover_interrupted_runs()
        try:
            yield
        finally:
            await shutdown_runs()


app = FastAPI(title="Agent Regression Lab", version="1.0.0", lifespan=lifespan)
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class RunCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    prompt_version: str = Field(default="", max_length=120)
    judge_model: str
    scope: str = Field(default="full", pattern="^(full|main|boundary)$")


class ReviewUpdate(BaseModel):
    manual_status: str | None = Field(default=None, pattern="^(PASS|PARTIAL|FAIL|CRITICAL)$")
    manual_comment: str | None = Field(default=None, max_length=4000)



def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not settings.admin_token:
        raise HTTPException(503, "ADMIN_TOKEN не настроен")
    if not x_admin_token or not secrets.compare_digest(x_admin_token, settings.admin_token):
        raise HTTPException(401, "Неверный токен запуска")


def serialize_result(row: Result, include_raw: bool = False) -> dict:
    result = {
        "id": row.id,
        "position": row.position,
        "case_id": row.case_id,
        "base_case_id": row.base_case_id,
        "attempt": row.attempt,
        "company_code": row.company_code,
        "dialogue_key": row.dialogue_key,
        "category": row.category,
        "question": row.question,
        "expected": row.expected,
        "evidence": row.evidence,
        "forbidden": row.forbidden,
        "critical_if": row.critical_if,
        "answerability": row.answerability,
        "is_main": row.is_main,
        "is_boundary": row.is_boundary,
        "is_web": row.is_web,
        "state": row.state,
        "answer": row.answer,
        "response_id": row.response_id,
        "latency_ms": row.latency_ms,
        "usage": row.usage,
        "citations": row.citations,
        "tool_calls": row.tool_calls,
        "technical_error": row.technical_error,
        "technical_error_kind": row.technical_error_kind,
        "auto_status": row.auto_status,
        "effective_status": row.effective_status,
        "auto_evaluation": row.auto_evaluation,
        "manual_status": row.manual_status,
        "manual_comment": row.manual_comment,
    }
    if include_raw:
        result["raw_response"] = row.raw_response
    return result


def serialize_run(run: Run, include_results: bool = False, include_raw: bool = False) -> dict:
    metrics = run_metrics(run)
    payload = {
        "id": run.id,
        "name": run.name,
        "prompt_version": run.prompt_version,
        "judge_model": run.judge_model,
        "scope": run.scope,
        "status": run.status,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "error": run.error,
        "cancel_requested": run.cancel_requested,
        "metrics": metrics,
        "execution": execution_summary(run.results),
        "gate": gate_explanation(run, metrics),
        "provenance": public_provenance(run),
        "can_delete": run.status in DELETABLE_RUN_STATUSES and run.id not in RUN_TASKS,
        "can_stop": run.status in ACTIVE_RUN_STATUSES and not run.cancel_requested,
    }
    if include_results:
        payload["results"] = [serialize_result(row, include_raw=include_raw) for row in run.results]
    return payload


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "agent_configured": bool(settings.yandex_api_key),
        "judge_configured": bool(settings.judge_api_key and settings.judge_base_url),
        "database": "postgresql" if settings.database_url.startswith("postgresql") else "sqlite",
    }


@app.get("/api/config")
def config() -> dict:
    return {
        "judge_models": settings.judge_models,
        "judge_profiles": public_profiles(settings.judge_models),
        "default_judge_model": settings.default_judge_model,
        "scopes": ["full", "main", "boundary"],
        "public_read": True,
        "mutations_require_token": True,
    }



@app.get("/api/cases")
def cases() -> dict:
    return public_cases()


@app.get("/api/compare")
def compare(baseline: int, candidate: int, db: Session = Depends(get_db)) -> dict:
    from .comparison import compare_runs
    if baseline == candidate:
        raise HTTPException(400, "Выберите два разных прогона")
    a, b = db.get(Run, baseline), db.get(Run, candidate)
    if not a or not b:
        raise HTTPException(404, "Один из прогонов не найден")
    try:
        return compare_runs(a, b)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/runs")
def list_runs(db: Session = Depends(get_db), q: str = "", status: str = "",
              sort: str = Query("desc", pattern="^(asc|desc)$"),
              offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)) -> list[dict]:
    query = select(Run)
    if q:
        from sqlalchemy import String, cast, or_
        query = query.where(or_(Run.name.icontains(q, autoescape=True), cast(Run.id, String) == q))
    if status == "cancelling":
        query = query.where(Run.status.in_(ACTIVE_RUN_STATUSES), Run.cancel_requested.is_(True))
    elif status:
        query = query.where(Run.status == status)
    order = Run.created_at.asc() if sort == "asc" else Run.created_at.desc()
    runs = db.scalars(query.order_by(order, Run.id.asc() if sort == "asc" else Run.id.desc()).offset(offset).limit(limit)).all()
    return [serialize_run(run) for run in runs]


@app.post("/api/runs", dependencies=[Depends(require_admin)])
async def create_run(payload: RunCreate, db: Session = Depends(get_db)) -> dict:
    if payload.judge_model not in settings.judge_models:
        raise HTTPException(400, "Недоступная модель судьи")
    suite = build_suite(payload.scope)
    if not payload.name.strip():
        raise HTTPException(422, "Название не должно быть пустым")
    run = Run(
        name=payload.name.strip(),
        prompt_version=payload.prompt_version.strip(),
        provenance=capture_provenance(suite, payload.prompt_version.strip(), payload.judge_model),
        judge_model=payload.judge_model,
        scope=payload.scope,
    )
    db.add(run)
    db.flush()
    for position, case in enumerate(suite, 1):
        db.add(
            Result(
                run_id=run.id,
                position=position,
                case_id=case.id,
                base_case_id=case.base_case_id,
                attempt=case.attempt,
                company_code=case.company_code,
                dialogue_key=case.dialogue_key,
                category=case.category,
                question=case.question,
                expected=case.expected,
                evidence=case.evidence,
                forbidden=case.forbidden,
                critical_if=case.critical_if,
                answerability=case.answerability,
                is_main=case.is_main,
                is_boundary=case.is_boundary,
                is_web=case.is_web,
            )
        )
    db.commit()
    db.refresh(run)
    return serialize_run(run, include_results=True)


@app.post("/api/runs/{run_id}/start", dependencies=[Depends(require_admin)])
async def launch_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Прогон не найден")
    if run.status != "draft":
        raise HTTPException(409, "Запускается только draft. Для повторной проверки создайте новый прогон; история сохраняется.")
    if run_id in RUN_TASKS:
        raise HTTPException(409, "Worker ещё выполняет прогон")
    changed = db.execute(update(Run).where(Run.id == run_id, Run.status == "draft")
                         .values(status="queued", cancel_requested=False,
                                 provenance=capture_provenance([case_from_row(row) for row in run.results], run.prompt_version, run.judge_model)))
    if not changed.rowcount:
        db.rollback()
        raise HTTPException(409, "Запускается только draft. Для повторной проверки создайте новый прогон; история сохраняется.")
    db.commit()
    try:
        start_run(run.id)
    except Exception:
        db.execute(update(Run).where(Run.id == run_id, Run.status == "queued")
                   .values(status="failed", error="Не удалось создать фоновую задачу",
                           finished_at=datetime.now(timezone.utc)))
        db.commit()
        raise HTTPException(503, "Не удалось создать фоновую задачу")
    return {"status": "queued", "run_id": run.id}


@app.post("/api/runs/{run_id}/cancel", dependencies=[Depends(require_admin)])
async def cancel_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Прогон не найден")
    if run.status == "cancelled":
        return {"status": "cancelled", "run_id": run.id, "cancel_requested": True}
    if run.status not in ACTIVE_RUN_STATUSES:
        raise HTTPException(409, "Остановить можно только queued/running прогон")
    if run.cancel_requested:
        return {"status": "cancellation_requested", "run_id": run.id, "cancel_requested": True}
    changed = db.execute(
        update(Run)
        .where(
            Run.id == run.id,
            Run.status.in_(ACTIVE_RUN_STATUSES),
            Run.cancel_requested.is_(False),
        )
        .values(cancel_requested=True)
    )
    db.commit()
    if not changed.rowcount:
        db.expire_all()
        current = db.get(Run, run_id)
        if not current:
            raise HTTPException(404, "Прогон не найден")
        if current.status == "cancelled" or (
            current.status in ACTIVE_RUN_STATUSES and current.cancel_requested
        ):
            return {
                "status": "cancelled" if current.status == "cancelled" else "cancellation_requested",
                "run_id": current.id,
                "cancel_requested": True,
            }
        raise HTTPException(409, "Остановить можно только queued/running прогон")
    return {"status": "cancellation_requested", "run_id": run.id, "cancel_requested": True}


@app.delete("/api/runs/{run_id}", dependencies=[Depends(require_admin)])
async def delete_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Прогон не найден")
    if run.status in ACTIVE_RUN_STATUSES or run_id in RUN_TASKS:
        raise HTTPException(409, "Сначала остановите прогон и дождитесь статуса cancelled")
    if run.status not in DELETABLE_RUN_STATUSES:
        raise HTTPException(409, f"Прогон в статусе {run.status} удалить нельзя")
    deleted = {"status": "deleted", "run_id": run.id, "name": run.name}
    # A conditional write takes the database row/write lock before child deletion.
    # A concurrent launch can only win before this statement, never between deletes.
    changed = db.execute(update(Run).where(Run.id == run_id, Run.status.in_(DELETABLE_RUN_STATUSES))
                         .values(status="deleting"))
    if not changed.rowcount:
        db.rollback()
        raise HTTPException(409, "Состояние прогона изменилось; обновите список")
    db.execute(delete(Result).where(Result.run_id == run_id))
    db.execute(delete(Run).where(Run.id == run_id))
    db.commit()
    return deleted


@app.get("/api/runs/{run_id}")
def get_run(
    run_id: int,
    raw: bool = False,
    x_admin_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Прогон не найден")
    if raw:
        require_admin(x_admin_token)
    return serialize_run(run, include_results=True, include_raw=raw)


@app.get("/api/runs/{run_id}/export/csv")
def export_csv(run_id: int, db: Session = Depends(get_db)) -> Response:
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Прогон не найден")
    csv_content = generate_csv(run)
    # Use ASCII-safe filename with RFC 5987 encoding for Unicode
    safe_name = f"regression-{run.id}"
    from urllib.parse import quote
    encoded_name = quote(f"regression-{run.id}-{run.name}.csv".encode("utf-8"))
    return PlainTextResponse(
        csv_content,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}.csv"; filename*=UTF-8\'\'{encoded_name}'
        },
        media_type="text/csv",
    )


@app.get("/api/runs/{run_id}/export/pdf")
def export_pdf(run_id: int, db: Session = Depends(get_db)) -> Response:
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Прогон не найден")
    html_content = generate_html_report(run)
    # Use ASCII-safe filename with RFC 5987 encoding for Unicode
    safe_name = f"regression-{run.id}"
    from urllib.parse import quote
    encoded_name = quote(f"regression-{run.id}-{run.name}.html".encode("utf-8"))
    return Response(
        html_content,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}.html"; filename*=UTF-8\'\'{encoded_name}'
        },
        media_type="text/html",
    )


@app.patch("/api/results/{result_id}", dependencies=[Depends(require_admin)])
async def review_result(result_id: int, payload: ReviewUpdate, db: Session = Depends(get_db)) -> dict:
    row = db.get(Result, result_id)
    if not row:
        raise HTTPException(404, "Результат не найден")
    row.manual_status = payload.manual_status
    row.manual_comment = payload.manual_comment
    db.commit()
    db.refresh(row)
    return serialize_result(row)


@app.get("/{path:path}")
def spa_fallback(path: str) -> FileResponse:
    if path.startswith("api/"):
        raise HTTPException(404)
    return FileResponse(STATIC_DIR / "index.html")
