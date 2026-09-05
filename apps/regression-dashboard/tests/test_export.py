from __future__ import annotations

import csv
import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.database import Base, Result, Run, get_db


@pytest.fixture
def api_client():
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

    main_module.app.dependency_overrides[get_db] = override_get_db
    with TestClient(main_module.app) as client:
        yield client, testing_session
    main_module.app.dependency_overrides.clear()
    engine.dispose()


def _seed_run(testing_session, name: str = "test-run") -> int:
    with testing_session() as db:
        run = Run(
            name=name,
            prompt_version="test-v1",
            judge_model="test-judge",
            scope="main",
            status="completed",
        )
        run.results = [
            Result(
                position=1,
                case_id="A01",
                base_case_id="A01",
                attempt=1,
                company_code="A",
                dialogue_key="dialogue-1",
                category="Basic Info",
                question="Test question?",
                expected="Expected behavior",
                evidence="Evidence list",
                forbidden="Forbidden list",
                critical_if="Critical condition",
                answerability="yes",
                is_main=True,
                is_boundary=False,
                is_web=False,
                answer="Test answer with correct INN.",
                latency_ms=123.4,
                auto_status="PASS",
                auto_evaluation={
                    "status": "PASS",
                    "reason": "Test passed",
                    "factual_correct": True,
                    "useful": True,
                    "false_refusal": False,
                    "algorithmic": {
                        "status": "PASS",
                        "reason": "All checks passed",
                        "required_facts_matched": 2,
                        "required_facts_total": 2,
                        "forbidden_matches": [],
                        "critical_flags": [],
                        "critical_checks_inconclusive": False,
                        "requires_manual_review": False,
                    },
                },
            ),
            Result(
                position=2,
                case_id="B02",
                base_case_id="B02",
                attempt=1,
                company_code="B",
                dialogue_key="dialogue-2",
                category="Financial",
                question="What is the profit?",
                expected="Report loss correctly",
                evidence="Loss amount",
                forbidden="Positive profit",
                critical_if="Wrong sign",
                answerability="yes",
                is_main=True,
                is_boundary=False,
                is_web=False,
                answer="Loss of 6518000 rubles.",
                latency_ms=234.5,
                auto_status="CRITICAL",
                auto_evaluation={
                    "status": "PASS",
                    "reason": "LLM passed",
                    "factual_correct": True,
                    "useful": True,
                    "false_refusal": False,
                    "algorithmic": {
                        "status": "CRITICAL",
                        "reason": "Wrong sign detected",
                        "required_facts_matched": 1,
                        "required_facts_total": 1,
                        "forbidden_matches": [],
                        "critical_flags": ["Wrong sign: positive instead of negative"],
                        "critical_checks_inconclusive": False,
                        "requires_manual_review": False,
                    },
                },
            ),
        ]
        db.add(run)
        db.commit()
        return run.id


def test_export_csv_returns_valid_csv(api_client) -> None:
    client, testing_session = api_client
    run_id = _seed_run(testing_session, "csv-export-test")

    response = client.get(f"/api/runs/{run_id}/export/csv")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert "attachment" in response.headers["content-disposition"]
    assert "regression-" in response.headers["content-disposition"]

    csv_content = io.StringIO(response.text)
    reader = csv.DictReader(csv_content)
    rows = list(reader)

    assert len(rows) == 2
    assert rows[0]["case_id"] == "A01"
    assert rows[0]["llm_status"] == "PASS"
    assert rows[0]["algorithmic_status"] == "PASS"
    assert rows[0]["combined_status"] == "PASS"
    assert rows[0]["factual_correct"] == "True"

    assert rows[1]["case_id"] == "B02"
    assert rows[1]["llm_status"] == "PASS"
    assert rows[1]["algorithmic_status"] == "CRITICAL"
    assert rows[1]["combined_status"] == "CRITICAL"
    assert "Wrong sign" in rows[1]["critical_flags"]


