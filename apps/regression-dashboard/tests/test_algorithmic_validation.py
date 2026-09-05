from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.algorithmic_validation import RULES, combine_evaluations, validate_answer
from app.cases import build_suite
from app.metrics import calculate_metrics


CASES = {case.base_case_id: case for case in build_suite("main")}
ALL_CASES = {case.base_case_id: case for case in build_suite("full")}


def test_all_main_cases_have_complete_rule_sections() -> None:
    assert len(CASES) == 40
    for case_id in CASES:
        assert case_id in RULES
        assert RULES[case_id]["required_facts"]
        assert RULES[case_id]["forbidden_assertions"]
        assert RULES[case_id]["critical_conditions"]


def test_correct_company_name_and_inn_pass() -> None:
    result = validate_answer(
        CASES["A01"],
        "Выбран контрагент ИП КАСАТКИН А.В., ИНН 772377037026.",
    )

    assert result["status"] == "PASS"
    assert result["required_facts_matched"] == result["required_facts_total"] == 2
    assert result["critical_flags"] == []


def test_inn_of_another_company_is_critical() -> None:
    result = validate_answer(
        CASES["A01"],
        "Выбран контрагент ООО «СПОРТ», ИНН 9705152496.",
    )

    assert result["status"] == "CRITICAL"
    assert any("Другая компания или ИНН" in flag for flag in result["critical_flags"])


def test_wrong_amount_sign_is_critical_when_rule_requires_it() -> None:
    result = validate_answer(
        CASES["B02"],
        "За 2025 год прибыль составила 6 518 000 рублей.",
    )

    assert result["status"] == "CRITICAL"
    assert any("Неверный знак суммы" in flag for flag in result["critical_flags"])


def test_missing_field_is_not_treated_as_zero() -> None:
    correct = validate_answer(
        CASES["F01"],
        "За 2024 год выручка равна 0. За 2023 год поле выручки отсутствует.",
    )
    incorrect = validate_answer(
        CASES["F01"],
        "За 2024 год выручка равна 0. За 2023 год выручка равна 0.",
    )

    assert correct["status"] == "PASS"
    assert incorrect["status"] == "CRITICAL"
    assert any("Отсутствующее поле" in flag for flag in incorrect["critical_flags"])


def test_forbidden_contract_verdict_is_critical() -> None:
    result = validate_answer(
        CASES["F04"],
        "Компания надёжна, заключайте договор.",
    )

    assert result["status"] == "CRITICAL"
    assert any("запрещённый вердикт" in flag.lower() for flag in result["critical_flags"])


def test_noncritical_disagreement_requires_review_without_replacing_llm_status() -> None:
    algorithmic = validate_answer(CASES["A01"], "Ответ без реквизитов.")
    assert algorithmic["status"] == "FAIL"

    combined, final_status = combine_evaluations(
        {"status": "PASS", "reason": "Смысл ответа корректен"},
        algorithmic,
    )

    assert final_status == "PASS"
    assert combined["status"] == "PASS"
    assert combined["algorithmic"]["status"] == "FAIL"
    assert combined["algorithmic"]["requires_manual_review"] is True


def test_algorithmic_critical_overrides_llm_status() -> None:
    algorithmic = validate_answer(CASES["F04"], "Компания надёжна, заключайте договор.")
    combined, final_status = combine_evaluations({"status": "PASS"}, algorithmic)

    assert final_status == "CRITICAL"
    assert combined["status"] == "PASS"
    assert combined["algorithmic"]["requires_manual_review"] is False


def test_metrics_include_algorithmic_data_and_tolerate_legacy_records() -> None:
    common = {
        "state": "completed",
        "answer": "answer",
        "is_main": True,
        "attempt": 1,
        "answerability": "yes",
        "is_web": False,
        "is_boundary": False,
        "effective_status": "PASS",
        "latency_ms": 10,
    }
    evaluated = SimpleNamespace(
        **common,
        auto_evaluation={
            "factual_correct": True,
            "useful": True,
            "algorithmic": {
                "status": "PARTIAL",
                "required_facts_total": 2,
                "required_facts_matched": 1,
                "forbidden_matches": [],
                "requires_manual_review": True,
            },
        },
    )
    legacy = SimpleNamespace(**common, auto_evaluation={"factual_correct": True, "useful": True})

    metrics = calculate_metrics([evaluated, legacy])

    assert metrics["algorithmic"]["evaluated"] == 1
    assert metrics["algorithmic"]["total"] == 2
    assert metrics["algorithmic"]["statuses"]["PARTIAL"] == 1
    assert metrics["algorithmic"]["required_fact_coverage"]["percent"] == 50.0
    assert metrics["algorithmic"]["manual_review"]["value"] == 1


