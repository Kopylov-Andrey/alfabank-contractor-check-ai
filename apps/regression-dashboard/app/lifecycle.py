"""Exclusive ownership for the documented single backend worker architecture."""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text, update

from .database import Result, Run, SessionLocal, engine

ACTIVE = {"queued", "running"}
DELETABLE = {"draft", "completed", "failed", "cancelled"}


@contextmanager
def worker_guard(db_engine=None):
    """Refuse a second worker BEFORE migrations/recovery; OS releases locks on crash.

    SQLite must reside on a local disk. PostgreSQL uses a database-wide session
    advisory lock on a dedicated connection (no transaction pooler).
    """
    db_engine = db_engine or engine
    if db_engine.dialect.name == "postgresql":
        with db_engine.connect() as connection:
            if not connection.scalar(text("SELECT pg_try_advisory_lock(719438201)")):
                raise RuntimeError("Regression dashboard уже обслуживает другой worker; используйте --workers 1")
            try:
                yield
            finally:
                connection.execute(text("SELECT pg_advisory_unlock(719438201)"))
        return
    if db_engine.dialect.name != "sqlite":
        raise RuntimeError("Worker guard поддерживает только SQLite и PostgreSQL")
    database = db_engine.url.database
    if not database or database == ":memory:":
        yield  # Each in-memory database is isolated; used by tests only.
        return
    lock_path = Path(database).resolve().with_suffix(Path(database).suffix + ".worker.lock")
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Regression dashboard уже обслуживает другой worker; используйте --workers 1") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def recover_interrupted_runs(session_factory=None):
    """Only call after acquiring worker_guard. Never resume external requests."""
    with (session_factory or SessionLocal)() as db:
        runs = db.scalars(select(Run).where(Run.status.in_(ACTIVE))).all()
        for run in runs:
            run.status = "cancelled" if run.cancel_requested else "failed"
            run.finished_at = datetime.now(timezone.utc)
            run.error = "Предыдущий worker завершился до окончания прогона. Автоматического возобновления нет."
            db.execute(update(Result).where(Result.run_id == run.id, Result.state == "running")
                       .values(state="interrupted"))
        db.commit()
        return len(runs)
