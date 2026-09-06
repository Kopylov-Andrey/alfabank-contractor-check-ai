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


# ============================================================================
# P0-1: HIGH + GREEN False CRITICAL Tests
# ============================================================================

def test_high_and_green_separated_not_critical() -> None:
    """H01: Correctly separated HIGH and GREEN should NOT trigger risk_mismatch CRITICAL."""
    result = validate_answer(
        CASES["H01"],
        "Общий риск: HIGH. Источник: отчёт, поле baseInfo.riskLevel\nРиск ЗСК: GREEN. Источник: отчёт, поле zskRiskLevel",
    )

    # Should NOT be CRITICAL due to proximity of HIGH and GREEN
    assert result["status"] != "CRITICAL", f"Got CRITICAL with flags: {result['critical_flags']}"
    # Should match required facts (both risk values present)
    assert result["required_facts_matched"] == 2


def test_high_green_different_order_not_critical() -> None:
    """Risk indicators mentioned in different order should not trigger false positive."""
    result = validate_answer(
        CASES["H01"],
        "Риск ЗСК — GREEN. При этом общий уровень риска компании — HIGH.",
    )

    assert result["status"] != "CRITICAL"


def test_high_green_explicit_separation_not_critical() -> None:
    """Explicitly stating they are different indicators should not trigger mismatch."""
    result = validate_answer(
        CASES["H01"],
        "Общий риск HIGH, а индикатор ЗСК GREEN — это разные показатели.",
    )

    assert result["status"] != "CRITICAL"


def test_high_green_with_negation_not_critical() -> None:
    """Negation context should not trigger false CRITICAL."""
    result = validate_answer(
        CASES["H01"],
        "Нельзя считать общий риск GREEN. В отчёте общий риск HIGH, а ЗСК GREEN.",
    )

    assert result["status"] != "CRITICAL"


def test_high_green_multiline_not_critical() -> None:
    """Multi-line format should not trigger false positive."""
    result = validate_answer(
        CASES["H01"],
        "Общий риск:\nHIGH\n\nЗСК:\nGREEN",
    )

    assert result["status"] != "CRITICAL"


def test_wrong_general_risk_detected() -> None:
    """Wrong general risk value should be detected (at least FAIL/PARTIAL, LLM will judge severity)."""
    result = validate_answer(
        CASES["H01"],
        "Общий риск: GREEN. ЗСК: GREEN.",
    )

    # Should at minimum FAIL/PARTIAL for wrong value (LLM will judge if CRITICAL)
    assert result["status"] in ["FAIL", "PARTIAL", "CRITICAL"]
    assert result["required_facts_matched"] < result["required_facts_total"]


def test_wrong_zsk_risk_detected() -> None:
    """Wrong ZSK value should be detected."""
    result = validate_answer(
        CASES["H01"],
        "Общий риск HIGH. ЗСК HIGH.",
    )

    # Should fail for wrong ZSK
    assert result["status"] in ["FAIL", "PARTIAL", "CRITICAL"]
    assert result["required_facts_matched"] < result["required_facts_total"]


def test_both_risks_swapped_needs_llm() -> None:
    """Both values swapped - algorithmic can't reliably detect this semantic error, LLM will judge."""
    result = validate_answer(
        CASES["H01"],
        "Общий риск GREEN, а ЗСК HIGH.",
    )

    # Algorithmic evaluator may not catch this (proximity matching limitation)
    # LLM judge will need to determine severity
    # We just verify it doesn't false-positive as algorithmicCRITICAL
    assert result["status"] != "CRITICAL" or "risk_mismatch" not in str(result.get("critical_flags", []))


# ============================================================================
# P0-2: E01 Calculated Amount Tests
# ============================================================================

def test_calculated_delta_not_critical() -> None:
    """E01: Correctly calculated delta should NOT trigger unexpected_amount CRITICAL."""
    result = validate_answer(
        CASES["E01"],
        "Выручка компании снизилась:\n"
        "- За 2024 год: 189 687 000 ₽\n"
        "- За 2025 год: 36 689 000 ₽\n"
        "- Изменение: снижение на 152 998 000 ₽ (примерно в 5,2 раза или на 80,7%).",
    )

    # Should NOT be CRITICAL for correctly calculated delta
    assert result["status"] != "CRITICAL", f"Got CRITICAL with flags: {result['critical_flags']}"
    # Should match required facts (both amounts + direction)
    assert result["required_facts_matched"] >= 2


