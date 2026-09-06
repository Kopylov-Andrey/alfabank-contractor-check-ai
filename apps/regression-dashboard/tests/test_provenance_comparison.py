import csv
import io

from app.database import Result, Run
from app.metrics import calculate_metrics
from app.provenance import capture_provenance
from app.cases import build_suite
from test_run_management import ADMIN_HEADERS, _seed_run, api_client


def test_new_and_legacy_provenance_are_distinct(api_client):
    client, factory = api_client
    legacy, _ = _seed_run(factory, "completed", "legacy")
    data = client.get(f"/api/runs/{legacy}").json()
    assert data["provenance"]["prompt_source"] == "unknown"
    assert data["provenance"]["metrics_version"] == "legacy-v1"
    assert "judge_prompt_version" not in data["provenance"]
    provenance = capture_provenance(build_suite("main"), "external-label")
    assert provenance["prompt_source"] == "user_label"
    assert provenance["agent_prompt_verified"] is False
    assert provenance["judge_prompt_version"] == "judge-v2.0"
    assert len(provenance["evaluator_sha256"]) == 64
    assert provenance == capture_provenance(build_suite("main"), "external-label")
    assert provenance["suite_sha256"] != capture_provenance(build_suite("full"), "")["suite_sha256"]


def test_metrics_keep_legacy_and_separate_new_technical_errors(api_client):
    client, factory = api_client
    run_id, ids = _seed_run(factory, "completed", "metrics", result_count=2)
    with factory() as db:
        a, b = [db.get(Result, id) for id in ids]
        a.state = "completed"; a.answer = "Ответ"; a.auto_status = "CRITICAL"
        a.auto_evaluation = {"status":"PASS","factual_correct":True,"useful":True,
                             "algorithmic":{"status":"CRITICAL"}}
        b.state = "error"; b.answer = "Есть ответ"; b.auto_status = "FAIL"
        b.technical_error = "Judge HTTP 503"; b.auto_evaluation = {"status":"FAIL","technical_error":True}
        db.commit()
        legacy = calculate_metrics([a,b])
        new = calculate_metrics([a,b],version="quality-v2")
        assert legacy["statuses"]["FAIL"] == 1
        assert new["statuses"]["FAIL"] == 0
        assert new["critical"]["value"] == 0
        assert new["combined"]["critical"]["value"] == 1
        assert new["algorithmic"]["critical"]["value"] == 1
        assert new["gtsr"]["total"] == legacy["gtsr"]["total"] == 40
        assert new["technical"]["errors"] == 1
        assert new["progress"] == legacy["progress"]
        assert new["release_gate"] == legacy["release_gate"] == "PENDING"
        a.manual_status = "PARTIAL"; db.commit()
        assert calculate_metrics([a],version="quality-v2")["statuses"]["PARTIAL"] == 1
    # No stored status was recomputed by reads.
    assert client.get(f"/api/runs/{run_id}").json()["results"][1]["auto_status"] == "FAIL"


def test_zero_evaluated_is_no_data():
    from types import SimpleNamespace
    metrics = calculate_metrics([SimpleNamespace(state="pending") for _ in range(59)],version="quality-v2")
    assert metrics["gtsr"]["percent"] is None
    assert metrics["completeness"]["percent"] is None
    assert metrics["release_gate"] == "PENDING"


def test_comparison_repeats_missing_technical_and_manual(api_client):
    client, factory = api_client
    a_id, a_ids = _seed_run(factory, "completed", "baseline",result_count=4)
    b_id, b_ids = _seed_run(factory, "cancelled", "candidate",result_count=3)
    with factory() as db:
        for id in a_ids + b_ids:
            row = db.get(Result,id); row.state = "completed"; row.answer = "answer"; row.auto_status = "FAIL"
            row.auto_evaluation = {"status":"FAIL"}
        b0,b1,b2 = [db.get(Result,id) for id in b_ids]
        b0.manual_status = "PASS"
        b1.state = "error"; b1.technical_error = "Judge error"
        b2.auto_status = "PASS"
        db.get(Result,a_ids[2]).attempt = b2.attempt = 2
        db.commit()
    response = client.get(f"/api/compare?baseline={a_id}&candidate={b_id}")
    assert response.status_code == 200
    comparison = response.json()
    assert comparison["counts"] == {"improved":2,"unavailable":2}
    assert comparison["rows"][2]["attempt"] == 2
    assert comparison["rows"][0]["candidate"]["manual"] == "PASS"
    assert comparison["rows"][1]["reason"] == "Техническая ошибка"
    assert comparison["rows"][3]["reason"] == "Кейс отсутствует в одном из прогонов"
    assert any("версия неизвестна" in warning for warning in comparison["warnings"])
    assert client.get(f"/api/compare?baseline={a_id}&candidate={a_id}").status_code == 400
    assert client.get(f"/api/compare?baseline={a_id}&candidate=99999").status_code == 404


