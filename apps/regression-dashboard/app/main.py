from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .cases import build_suite, public_cases
from .config import settings
from .database import Result, Run, get_db, init_db
from .metrics import calculate_metrics
from .runner import start_run


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Agent Regression Lab", version="1.0.0", lifespan=lifespan)
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class RunCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    prompt_version: str = Field(default="current", max_length=120)
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
        "metrics": calculate_metrics(run.results),
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
        "default_judge_model": settings.default_judge_model,
        "scopes": ["full", "main", "boundary"],
        "public_read": True,
        "mutations_require_token": True,
    }


@app.get("/api/cases")
def cases() -> dict:
    return public_cases()


@app.get("/api/runs")
def list_runs(db: Session = Depends(get_db)) -> list[dict]:
    runs = db.scalars(select(Run).order_by(Run.created_at.desc()).limit(100)).all()
    return [serialize_run(run) for run in runs]


@app.post("/api/runs", dependencies=[Depends(require_admin)])
def create_run(payload: RunCreate, db: Session = Depends(get_db)) -> dict:
    if payload.judge_model not in settings.judge_models:
        raise HTTPException(400, "Недоступная модель судьи")
    suite = build_suite(payload.scope)
    run = Run(
        name=payload.name.strip(),
        prompt_version=payload.prompt_version.strip() or "current",
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
def launch_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Прогон не найден")
    if run.status not in {"draft", "failed", "cancelled"}:
        raise HTTPException(409, "Этот прогон уже запущен или завершён")
    run.cancel_requested = False
    run.status = "queued"
    db.commit()
    start_run(run.id)
    return {"status": "queued", "run_id": run.id}


@app.post("/api/runs/{run_id}/cancel", dependencies=[Depends(require_admin)])
def cancel_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Прогон не найден")
    run.cancel_requested = True
    db.commit()
    return {"status": "cancellation_requested"}


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


@app.patch("/api/results/{result_id}", dependencies=[Depends(require_admin)])
def review_result(result_id: int, payload: ReviewUpdate, db: Session = Depends(get_db)) -> dict:
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