def test_wrong_calculated_delta_still_critical() -> None:
    """E01: Incorrectly calculated delta SHOULD trigger CRITICAL."""
    result = validate_answer(
        CASES["E01"],
        "Выручка снизилась с 189 687 000 до 36 689 000 рублей, разница 180 000 000.",
    )

    # Wrong calculation should still be CRITICAL
    assert result["status"] == "CRITICAL"


def test_invented_amount_still_critical() -> None:
    """E01: Completely invented amount should still trigger CRITICAL."""
    result = validate_answer(
        CASES["E01"],
        "Выручка снизилась. Дополнительный риск оценивается в 200 000 000 рублей.",
    )

    # Invented amount should be CRITICAL
    assert result["status"] == "CRITICAL"


# ============================================================================
# P1-1: D05 Refusal Context Detection
# ============================================================================

@pytest.mark.parametrize("refusal_text", [
    "Для проверки сведений об ООО «СПОРТ» нужно отдельно подтвердить смену компании.",
    "Для проверки выручки ООО «СПОРТ» нужно отдельно подтвердить смену контрагента.",
    "Чтобы проверить сведения об ООО «СПОРТ», подтвердите смену компании или запросите сравнение.",
    "Чтобы получить данные ООО СПОРТ, нужно выбрать эту компанию отдельно.",
    "Сведения об ООО СПОРТ доступны только после смены контрагента.",
])
def test_d05_refusal_with_company_mention_not_critical(refusal_text: str) -> None:
    """D05: Mentioning other company in refusal context should NOT trigger CRITICAL."""
    result = validate_answer(CASES["D05"], refusal_text)

    # Should NOT be CRITICAL for refusal mentioning other company
    assert result["status"] != "CRITICAL", f"Got CRITICAL for refusal: {result['critical_flags']}"


@pytest.mark.parametrize("factual_text", [
    "У ООО «СПОРТ» выручка составляет 50 000 000 рублей.",
    "Общий риск ООО «СПОРТ» LOW.",
    "У ООО «СПОРТ» есть действующие исполнительные производства.",
    "ООО СПОРТ зарегистрировано 5 лет назад.",
    "Выручка ООО СПОРТ за 2025 год составила 100 млн рублей.",
])
def test_d05_factual_claim_about_other_company_critical(factual_text: str) -> None:
    """D05: Actual factual claims about other company SHOULD trigger CRITICAL."""
    result = validate_answer(CASES["D05"], factual_text)

    # Should be CRITICAL for factual claim
    assert result["status"] == "CRITICAL", f"Expected CRITICAL for: {factual_text}"
    assert any("компани" in flag.lower() or "спорт" in flag.lower() for flag in result["critical_flags"])


# ============================================================================
# P1-2: Manual Review Policy
# ============================================================================

def test_manual_review_not_set_for_llm_partial_algo_pass() -> None:
    """LLM PARTIAL + Algo PASS should NOT require manual review (normal responsibility difference)."""
    # Algo finds required facts, LLM downgrades for style/citation
    algorithmic = {"status": "PASS", "reason": "All facts found", "requires_manual_review": False}
    llm = {"status": "PARTIAL", "reason": "Missing precise citations"}

    combined, final_status = combine_evaluations(llm, algorithmic)

    # Final status from LLM (as per policy)
    assert final_status == "PARTIAL"
    # Should NOT require manual review - this is normal separation of concerns
    assert combined["algorithmic"]["requires_manual_review"] is False


def test_manual_review_not_set_for_llm_fail_algo_pass() -> None:
    """LLM FAIL + Algo PASS should NOT require manual review (LLM found semantic error)."""
    algorithmic = {"status": "PASS", "reason": "All facts found", "requires_manual_review": False}
    llm = {"status": "FAIL", "reason": "Hallucinated additional facts"}

    combined, final_status = combine_evaluations(llm, algorithmic)

    assert final_status == "FAIL"
    # LLM found semantic issue beyond algo scope - this is normal
    assert combined["algorithmic"]["requires_manual_review"] is False


def test_manual_review_set_for_llm_pass_algo_fail() -> None:
    """LLM PASS + Algo FAIL SHOULD require manual review (disagreement)."""
    algorithmic = {"status": "FAIL", "reason": "Required fact not found", "requires_manual_review": False}
    llm = {"status": "PASS", "reason": "Semantically correct"}

    combined, final_status = combine_evaluations(llm, algorithmic)

    assert final_status == "PASS"  # LLM wins per policy
    # Disagreement: algo says FAIL, LLM says PASS → manual review
    assert combined["algorithmic"]["requires_manual_review"] is True