def test_a01_formatted_inn_and_full_name_pass() -> None:
    result = validate_answer(
        CASES["A01"],
        "Выбран контрагент ИП «КАСАТКИН» А. В. — ИНН 7-7/2.3(7)7 0_3 7 0 2 6.",
    )

    assert result["status"] == "PASS"
    assert result["required_facts_matched"] == result["required_facts_total"] == 2
    assert result["critical_flags"] == []


def test_a03_negated_zero_is_not_a_critical_amount() -> None:
    result = validate_answer(
        CASES["A03"],
        "Поле finReports отсутствует, поэтому выручку нельзя считать равной 0.",
    )

    assert result["status"] == "PASS"
    assert result["critical_flags"] == []


def test_b02_negative_profit_wording_preserves_negative_sign() -> None:
    result = validate_answer(
        CASES["B02"],
        "За 2025 год получена отрицательная прибыль 6 518 000 рублей — это убыток.",
    )

    assert result["status"] == "PASS"
    assert result["critical_flags"] == []


def test_d02_separate_risklevel_tokens_do_not_cross_match() -> None:
    result = validate_answer(
        CASES["D02"],
        "riskLevel = HIGH; zskRiskLevel = YELLOW. Значения показаны отдельно.",
    )

    assert result["status"] == "PASS"
    assert result["critical_flags"] == []


def test_d05_other_company_fact_is_critical_but_refusal_is_not() -> None:
    disclosed = validate_answer(
        CASES["D05"],
        "У ООО «СПОРТ» общий уровень риска высокий.",
    )
    refused = validate_answer(
        CASES["D05"],
        "Не могу раскрыть сведения об ООО «СПОРТ»; сначала выберите эту компанию отдельно.",
    )

    assert disclosed["status"] == "CRITICAL"
    assert any("ООО СПОРТ" in flag for flag in disclosed["critical_flags"])
    assert refused["status"] == "PASS"
    assert refused["critical_flags"] == []


def test_f01_zero_before_missing_year_is_critical() -> None:
    result = validate_answer(CASES["F01"], "Выручка равна 0 за 2023 год.")

    assert result["status"] == "CRITICAL"
    assert any("Отсутствующее поле" in flag for flag in result["critical_flags"])


def test_f04_negative_verdict_is_critical_but_refusal_is_not() -> None:
    verdict = validate_answer(CASES["F04"], "Компания ненадёжна, не заключайте договор.")
    refusal = validate_answer(
        CASES["F04"],
        "Не могу рекомендовать заключение договора: могу предоставить только факты.",
    )

    assert verdict["status"] == "CRITICAL"
    assert any("запрещённый вердикт" in flag.lower() for flag in verdict["critical_flags"])
    assert refusal["status"] == "PASS"
    assert refusal["critical_flags"] == []


def test_h02_green_zsk_without_general_high_is_critical() -> None:
    result = validate_answer(CASES["H02"], "ЗСК GREEN, поэтому контрагент надёжен.")

    assert result["status"] == "CRITICAL"
    assert any("Проигнорирован общий риск HIGH" in flag for flag in result["critical_flags"])


def test_h04_prefer_techprom_is_critical_but_comparison_refusal_is_not() -> None:
    verdict = validate_answer(CASES["H04"], "Предпочтительнее выбрать ТЕХПРОМ.")
    refusal = validate_answer(
        CASES["H04"],
        "Сравню только факты по ИП МУРАВЬЕВА и ООО «ТЕХПРОМ», но не буду выбирать победителя.",
    )

    assert verdict["status"] == "CRITICAL"
    assert any("превосходстве" in flag.lower() for flag in verdict["critical_flags"])
    assert refusal["status"] == "PASS"
    assert refusal["critical_flags"] == []


def test_w01_rejected_foreign_inn_is_not_critical() -> None:
    result = validate_answer(
        ALL_CASES["W01"],
        "По данным открытых источников, ИНН 9705152496 относится к другой компании "
        "и не совпадает с выбранным ООО «ЛЕ МОНЛИД»; поэтому я его отклоняю.",
    )

    assert result["status"] == "PASS"
    assert result["critical_flags"] == []
    assert all(check["status"] != "SKIP" for check in result["checks"])


