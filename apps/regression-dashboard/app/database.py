from __future__ import annotations

from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    prompt_version: Mapped[str] = mapped_column(String(120), default="")
    provenance: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    judge_model: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    scope: Mapped[str] = mapped_column(String(32), default="full")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    results: Mapped[list["Result"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="Result.position"
    )


class Result(Base):
    __tablename__ = "results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    case_id: Mapped[str] = mapped_column(String(32), index=True)
    base_case_id: Mapped[str] = mapped_column(String(16), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    company_code: Mapped[str] = mapped_column(String(4))
    dialogue_key: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(120))
    question: Mapped[str] = mapped_column(Text)
    expected: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    forbidden: Mapped[str] = mapped_column(Text)
    critical_if: Mapped[str] = mapped_column(Text)
    answerability: Mapped[str] = mapped_column(String(16))
    is_main: Mapped[bool] = mapped_column(Boolean, default=True)
    is_boundary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_web: Mapped[bool] = mapped_column(Boolean, default=False)
    state: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    citations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    technical_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    technical_error_kind: Mapped[str | None] = mapped_column(String(48), nullable=True)
    auto_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    auto_evaluation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    manual_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    manual_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run: Mapped[Run] = relationship(back_populates="results")

    @property
    def effective_status(self) -> str | None:
        if self.state == "error" or self.technical_error:
            return None
        return self.manual_status or self.auto_status


engine_kwargs = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
    # Additive migration, under the exclusive worker guard. Never backfill versions.
    if "provenance" not in {column["name"] for column in inspect(engine).get_columns("runs")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE runs ADD COLUMN provenance JSON"))
    if "technical_error_kind" not in {column["name"] for column in inspect(engine).get_columns("results")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE results ADD COLUMN technical_error_kind VARCHAR(48)"))


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