def test_manual_review_set_for_llm_pass_algo_partial() -> None:
    """LLM PASS + Algo PARTIAL SHOULD require manual review (missing required fact)."""
    algorithmic = {"status": "PARTIAL", "reason": "1/2 required facts", "requires_manual_review": False}
    llm = {"status": "PASS", "reason": "Answer is correct"}

    combined, final_status = combine_evaluations(llm, algorithmic)

    assert final_status == "PASS"
    # LLM says PASS but algo found incomplete required facts → review
    assert combined["algorithmic"]["requires_manual_review"] is True


def test_manual_review_preserved_when_intrinsic() -> None:
    """Intrinsic manual review (critical_checks_inconclusive) should be preserved."""
    algorithmic = {
        "status": "PARTIAL",
        "reason": "Critical check inconclusive",
        "requires_manual_review": True,  # Intrinsic
    }
    llm = {"status": "PASS", "reason": "Looks good"}

    combined, final_status = combine_evaluations(llm, algorithmic)

    assert final_status == "PASS"
    # Intrinsic manual review preserved
    assert combined["algorithmic"]["requires_manual_review"] is True


def test_algorithmic_critical_overrides_llm() -> None:
    """Algorithmic CRITICAL should override LLM status (unchanged from P0)."""
    algorithmic = {"status": "CRITICAL", "reason": "Wrong company", "requires_manual_review": False}
    llm = {"status": "PASS", "reason": "Looks correct"}

    combined, final_status = combine_evaluations(llm, algorithmic)

    # Algo CRITICAL wins
    assert final_status == "CRITICAL"
    assert combined["algorithmic"]["requires_manual_review"] is False


# ============================================================================
# P1-3: W01 Incomplete Handling
# ============================================================================

def test_no_answer_returns_skipped_status() -> None:
    """Empty/None answer should return status indicating no evaluation possible."""
    # Use A01 as test case (any case works for this test)
    result_empty = validate_answer(CASES["A01"], "")
    result_none = validate_answer(CASES["A01"], None)

    # Should indicate evaluation was skipped
    assert result_empty["status"] == "FAIL"
    assert "пустой" in result_empty["reason"].lower() or "отсутств" in result_empty["reason"].lower()

    assert result_none["status"] == "FAIL"
    assert "пустой" in result_none["reason"].lower() or "отсутств" in result_none["reason"].lower()


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


def test_g02_accepts_exact_derived_period_deltas() -> None:
    result = validate_answer(
        CASES["G02"],
        "За 2024 год: выручка 1 055 829 000 ₽, прибыль 14 079 000 ₽. "
        "За 2023 год: выручка 765 060 000 ₽, убыток 32 215 000 ₽. "
        "Изменение выручки: 290 769 000 ₽; "
        "изменение финансового результата: 46 294 000 ₽.",
    )

    assert result["status"] == "PASS"
    assert result["critical_flags"] == []
    assert all(check["status"] != "SKIP" for check in result["checks"])


@pytest.mark.parametrize("wrong_delta", [290_700_000, 46_200_000])
def test_g02_rejects_incorrect_derived_period_delta(wrong_delta: int) -> None:
    revenue_delta = wrong_delta if wrong_delta > 100_000_000 else 290_769_000
    result_delta = wrong_delta if wrong_delta < 100_000_000 else 46_294_000
    result = validate_answer(
        CASES["G02"],
        "За 2024 год: выручка 1 055 829 000 ₽, прибыль 14 079 000 ₽. "
        "За 2023 год: выручка 765 060 000 ₽, убыток 32 215 000 ₽. "
        f"Изменение выручки: {revenue_delta:,} ₽; "
        f"изменение финансового результата: {result_delta:,} ₽.",
    )

    assert result["status"] == "CRITICAL"
    assert any("Неверная сумма" in flag for flag in result["critical_flags"])


@pytest.mark.parametrize(
    "refusal",
    [
        "Для проверки другой компании нужно подтвердить смену компании.",
        "Подтвердите смену активной компании.",
        "Для проверки другой компании нужно отдельно подтвердить смену контрагента.",
        "Запросите сравнение.",
    ],
)
def test_d05_specialized_switch_refusals_pass(refusal: str) -> None:
    result = validate_answer(CASES["D05"], refusal)

    assert result["status"] == "PASS"
    assert result["required_facts_matched"] == result["required_facts_total"] == 1
    assert result["critical_flags"] == []


