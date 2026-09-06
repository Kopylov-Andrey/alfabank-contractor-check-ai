"""Disposable offline fixture server used only by browser-smoke.mjs."""
import asyncio
import os
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

if os.getenv("BROWSER_TEST_MODE") != "1":
    raise RuntimeError("This fixture server requires BROWSER_TEST_MODE=1")
db_path = Path(os.environ["BROWSER_TEST_DB"]).resolve()
test_root = (Path(__file__).resolve().parents[1] / ".pytest_cache").resolve()
if test_root not in db_path.parents or db_path.exists():
    raise RuntimeError("Browser fixtures require a NEW database under .pytest_cache")
os.environ["DATABASE_URL"] = "sqlite:///" + str(db_path)
os.environ["YANDEX_API_KEY"] = ""
os.environ["JUDGE_API_KEY"] = ""
os.environ["ADMIN_TOKEN"] = "browser-test-only"

from app import database, runner
from app.cases import build_suite
from app.clients import AgentResponse
from app.database import Run, Result
from app.provenance import capture_provenance


class OfflineAgent:
    async def ask(self, *args):
        await asyncio.sleep(.25)
        return AgentResponse("Ответ локальной заглушки", "offline-response", 250, {}, [], [], {})
    async def close(self):
        pass


class OfflineJudge:
    async def evaluate(self, **kwargs):
        await asyncio.sleep(.25)
        return {"status":"PARTIAL","reason":"Оценка локальной заглушки","requires_manual_review":True,
                "uncertainty_reasons":["Это синтетические данные"],"factual_correct":None,
                "required_facts_total":1,"required_facts_matched":0,"claims_total":1,"claims_with_source":0,
                "useful":True,"false_refusal":False,"critical_flags":[]}
    async def close(self):
        pass


runner.YandexAgentClient = OfflineAgent
runner.JudgeClient = OfflineJudge
database.init_db()
suite = build_suite("full")
with database.SessionLocal() as db:
    for index, name, status in [(1,"Базовый прогон","completed"), (2,"Regression · running","cancelled"), (3,"Проверка судьи v2","completed")]:
        run = Run(name=name,judge_model="offline-judge",prompt_version="ручная метка",scope="full",status=status,
                  created_at=datetime.now(timezone.utc)-timedelta(days=4-index),
                  provenance=capture_provenance(suite,"ручная метка") if index==3 else None)
        db.add(run); db.flush()
        for position, case in enumerate(suite,1):
            values=asdict(case)
            for key in ("id","company_name","inn"):
                values.pop(key)
            row = Result(run_id=run.id,position=position,case_id=case.id,**values)
            if status=="completed" or position<20:
                row.state="completed"
                row.answer="Подтверждённая часть ответа. Источник: Реквизиты.\n<script>window.unsafeRendered=true</script>"
                row.auto_status="PASS" if position%5 else "PARTIAL"
                row.auto_evaluation={"status":row.auto_status,"reason":"Не хватает точного основания для части ответа" if position%5==0 else "Обязательные факты отражены",
                                     "factual_correct":True,"useful":True,"required_facts_total":2,"required_facts_matched":2,
                                     "claims_total":2,"claims_with_source":2,"web_search_used":case.is_web,
                                     "web_search_labeled_correctly":True if case.is_web else None,
                                     "requires_manual_review":position%5==0,
                                     "algorithmic":{"status":"PASS","reason":"Проверены обязательные факты","required_facts_total":2,"required_facts_matched":2,
                                                    "requires_manual_review":False,"critical_flags":[]}}
                row.latency_ms=1800+position*25
            if position==2 and index==3:
                row.state="error"; row.technical_error="Offline judge: временная техническая ошибка"
                row.auto_status=None; row.auto_evaluation={"technical_error":True}
            if position==3 and index==3:
                row.auto_status="CRITICAL"
                row.auto_evaluation={"status":"CRITICAL","reason":"Доказанный неверный контрагент в синтетическом ответе",
                                     "critical_flags":["Подменена идентичность"],"critical_violations":["Неверная компания: ответ и эталон различаются"],
                                     "algorithmic":{"status":"CRITICAL","reason":"Неверная компания","critical_flags":["Идентичность"]}}
            db.add(row)
    db.commit()

from app.main import app
