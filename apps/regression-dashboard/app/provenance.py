from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

METRICS_VERSION = "quality-v2"


def capture_provenance(suite, prompt_label: str, judge_model: str | None = None) -> dict:
    from .evaluation import JUDGE_PROMPT_VERSION, JUDGE_SYSTEM
    root = Path(__file__).parent
    def digest(paths):
        result = hashlib.sha256()
        for path in paths:
            result.update(path.encode())
            result.update((root / path).read_bytes().replace(b"\r\n", b"\n"))
        return result.hexdigest()
    result = {
        "prompt_source": "user_label" if prompt_label else "unknown",
        "agent_prompt_verified": False,
        "judge_prompt_version": JUDGE_PROMPT_VERSION,
        "judge_prompt_sha256": hashlib.sha256(JUDGE_SYSTEM.encode()).hexdigest(),
        "evaluator_sha256": digest(["evaluation.py", "algorithmic_validation.py", "data/algorithmic_rules.json"]),
        "suite_sha256": hashlib.sha256(json.dumps([asdict(case) for case in suite], ensure_ascii=False,
                                                  sort_keys=True).encode()).hexdigest(),
        "metrics_version": METRICS_VERSION,
        "metrics_sha256": digest(["metrics.py"]),
        "report_data_version": None,
    }
    if judge_model:
        from .judge_models import profile_for
        result["judge_model_profile"] = asdict(profile_for(judge_model))
    return result


def public_provenance(run) -> dict:
    saved = getattr(run, "provenance", None) or {}
    return {"prompt_source": "unknown", "agent_prompt_verified": False,
            "metrics_version": "legacy-v1", **saved}
