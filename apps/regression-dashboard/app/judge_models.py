"""Simple judge model profiles for CAILA adapter.

IMPORTANT: Only include models that are verified to work with your CAILA account.
Model availability depends on your pricing plan and account configuration.

To test a new model:
1. Try it in a run first
2. If it works without HTTP 400, add it to JUDGE_MODELS in .env
3. The profile will be auto-generated if not in PROFILES below
"""
from __future__ import annotations
from dataclasses import asdict, dataclass

@dataclass(frozen=True)
class JudgeModelProfile:
    model_id: str
    provider: str
    display_name: str
    tier: str
    supports_chat_completions: bool = True

# VERIFIED working models - add your own as you test them
PROFILES = {
    # OpenAI GPT-5.6 series - VERIFIED WORKING
    "gpt-5.6-luna": JudgeModelProfile(
        "gpt-5.6-luna", "OpenAI", "GPT-5.6 Luna", "fast"
    ),
    "gpt-5.6-terra": JudgeModelProfile(
        "gpt-5.6-terra", "OpenAI", "GPT-5.6 Terra", "standard"
    ),
    "gpt-5.6-sol": JudgeModelProfile(
        "gpt-5.6-sol", "OpenAI", "GPT-5.6 Sol", "premium"
    ),
    # Add more models here after you verify they work with your CAILA account
    # Example:
    # "gpt-4.1-mini": JudgeModelProfile(
    #     "gpt-4.1-mini", "OpenAI", "GPT-4.1 Mini", "fast"
    # ),
}

def profile_for(model_id: str) -> JudgeModelProfile:
    """Return profile for model_id; create default profile if not found."""
    return PROFILES.get(
        model_id,
        JudgeModelProfile(model_id, "configured", model_id, "standard")
    )

def public_profiles(allowed: tuple[str, ...]) -> list[dict]:
    """Return list of all known profiles for frontend."""
    # Show all known models, mark which are in the allowlist
    return [
        {
            **asdict(profile_for(model_id)),
            "available": model_id in allowed,
        }
        for model_id in PROFILES.keys()
    ]