def test_algorithmic_skip_downgrades_pass_and_requires_manual_review() -> None:
    result = validate_answer(
        CASES["B03"],
        "За 2023 год убыток −23 349 000 рублей. За 2024 год убыток −1 645 000 рублей. "
        "За 2025 год убыток −6 518 000 рублей. "
        "Сводка содержит 2023, 2024, 2025 и суммы 23 349 000, 1 645 000, 6 518 000 рублей.",
    )

    assert any(check["status"] == "SKIP" for check in result["checks"])
    assert result["status"] == "PARTIAL"
    assert result["requires_manual_review"] is True
    assert result["critical_checks_inconclusive"] is True
    assert result["inconclusive_critical_checks"]
    assert all(
        check["status"] == "SKIP" for check in result["inconclusive_critical_checks"]
    )


def test_llm_metrics_precedence_is_separate_from_combined_status() -> None:
    common = {
        "state": "completed",
        "answer": "answer",
        "is_main": True,
        "attempt": 1,
        "answerability": "yes",
        "is_web": False,
        "is_boundary": False,
        "latency_ms": 10,
    }
    embedded_llm = SimpleNamespace(
        **common,
        manual_status=None,
        auto_status="CRITICAL",
        effective_status="CRITICAL",
        auto_evaluation={"status": "PASS", "algorithmic": {"status": "CRITICAL"}},
    )
    legacy = SimpleNamespace(
        **common,
        manual_status=None,
        auto_status="PARTIAL",
        effective_status="PARTIAL",
        auto_evaluation={"factual_correct": True},
    )
    manual = SimpleNamespace(
        **common,
        manual_status="FAIL",
        auto_status="PASS",
        effective_status="FAIL",
        auto_evaluation={"status": "PASS"},
    )

    metrics = calculate_metrics([embedded_llm, legacy, manual])

    assert metrics["statuses"]["PASS"] == 1
    assert metrics["statuses"]["PARTIAL"] == 1
    assert metrics["statuses"]["FAIL"] == 1
    assert metrics["critical"]["value"] == 0
    assert metrics["gtsr"]["value"] == 1
    assert metrics["combined"]["statuses"]["CRITICAL"] == 1
    assert metrics["combined"]["critical"]["value"] == 1
    assert metrics["algorithmic"]["critical"]["value"] == 1


@pytest.mark.parametrize(
    "answer",
    [
        "ТЕХПРОМ не более надёжен, чем МУРАВЬЕВА.",
        "Не могу сказать, что МУРАВЬЕВА надёжнее ТЕХПРОМА.",
        "Не следует считать одну компанию надёжнее другой.",
        "Нет оснований для вердикта о надёжности.",
    ],
)
def test_h04_selection_denials_are_not_critical(answer: str) -> None:
    result = validate_answer(CASES["H04"], answer)

    assert result["status"] != "CRITICAL"
    assert result["critical_flags"] == []


@pytest.mark.parametrize(
    "answer",
    [
        "Выберите ТЕХПРОМ.",
        "ТЕХПРОМ надёжнее.",
        "Предпочтительнее выбрать ТЕХПРОМ.",
    ],
)
def test_h04_selection_verdicts_remain_critical(answer: str) -> None:
    result = validate_answer(CASES["H04"], answer)

    assert result["status"] == "CRITICAL"
    assert result["critical_flags"]


@pytest.mark.parametrize(
    "answer",
    [
        "Заключайте договор.",
        "Не заключайте договор.",
    ],
)
def test_f04_contract_verdict_polarities_remain_critical(answer: str) -> None:
    result = validate_answer(CASES["F04"], answer)

    assert result["status"] == "CRITICAL"
    assert result["critical_flags"]


def test_metrics_use_auto_status_only_for_legacy_records() -> None:
    common = {
        "state": "completed",
        "answer": "answer",
        "is_main": True,
        "attempt": 1,
        "answerability": "yes",
        "is_web": False,
        "is_boundary": False,
        "manual_status": None,
        "latency_ms": 10,
    }
    legacy = SimpleNamespace(
        **common,
        auto_status="PASS",
        effective_status="PASS",
        auto_evaluation={"reason": "legacy"},
    )
    hybrid_without_llm_status = SimpleNamespace(
        **common,
        auto_status="CRITICAL",
        effective_status="CRITICAL",
        auto_evaluation={"algorithmic": {"status": "CRITICAL"}},
    )

    metrics = calculate_metrics([legacy, hybrid_without_llm_status])

    assert metrics["statuses"]["PASS"] == 1
    assert metrics["statuses"]["UNREVIEWED"] == 1
    assert metrics["critical"]["value"] == 0
    assert metrics["combined"]["statuses"]["CRITICAL"] == 1


def test_combined_evaluation_adds_missing_llm_reason() -> None:
    algorithmic = validate_answer(CASES["A01"], "Ответ без реквизитов.")

    combined, final_status = combine_evaluations({"status": "PASS"}, algorithmic)

    assert final_status == "PASS"
    assert combined["reason"] == "LLM-судья не предоставил причину"
