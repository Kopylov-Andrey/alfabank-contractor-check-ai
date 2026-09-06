import asyncio
from dataclasses import replace

import pytest
from sqlalchemy import create_engine, inspect, select

from app import database, lifecycle, main, runner
from app.clients import AgentResponse
from app.database import Result, Run
from test_run_management import ADMIN_HEADERS, _seed_run, api_client


@pytest.mark.parametrize("stage", ["setup", "answer", "judge"])
def test_stop_waits_for_inflight_request_and_blocks_delete(api_client, monkeypatch, stage):
    client, factory = api_client
    run_id, ids = _seed_run(factory, "queued", "paused", result_count=2)
    monkeypatch.setattr(runner, "SessionLocal", factory)
    monkeypatch.setattr(runner, "settings", replace(runner.settings, max_concurrency=1))
    calls = []
    async def scenario():
        entered, release, closing = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def pause(label):
            calls.append(label)
            if label == stage:
                entered.set()
                await release.wait()
        class Agent:
            async def ask(self, question, previous=None):
                await pause("setup" if previous is None else "answer")
                return AgentResponse("Ответ сохранён", "r", 5, {}, [], [], {})
            async def close(self):
                closing.set()
        class Judge:
            async def evaluate(self, **kwargs):
                await pause("judge")
                return {"status": "PASS"}
            async def close(self):
                assert closing.is_set()
        monkeypatch.setattr(runner, "YandexAgentClient", Agent)
        monkeypatch.setattr(runner, "JudgeClient", Judge)
        task = asyncio.create_task(runner.execute_run(run_id))
        runner.RUN_TASKS[run_id] = task
        await asyncio.wait_for(entered.wait(), 3)
        try:
            assert client.post(f"/api/runs/{run_id}/cancel", headers=ADMIN_HEADERS).status_code == 200
            assert client.post(f"/api/runs/{run_id}/cancel", headers=ADMIN_HEADERS).status_code == 200
            assert client.delete(f"/api/runs/{run_id}", headers=ADMIN_HEADERS).status_code == 409
            with factory() as db:
                assert db.get(Run, run_id).status == "running"
            release.set()
            await asyncio.wait_for(task, 3)
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        assert run_id not in runner.RUN_TASKS
    asyncio.run(scenario())
    assert calls == {"setup": ["setup"], "answer": ["setup", "answer"], "judge": ["setup", "answer", "judge"]}[stage]
    with factory() as db:
        assert db.get(Run, run_id).status == "cancelled"
        assert db.get(Result, ids[0]).answer == (None if stage == "setup" else "Ответ сохранён")
        assert db.get(Result, ids[1]).state == "pending"
    assert client.delete(f"/api/runs/{run_id}", headers=ADMIN_HEADERS).status_code == 200
    with factory() as db:
        assert not db.scalars(select(Result).where(Result.run_id == run_id)).all()


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled", "draft"])
def test_delete_terminal_and_draft(api_client, status):
    client, factory = api_client
    run_id, _ = _seed_run(factory, status, status)
    assert client.delete(f"/api/runs/{run_id}", headers=ADMIN_HEADERS).status_code == 200


def test_no_terminal_run_can_overwrite_its_history(api_client):
    client, factory = api_client
    for status in ("cancelled", "failed", "completed"):
        run_id, _ = _seed_run(factory, status, status)
        assert client.post(f"/api/runs/{run_id}/start", headers=ADMIN_HEADERS).status_code == 409
        with factory() as db:
            assert db.get(Run, run_id).status == status


def test_launch_delete_serialization_and_duplicate_start(api_client, monkeypatch):
    client, factory = api_client
    monkeypatch.setattr(main, "start_run", lambda _: None)
    run_id, _ = _seed_run(factory, "draft", "launch-first")
    assert client.post(f"/api/runs/{run_id}/start", headers=ADMIN_HEADERS).status_code == 200
    assert client.post(f"/api/runs/{run_id}/start", headers=ADMIN_HEADERS).status_code == 409
    assert client.delete(f"/api/runs/{run_id}", headers=ADMIN_HEADERS).status_code == 409
    deleted_id, _ = _seed_run(factory, "draft", "delete-first")
    assert client.delete(f"/api/runs/{deleted_id}", headers=ADMIN_HEADERS).status_code == 200
    assert client.post(f"/api/runs/{deleted_id}/start", headers=ADMIN_HEADERS).status_code == 404