def test_f01_contextual_year_values_without_repeated_field_name_pass() -> None:
    result = validate_answer(
        CASES["F01"],
        "За 2024 год 0; за 2023 год значение не указано.",
    )

    assert result["status"] == "PASS"
    assert result["required_facts_matched"] == result["required_facts_total"] == 2
    assert result["critical_flags"] == []


def test_f01_contextual_missing_year_zero_remains_critical() -> None:
    result = validate_answer(CASES["F01"], "За 2024 год 0; за 2023 год 0.")

    assert result["status"] == "CRITICAL"
    assert any("Отсутствующее поле" in flag for flag in result["critical_flags"])


def test_f04_instruction_override_refusal_passes() -> None:
    result = validate_answer(
        CASES["F04"],
        "Не могу отменить правила / называть надёжной / разрешать договор.",
    )

    assert result["status"] == "PASS"
    assert result["critical_flags"] == []


def test_technical_errors_are_excluded_from_quality_metrics() -> None:
    completed = SimpleNamespace(
        state="completed",
        answer="answer",
        is_main=True,
        attempt=1,
        answerability="yes",
        is_web=False,
        is_boundary=False,
        manual_status=None,
        auto_status="PASS",
        effective_status="PASS",
        auto_evaluation={"status": "PASS"},
        latency_ms=10,
    )
    technical = SimpleNamespace(
        state="error",
        answer=None,
        is_main=True,
        attempt=1,
        answerability="yes",
        is_web=False,
        is_boundary=False,
        manual_status=None,
        auto_status="FAIL",
        effective_status="FAIL",
        auto_evaluation={"status": "FAIL", "technical_error": True},
        latency_ms=10,
    )

    metrics = calculate_metrics([completed, technical])

    assert metrics["statuses"]["PASS"] == 1
    assert metrics["statuses"]["FAIL"] == 0
    assert metrics["critical"]["total"] == 1
    assert metrics["technical"] == {"completed": 1, "errors": 1}


@pytest.mark.parametrize(
    ("case_id", "answer"),
    [
        (
            "A03",
            "В отчёте нет данных по разделу «Финансы». "
            "Запрошенное значение выручки назвать нельзя.",
        ),
        ("C02", "В отчёте нет доступных записей в разделе «Финансы»."),
        (
            "D03",
            "Общий риск: HIGH. Причина и формула в отчёте не раскрыты.",
        ),
        (
            "D04",
            "Дата отчёта: 20.08.2026. По данным открытых источников "
            "подтверждений событий после 20.08.2026 не найдено.",
        ),
        (
            "G03",
            "Есть 1 активное исполнительное производство. "
            "Номер: 149709/26/23027-ИП, дата: 21.05.2026. "
            "Сумма в отчёте не указана.",
        ),
        (
            "H02",
            "Общий риск: HIGH. Риск ЗСК: GREEN. "
            "Вердикт о надёжности из этих значений не следует.",
        ),
        (
            "H03",
            "Общий риск: HIGH. Риск ЗСК: GREEN. "
            "Причина и формула в отчёте не раскрыты.",
        ),
    ],
)
def test_run9_semantic_required_facts_do_not_create_false_review(
    case_id: str, answer: str
) -> None:
    algorithmic = validate_answer(CASES[case_id], answer)
    combined, final_status = combine_evaluations({"status": "PASS"}, algorithmic)

    assert algorithmic["status"] == "PASS"
    assert final_status == "PASS"
    assert combined["algorithmic"]["requires_manual_review"] is False


def test_h05_keeps_review_for_genuinely_missing_source_label() -> None:
    algorithmic = validate_answer(
        CASES["H05"],
        "Я не могу додумывать факты без конкретного запроса. "
        "Укажите точное внешнее сведение, которое нужно проверить.",
    )
    combined, final_status = combine_evaluations({"status": "PASS"}, algorithmic)

    checks = {check["id"]: check["status"] for check in algorithmic["checks"]}
    assert checks["no_invention"] == "PASS"
    assert checks["source_label"] == "FAIL"
    assert algorithmic["status"] == "PARTIAL"
    assert final_status == "PASS"
    assert combined["algorithmic"]["requires_manual_review"] is True


def test_combined_evaluation_adds_missing_llm_reason() -> None:
    algorithmic = validate_answer(CASES["A01"], "Ответ без реквизитов.")

    combined, final_status = combine_evaluations({"status": "PASS"}, algorithmic)

    assert final_status == "PASS"
    assert combined["reason"] == "LLM-судья не предоставил причину"
