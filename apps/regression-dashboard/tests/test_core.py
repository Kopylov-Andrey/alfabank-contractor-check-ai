from __future__ import annotations

from types import SimpleNamespace

from app.cases import build_suite, public_cases
from app.evaluation import normalize_evaluation
from app.metrics import calculate_metrics, percentile
from app.clients import _extract_agent_response


def test_suite_shape() -> None:
    suite = build_suite("full")
    assert len(suite) == 59
    assert len([case for case in suite if case.is_main and case.attempt == 1]) == 40
    assert len([case for case in suite if case.attempt > 1]) == 16
    assert len([case for case in suite if case.base_case_id.startswith("W")]) == 3
    assert len({case.dialogue_key for case in suite}) == 27


def test_frozen_case_metadata() -> None:
    data = public_cases()
    assert data["version"] == "1.1"
    f01 = next(case for case in data["cases"] if case["id"] == "F01")
    assert "2024" in f01["expected"]
    assert f01["company_code"] == "F"


def test_evaluation_normalization_is_defensive() -> None:
    value = normalize_evaluation(
        {
            "status": "pass",
            "required_facts_total": 2,
            "required_facts_matched": 8,
            "claims_total": 1,
            "claims_with_source": 4,
            "confidence": 3,
            "critical_flags": ["verdict"],
        }
    )
    assert value["status"] == "CRITICAL"
    assert value["required_facts_matched"] == 2
    assert value["claims_with_source"] == 1
    assert value["confidence"] == 1


def test_percentile() -> None:
    assert percentile([1, 2, 3, 4, 5], .95) == 5
    assert percentile([], .95) is None


def test_metrics_empty() -> None:
    rows = [SimpleNamespace(state="pending") for _ in range(59)]
    metrics = calculate_metrics(rows)
    assert metrics["progress"] == {"completed": 0, "total": 59, "percent": 0.0}
    assert metrics["release_gate"] == "PENDING"


def test_extract_agent_response_and_citations() -> None:
    value = _extract_agent_response(
        {
            "id": "resp-1",
            "status": "completed",
            "usage": {"total_tokens": 12},
            "output": [
                {"type": "mcp_call", "name": "get-report-by-inn", "status": "completed"},
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Ответ",
                            "annotations": [
                                {"type": "url_citation", "url": "https://example.com", "title": "Source"},
                                {"type": "url_citation", "url": "https://example.com", "title": "Source"},
                            ],
                        }
                    ],
                },
            ],
        },
        120.0,
    )
    assert value.text == "Ответ"
    assert len(value.citations) == 1
    assert value.tool_calls[0]["name"] == "get-report-by-inn"
