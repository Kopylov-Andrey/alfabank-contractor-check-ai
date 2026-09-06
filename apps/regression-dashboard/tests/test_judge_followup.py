from app.algorithmic_validation import combine_evaluations
from app.evaluation import parse_judge_response
from app.judge_models import public_profiles


def test_llm_manual_review_is_not_lost_when_algorithm_agrees():
    combined, status = combine_evaluations(
        {"status":"PARTIAL", "reason":"нужна проверка", "requires_manual_review":True},
        {"status":"PARTIAL", "reason":"согласен", "requires_manual_review":False},
    )
    assert status == "PARTIAL"
    assert combined["requires_manual_review"] is True


def test_contour_disagreement_requires_review():
    combined, _ = combine_evaluations(
        {"status":"PASS", "reason":"ok", "requires_manual_review":False},
        {"status":"PARTIAL", "reason":"gap", "requires_manual_review":False},
    )
    assert combined["requires_manual_review"] is True


def test_profiles_include_fast_glm_but_only_configured_models_are_available():
    # Test that profiles correctly mark availability based on allowlist
    profiles = {item["model_id"]: item for item in public_profiles(("gpt-5.6-luna",))}
    assert profiles["gpt-5.6-luna"]["available"] is True
    assert profiles["gpt-5.6-luna"]["tier"] == "fast"
    # Other models from PROFILES are shown but marked as unavailable
    assert profiles["gpt-5.6-terra"]["available"] is False
    assert profiles["gpt-5.6-sol"]["available"] is False
