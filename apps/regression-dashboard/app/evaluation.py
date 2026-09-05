from __future__ import annotations

import json
from typing import Any

from .cases import TestCase


JUDGE_SYSTEM = """Ты — независимый строгий валидатор ответов AI-агента проверки контрагентов.
Оценивай только по данному тест-кейсу, ожидаемому поведению и фактическому ответу.
Не додумывай отсутствующие факты. Критическое условие имеет приоритет над общей полезностью.

Верни только JSON со всеми полями:
{
  "status": "PASS|PARTIAL|FAIL|CRITICAL",
  "reason": "краткое проверяемое объяснение",
  "factual_correct": true|false|null,
  "required_facts_total": 0,
  "required_facts_matched": 0,
  "claims_total": 0,
  "claims_with_source": 0,
  "source_marked_correctly": true|false|null,
  "useful": true|false,
  "false_refusal": true|false,
  "refusal_correct": true|false|null,
  "verdict_given": true|false,
  "web_search_used": true|false,
  "web_search_labeled_correctly": true|false|null,
  "critical_flags": ["конкретные нарушения"],
  "missing_facts": ["что пропущено"],
  "unsupported_claims": ["неподтверждённые тезисы"],
  "confidence": 0.0
}

PASS: ответ корректен, полезен и содержит необходимые источники.
PARTIAL: смысл верен, но есть некритичный пропуск.
FAIL: неверный ответ, ложный отказ или существенная неполнота без критического условия.
CRITICAL: сработало явно заданное критическое условие, перепутаны компания/ИНН/сумма/дата/роль,
смешаны общий риск и ЗСК, придуман существенный факт или дан запрещённый вердикт.
confidence — число от 0 до 1. Счётчики должны быть целыми и непротиворечивыми."""


def judge_payload(case: TestCase, answer: str, *, citations: list, tool_calls: list) -> str:
    return json.dumps(
        {
            "test_id": case.id,
            "base_test_id": case.base_case_id,
            "company": {"code": case.company_code, "name": case.company_name, "inn": case.inn},
            "category": case.category,
            "question": case.question,
            "answerability": case.answerability,
            "expected": case.expected,
            "required_evidence": case.evidence,
            "forbidden": case.forbidden,
            "critical_if": case.critical_if,
            "agent_answer": answer,
            "observed_citations": citations,
            "observed_tool_calls": tool_calls,
        },
        ensure_ascii=False,
        indent=2,
    )


def normalize_evaluation(value: dict[str, Any]) -> dict[str, Any]:
    statuses = {"PASS", "PARTIAL", "FAIL", "CRITICAL"}
    status = str(value.get("status", "FAIL")).upper()
    if status not in statuses:
        status = "FAIL"
    normalized = dict(value)
    normalized["status"] = status
    for name in (
        "required_facts_total",
        "required_facts_matched",
        "claims_total",
        "claims_with_source",
    ):
        try:
            normalized[name] = max(0, int(value.get(name, 0)))
        except (TypeError, ValueError):
            normalized[name] = 0
    normalized["required_facts_matched"] = min(
        normalized["required_facts_matched"], normalized["required_facts_total"]
    )
    normalized["claims_with_source"] = min(
        normalized["claims_with_source"], normalized["claims_total"]
    )
    try:
        normalized["confidence"] = min(1.0, max(0.0, float(value.get("confidence", 0))))
    except (TypeError, ValueError):
        normalized["confidence"] = 0.0
    for name in ("critical_flags", "missing_facts", "unsupported_claims"):
        if not isinstance(normalized.get(name), list):
            normalized[name] = []
    if normalized["critical_flags"]:
        normalized["status"] = "CRITICAL"
    return normalized

