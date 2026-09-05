from __future__ import annotations

import json
from dataclasses import dataclass, replace
from importlib.resources import files


@dataclass(frozen=True)
class TestCase:
    id: str
    base_case_id: str
    attempt: int
    company_code: str
    company_name: str
    inn: str
    category: str
    question: str
    answerability: str
    expected: str
    evidence: str
    forbidden: str
    critical_if: str
    is_main: bool
    is_boundary: bool
    is_web: bool
    dialogue_key: str


def _load() -> dict:
    path = files("app").joinpath("data/test_cases.json")
    return json.loads(path.read_text(encoding="utf-8"))


DATA = _load()
COMPANIES: dict[str, dict] = DATA["companies"]
BOUNDARY_IDS: set[str] = set(DATA["boundary_ids"])


def _to_case(raw: dict, *, attempt: int = 1, suffix: str = "") -> TestCase:
    company = COMPANIES[raw["company_code"]]
    case_id = raw["id"] + suffix
    # Основной набор: один связный диалог на компанию. Повторы и Web — отдельные диалоги.
    if suffix:
        dialogue_key = case_id
    elif raw["id"].startswith("W"):
        dialogue_key = raw["id"]
    else:
        dialogue_key = f"MAIN_{raw['company_code']}"
    return TestCase(
        id=case_id,
        base_case_id=raw["id"],
        attempt=attempt,
        company_code=raw["company_code"],
        company_name=company["name"],
        inn=company["inn"],
        category=raw["category"],
        question=raw["question"],
        answerability=raw["answerability"],
        expected=raw["expected"],
        evidence=raw["evidence"],
        forbidden=raw["forbidden"],
        critical_if=raw["critical_if"],
        is_main=raw["is_main"],
        is_boundary=raw["is_boundary"],
        is_web=raw["is_web"],
        dialogue_key=dialogue_key,
    )


def build_suite(scope: str = "full") -> list[TestCase]:
    raw_cases = DATA["cases"]
    main = [_to_case(row) for row in raw_cases if row["is_main"]]
    if scope == "main":
        return main

    repeats: list[TestCase] = []
    if scope in {"full", "boundary"}:
        for attempt in (2, 3):
            for row in raw_cases:
                if row["id"] in BOUNDARY_IDS:
                    repeats.append(_to_case(row, attempt=attempt, suffix=f"_R{attempt}"))

    web = [_to_case(row) for row in raw_cases if row["id"].startswith("W")]
    if scope == "boundary":
        return [case for case in main if case.is_boundary] + repeats
    return main + repeats + web


def public_cases() -> dict:
    return {
        "version": DATA["version"],
        "companies": list(COMPANIES.values()),
        "main_count": 40,
        "boundary_repeat_count": 16,
        "web_count": 3,
        "total_scored": 59,
        "cases": [case.__dict__ for case in build_suite("full")],
    }

