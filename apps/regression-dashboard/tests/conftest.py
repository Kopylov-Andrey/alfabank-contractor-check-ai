"""All tests are isolated from the developer's .env, database and paid clients."""
import os
from contextlib import nullcontext

import pytest

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["YANDEX_API_KEY"] = ""
os.environ["JUDGE_API_KEY"] = ""


@pytest.fixture(autouse=True)
def isolate_lifespan_and_network(monkeypatch):
    from app import main
    import httpx
    monkeypatch.setattr(main, "worker_guard", nullcontext)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "recover_interrupted_runs", lambda: None)
    original = httpx.AsyncClient.send

    async def local_only(self, request, *args, **kwargs):
        if not isinstance(self._transport, (httpx.MockTransport, httpx.ASGITransport)):
            raise AssertionError("Real HTTP calls are disabled in tests")
        return await original(self, request, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", local_only)
