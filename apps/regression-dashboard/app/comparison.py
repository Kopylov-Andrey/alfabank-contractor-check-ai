from collections import Counter

from .metrics import is_technical_error
from .provenance import public_provenance

RANK = {"CRITICAL": 0, "FAIL": 1, "PARTIAL": 2, "PASS": 3}


def compare_runs(a, b):
    """Compare a baseline with a candidate; absent/error answers have no quality delta."""
    pa, pb = public_provenance(a), public_provenance(b)
    dimensions = [
        ("Модель судьи", a.judge_model, b.judge_model),
        ("Метка промпта (пользовательская)", a.prompt_version or None, b.prompt_version or None),
        ("Набор тестов", pa.get("suite_sha256"), pb.get("suite_sha256")),
        ("Оценщик", pa.get("evaluator_sha256"), pb.get("evaluator_sha256")),
        ("Расчёт метрик", pa.get("metrics_version"), pb.get("metrics_version")),
        ("Снимок отчётов", pa.get("report_data_version"), pb.get("report_data_version")),
    ]
    warnings = []
    for label, x, y in dimensions:
        if x is None or y is None or (label.startswith("Метка") and (pa["prompt_source"] == "unknown" or pb["prompt_source"] == "unknown")):
            warnings.append(f"{label}: версия неизвестна; сопоставимость ограничена.")
        elif x != y:
            warnings.append(f"{label}: значения различаются.")
    warnings.append("Метка промпта не подтверждает состояние внешнего агента. Изменение статуса не доказывает влияние промпта.")
    if any(run.status != "completed" or any(row.state != "completed" or is_technical_error(row) for row in run.results) for run in (a, b)):
        warnings.append("Есть неполные прогоны или технические ошибки; такие кейсы не имеют изменения качества.")
    key = lambda row: (row.case_id, row.attempt)
    left, right = {key(row): row for row in a.results}, {key(row): row for row in b.results}
    if len(left) != len(a.results) or len(right) != len(b.results):
        raise ValueError("Неоднозначная идентичность кейсов: повторяется case_id + attempt")

    def snapshot(row):
        if row is None:
            return None
        evaluation = row.auto_evaluation or {}
        return {"id": row.id, "llm": None if is_technical_error(row) else evaluation.get("status") or (row.auto_status if not evaluation.get("algorithmic") else None),
                "algorithmic": evaluation.get("algorithmic", {}).get("status"),
                "combined": row.auto_status, "manual": row.manual_status,
                "effective": row.effective_status, "technical_error": row.technical_error,
                "state": row.state}

    rows = []
    for case_id, attempt in sorted(left.keys() | right.keys()):
        x, y = left.get((case_id, attempt)), right.get((case_id, attempt))
        reason = None
        if x is None or y is None:
            reason = "Кейс отсутствует в одном из прогонов"
        elif is_technical_error(x) or is_technical_error(y):
            reason = "Техническая ошибка"
        elif x.state != "completed" or y.state != "completed" or x.effective_status not in RANK or y.effective_status not in RANK:
            reason = "Нет завершённой оценки"
        elif any(getattr(x, field) != getattr(y, field) for field in ("question", "expected", "evidence", "forbidden", "critical_if", "company_code")):
            reason = "Определение кейса изменилось"
        change = "unavailable"
        if reason is None:
            delta = RANK[y.effective_status] - RANK[x.effective_status]
            change = "improved" if delta > 0 else "regressed" if delta < 0 else "unchanged"
        rows.append({"case_id": case_id, "attempt": attempt, "question": (x or y).question,
                     "baseline": snapshot(x), "candidate": snapshot(y), "change": change, "reason": reason})
    return {"baseline_id": a.id, "candidate_id": b.id,
            "dimensions": [{"label": label, "baseline": x, "candidate": y} for label, x, y in dimensions],
            "warnings": warnings, "counts": dict(Counter(row["change"] for row in rows)), "rows": rows}