def test_export_pdf_returns_html_report(api_client) -> None:
    client, testing_session = api_client
    run_id = _seed_run(testing_session, "pdf-export-test")

    response = client.get(f"/api/runs/{run_id}/export/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert "attachment" in response.headers["content-disposition"]
    assert "regression-" in response.headers["content-disposition"]

    html = response.text
    assert "<!DOCTYPE html>" in html
    assert "Regression Report" in html
    assert "pdf-export-test" in html
    assert "Release Gate" in html
    assert "Quality Metrics" in html
    assert "Algorithmic Validation" in html
    assert "Status Distribution" in html


def test_export_missing_run_returns_404(api_client) -> None:
    client, _ = api_client

    csv_response = client.get("/api/runs/99999/export/csv")
    pdf_response = client.get("/api/runs/99999/export/pdf")

    assert csv_response.status_code == 404
    assert pdf_response.status_code == 404


def test_csv_export_handles_legacy_records_without_algorithmic(api_client) -> None:
    client, testing_session = api_client

    with testing_session() as db:
        run = Run(
            name="legacy-run",
            prompt_version="old",
            judge_model="old-judge",
            scope="main",
            status="completed",
        )
        run.results = [
            Result(
                position=1,
                case_id="LEGACY",
                base_case_id="LEGACY",
                attempt=1,
                company_code="A",
                dialogue_key="legacy-1",
                category="Legacy",
                question="Old question",
                expected="Expected",
                evidence="Evidence",
                forbidden="Forbidden",
                critical_if="Critical",
                answerability="yes",
                is_main=True,
                is_boundary=False,
                is_web=False,
                answer="Legacy answer",
                latency_ms=100.0,
                auto_status="PARTIAL",
                auto_evaluation={"reason": "Old evaluation format"},
            )
        ]
        db.add(run)
        db.commit()
        run_id = run.id

    response = client.get(f"/api/runs/{run_id}/export/csv")

    assert response.status_code == 200
    csv_content = io.StringIO(response.text)
    reader = csv.DictReader(csv_content)
    rows = list(reader)

    assert len(rows) == 1
    assert rows[0]["case_id"] == "LEGACY"
    assert rows[0]["llm_status"] == "PARTIAL"
    assert rows[0]["algorithmic_status"] == ""
    assert rows[0]["combined_status"] == "PARTIAL"


def test_export_handles_unicode_in_run_name(api_client) -> None:
    client, testing_session = api_client

    with testing_session() as db:
        run = Run(
            name="Регрессия · 06 сен, 18:30",
            prompt_version="test",
            judge_model="test-judge",
            scope="main",
            status="completed",
        )
        run.results = [
            Result(
                position=1,
                case_id="TEST",
                base_case_id="TEST",
                attempt=1,
                company_code="A",
                dialogue_key="test-1",
                category="Test",
                question="Test?",
                expected="Expected",
                evidence="Evidence",
                forbidden="Forbidden",
                critical_if="Critical",
                answerability="yes",
                is_main=True,
                is_boundary=False,
                is_web=False,
                answer="Test answer",
                latency_ms=100.0,
                auto_status="PASS",
                auto_evaluation={"status": "PASS", "reason": "OK"},
            )
        ]
        db.add(run)
        db.commit()
        run_id = run.id

    csv_response = client.get(f"/api/runs/{run_id}/export/csv")
    pdf_response = client.get(f"/api/runs/{run_id}/export/pdf")

    assert csv_response.status_code == 200
    assert pdf_response.status_code == 200
    # Check that Content-Disposition header has both ASCII fallback and UTF-8 encoded name
    assert "attachment" in csv_response.headers["content-disposition"]
    assert "filename*=UTF-8''" in csv_response.headers["content-disposition"]
    assert "attachment" in pdf_response.headers["content-disposition"]
    assert "filename*=UTF-8''" in pdf_response.headers["content-disposition"]
