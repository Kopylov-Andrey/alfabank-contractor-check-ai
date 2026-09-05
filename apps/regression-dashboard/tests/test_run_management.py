from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app import runner
from app.database import Base, Result, Run, get_db


ADMIN_HEADERS = {"X-Admin-Token": "test-admin-token"}


@pytest.fixture
def api_client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        with testing_session() as session:
            yield session

    monkeypatch.setattr(
        main_module,
        "settings",
        replace(main_module.settings, admin_token=ADMIN_HEADERS["X-Admin-Token"]),
    )
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    main_module.app.dependency_overrides[get_db] = override_get_db
    with TestClient(main_module.app) as client:
        yield client, testing_session
    main_module.app.dependency_overrides.clear()
    engine.dispose()


def _result(case_id: str, position: int = 1) -> Result:
    return Result(
        position=position,
        case_id=case_id,
        base_case_id=case_id,
        attempt=1,
        company_code="A",
        dialogue_key=f"dialogue-{case_id}",
        category="test",
        question="question",
        expected="expected",
        evidence="evidence",
        forbidden="forbidden",
        critical_if="critical",
        answerability="yes",
        is_main=True,
        is_boundary=False,
        is_web=False,
    )


def _seed_run(testing_session, status: str, name: str, result_count: int = 1) -> tuple[int, list[int]]:
    with testing_session() as db:
        run = Run(
            name=name,
            prompt_version="test",
            judge_model="test-model",
            scope="main",
            status=status,
        )
        run.results = [_result(f"T{index:02d}", index) for index in range(1, result_count + 1)]
        db.add(run)
        db.commit()
        return run.id, [result.id for result in run.results]


@pytest.mark.parametrize("status", ["queued", "running"])
def test_cancel_active_run_is_idempotent(api_client, status: str) -> None:
    client, testing_session = api_client
    run_id, _ = _seed_run(testing_session, status, f"active-{status}")

    first = client.post(f"/api/runs/{run_id}/cancel", headers=ADMIN_HEADERS)
    second = client.post(f"/api/runs/{run_id}/cancel", headers=ADMIN_HEADERS)

    assert first.status_code == 200
    assert first.json()["status"] == "cancellation_requested"
    assert second.status_code == 200
    assert second.json()["status"] == "cancellation_requested"
    with testing_session() as db:
        run = db.get(Run, run_id)
        assert run is not None
        assert run.status == status
        assert run.cancel_requested is True


def test_run_mutations_require_admin_token(api_client) -> None:
    client, testing_session = api_client
    queued_id, _ = _seed_run(testing_session, "queued", "protected-cancel")
    completed_id, _ = _seed_run(testing_session, "completed", "protected-delete")

    cancel_response = client.post(f"/api/runs/{queued_id}/cancel")
    delete_response = client.delete(f"/api/runs/{completed_id}")

    assert cancel_response.status_code == 401
    assert delete_response.status_code == 401
    with testing_session() as db:
        assert db.get(Run, queued_id).cancel_requested is False
        assert db.get(Run, completed_id) is not None


@pytest.mark.parametrize("status", ["queued", "running"])
def test_delete_active_run_is_rejected(api_client, status: str) -> None:
    client, testing_session = api_client
    run_id, result_ids = _seed_run(testing_session, status, f"active-{status}")

    response = client.delete(f"/api/runs/{run_id}", headers=ADMIN_HEADERS)

    assert response.status_code == 409
    assert response.json()["detail"] == "Сначала остановите прогон и дождитесь статуса cancelled"
    with testing_session() as db:
        assert db.get(Run, run_id) is not None
        assert all(db.get(Result, result_id) is not None for result_id in result_ids)


def test_delete_completed_run_cascades_to_results(api_client) -> None:
    client, testing_session = api_client
    run_id, result_ids = _seed_run(testing_session, "completed", "completed", result_count=2)

    response = client.delete(f"/api/runs/{run_id}", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "run_id": run_id, "name": "completed"}
    with testing_session() as db:
        assert db.get(Run, run_id) is None
        assert all(db.get(Result, result_id) is None for result_id in result_ids)


def test_deleted_run_is_not_available_from_api(api_client) -> None:
    client, testing_session = api_client
    run_id, _ = _seed_run(testing_session, "completed", "gone")

    assert client.delete(f"/api/runs/{run_id}", headers=ADMIN_HEADERS).status_code == 200
    response = client.get(f"/api/runs/{run_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Прогон не найден"


def test_delete_preserves_other_runs_and_results(api_client) -> None:
    client, testing_session = api_client
    deleted_run_id, _ = _seed_run(testing_session, "completed", "delete-me", result_count=2)
    kept_run_id, kept_result_ids = _seed_run(
        testing_session, "cancelled", "keep-me", result_count=2
    )

    response = client.delete(f"/api/runs/{deleted_run_id}", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    with testing_session() as db:
        assert db.get(Run, deleted_run_id) is None
        assert db.get(Run, kept_run_id) is not None
        remaining_ids = set(
            db.scalars(select(Result.id).where(Result.run_id == kept_run_id)).all()
        )
        assert remaining_ids == set(kept_result_ids)


def test_cancelled_run_finishes_without_starting_external_calls(api_client, monkeypatch) -> None:
    _, testing_session = api_client
    run_id, result_ids = _seed_run(testing_session, "queued", "cancel-before-start")
    with testing_session() as db:
        run = db.get(Run, run_id)
        run.cancel_requested = True
        db.commit()

    class FakeClient:
        calls = 0

        async def ask(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("Внешний API не должен вызываться")

        async def close(self) -> None:
            return None

    agent = FakeClient()
    judge = FakeClient()
    monkeypatch.setattr(runner, "SessionLocal", testing_session)
    monkeypatch.setattr(runner, "YandexAgentClient", lambda: agent)
    monkeypatch.setattr(runner, "JudgeClient", lambda: judge)

    asyncio.run(runner.execute_run(run_id))

    assert agent.calls == 0
    assert judge.calls == 0
    with testing_session() as db:
        run = db.get(Run, run_id)
        assert run is not None
        assert run.status == "cancelled"
        assert run.finished_at is not None
        assert all(db.get(Result, result_id).state == "pending" for result_id in result_ids)