def test_delete_rejects_stale_draft_after_another_session_launches(api_client):
    from fastapi import HTTPException
    _, factory = api_client
    run_id, ids = _seed_run(factory, "draft", "stale-reader")
    with factory() as stale:
        old = stale.get(Run, run_id)
        assert old.status == "draft"
        with factory() as writer:
            writer.get(Run, run_id).status = "queued"
            writer.commit()
        # The stale ORM object passes the initial check. The conditional SQL write
        # must still reject deletion and preserve children.
        with pytest.raises(HTTPException) as error:
            asyncio.run(main.delete_run(run_id, stale))
        assert error.value.status_code == 409
    with factory() as db:
        assert db.get(Run, run_id).status == "queued"
        assert db.get(Result, ids[0]) is not None


def test_child_deletion_rolls_back_if_parent_deletion_fails(api_client):
    from sqlalchemy import event
    client, factory = api_client
    run_id, ids = _seed_run(factory, "cancelled", "rollback", result_count=2)
    engine = factory.kw["bind"]
    def fail_parent_delete(connection, cursor, statement, parameters, context, many):
        if statement.startswith("DELETE FROM runs"):
            raise RuntimeError("Injected parent-delete failure")
    event.listen(engine, "before_cursor_execute", fail_parent_delete)
    try:
        with pytest.raises(RuntimeError, match="Injected"):
            client.delete(f"/api/runs/{run_id}", headers=ADMIN_HEADERS)
    finally:
        event.remove(engine, "before_cursor_execute", fail_parent_delete)
    with factory() as db:
        assert db.get(Run, run_id).status == "cancelled"
        assert all(db.get(Result, id) is not None for id in ids)


def test_worker_guard_and_restart_recovery(api_client, tmp_path):
    _, factory = api_client
    active, _ = _seed_run(factory, "running", "interrupted")
    stopped, _ = _seed_run(factory, "queued", "stopping")
    with factory() as db:
        db.get(Run, stopped).cancel_requested = True
        db.commit()
    db_engine = create_engine("sqlite:///" + str(tmp_path / "guard.db"))
    with lifecycle.worker_guard(db_engine):
        with pytest.raises(RuntimeError, match="worker"):
            with lifecycle.worker_guard(db_engine):
                lifecycle.recover_interrupted_runs(factory)
        with factory() as db:
            assert db.get(Run, active).status == "running"
        assert lifecycle.recover_interrupted_runs(factory) == 2
        assert lifecycle.recover_interrupted_runs(factory) == 0
    with lifecycle.worker_guard(db_engine):
        pass
    with factory() as db:
        assert db.get(Run, active).status == "failed"
        assert db.get(Run, stopped).status == "cancelled"
    db_engine.dispose()


def test_additive_migration_keeps_legacy_values(tmp_path, monkeypatch):
    db_engine = create_engine("sqlite:///" + str(tmp_path / "legacy.db"))
    with db_engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE runs (id INTEGER PRIMARY KEY, name TEXT, prompt_version TEXT)")
        connection.exec_driver_sql("INSERT INTO runs VALUES (1, 'history', 'current')")
    monkeypatch.setattr(database, "engine", db_engine)
    database.init_db()
    database.init_db()
    assert "provenance" in {x["name"] for x in inspect(db_engine).get_columns("runs")}
    with db_engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT name, prompt_version, provenance FROM runs").one() == ("history", "current", None)
    db_engine.dispose()


def test_all_mutations_require_auth(api_client):
    client, factory = api_client
    run_id, ids = _seed_run(factory, "draft", "protected")
    assert client.post("/api/runs", json={"name": "x", "judge_model": "test"}).status_code == 401
    assert client.post(f"/api/runs/{run_id}/start").status_code == 401
    assert client.patch(f"/api/results/{ids[0]}", json={"manual_status": "PASS"}).status_code == 401
    assert client.get(f"/api/runs/{run_id}?raw=true").status_code == 401


def test_failure_drains_sibling_dialogues_before_terminal(api_client, monkeypatch):
    client, factory = api_client
    run_id, _ = _seed_run(factory, "queued", "siblings", result_count=2)
    monkeypatch.setattr(runner, "SessionLocal", factory)
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        class Client:
            async def close(self):
                assert release.is_set()
        monkeypatch.setattr(runner, "YandexAgentClient", Client)
        monkeypatch.setattr(runner, "JudgeClient", Client)
        n = 0
        async def dialogue(*args):
            nonlocal n
            n += 1
            if n == 1:
                raise RuntimeError("dialogue failure")
            entered.set()
            await release.wait()
        monkeypatch.setattr(runner, "process_dialogue", dialogue)
        task = asyncio.create_task(runner.execute_run(run_id))
        await asyncio.wait_for(entered.wait(), 3)
        assert client.delete(f"/api/runs/{run_id}", headers=ADMIN_HEADERS).status_code == 409
        release.set()
        await task
    asyncio.run(scenario())
    with factory() as db:
        assert db.get(Run, run_id).status == "failed"