def test_history_search_status_sort_and_pagination(api_client):
    client, factory = api_client
    a,_ = _seed_run(factory,"completed","Тест %")
    b,_ = _seed_run(factory,"running","Другой")
    with factory() as db:
        db.get(Run,b).cancel_requested = True; db.commit()
    assert [run["id"] for run in client.get("/api/runs?q=%25").json()] == [a]
    assert [run["id"] for run in client.get("/api/runs?status=cancelling").json()] == [b]
    assert client.get("/api/runs?sort=asc&limit=1").json()[0]["id"] == a
    assert client.get("/api/runs?sort=asc&limit=1&offset=1").json()[0]["id"] == b


def test_export_partial_unicode_formula_injection_and_html_escaping(api_client):
    client, factory = api_client
    run_id, ids = _seed_run(factory,"cancelled","<script>alert(1)</script>")
    with factory() as db:
        row = db.get(Result,ids[0])
        row.question = " =HYPERLINK(\"https://example.invalid\")"
        row.answer = "@SUM(1)\nРусский ответ\n<script>alert(2)</script>"
        row.state = "error"; row.technical_error = "Judge error"
        row.auto_status = "FAIL"; row.auto_evaluation = {"status":"FAIL","technical_error":True}
        row.manual_status = "PARTIAL"; row.manual_comment = "+1+2"
        row.latency_ms = 0; db.commit()
    response = client.get(f"/api/runs/{run_id}/export/csv")
    assert response.content.startswith(b"\xef\xbb\xbf")
    record = next(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert record["run_id"] == str(run_id) and record["run_status"] == "cancelled"
    assert record["incomplete"] == "True"
    assert record["question"].startswith("' =")
    assert record["answer"].startswith("'@SUM(1)\nРусский")
    assert record["manual_comment"].startswith("'+")
    assert record["llm_status"] == ""
    assert record["combined_status"] == "FAIL"
    assert record["effective_status"] == ""
    assert record["manual_status"] == "PARTIAL"
    assert record["latency_ms"] == "0.0"
    assert record["evaluator_sha256"] == "Версия неизвестна"
    html = client.get(f"/api/runs/{run_id}/export/pdf").text
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "Техническая ошибка" in html and "Judge error" in html
    assert "Предварительно" in html and "Русский ответ" in html
    assert "Нет данных" in html


def test_manual_judge_flag_kept_separate_from_algorithm(api_client):
    client, factory = api_client
    run_id, ids = _seed_run(factory,"completed","review")
    with factory() as db:
        row = db.get(Result,ids[0])
        row.state="completed"; row.answer="Ответ"; row.auto_status="PARTIAL"
        row.auto_evaluation={"status":"PARTIAL","requires_manual_review":True,
                             "algorithmic":{"status":"PASS","requires_manual_review":False}}
        db.commit()
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["execution"]["review_pending"] == 1
    assert run["metrics"]["algorithmic"]["manual_review"]["value"] == 0
    saved = client.patch(f"/api/results/{ids[0]}",headers=ADMIN_HEADERS,json={"manual_status":"PASS","manual_comment":"Проверено"})
    assert saved.status_code == 200
    assert saved.json()["auto_status"] == "PARTIAL"
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["execution"]["review_pending"] == 0
    assert run["execution"]["review_flags"] == 1


def test_csv_formula_prefixes_with_controls_and_unicode_whitespace():
    from app.export import _safe_cell
    for value in ("=SUM(1)", "+1", "-2", "@SUM(1)", "\t=1", "\r=1",
                  "\ufeff=1", "\u00a0=1", "\x01=1", " \n@SUM(1)"):
        assert _safe_cell(value) == "'" + value
    assert _safe_cell("Обычный\nмногострочный ответ") == "Обычный\nмногострочный ответ"
    assert _safe_cell(-123) == -123
