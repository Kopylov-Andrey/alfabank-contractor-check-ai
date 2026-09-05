from __future__ import annotations

from collections import defaultdict
from statistics import mean, median
from typing import Iterable

from .database import Result


def _pct(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator * 100, 1) if denominator else None


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * fraction + 0.999999)))
    return round(ordered[index], 1)


def calculate_metrics(results: Iterable[Result]) -> dict:
    all_rows = list(results)
    rows = [row for row in all_rows if row.state in {"completed", "error"}]
    scored = [row for row in rows if row.answer is not None]
    main = [row for row in scored if row.is_main and row.attempt == 1]
    answerable = [row for row in main if row.answerability == "yes"]
    web = [row for row in scored if row.is_web]

    status_counts = {name: 0 for name in ("PASS", "PARTIAL", "FAIL", "CRITICAL", "UNREVIEWED")}
    for row in scored:
        status_counts[row.effective_status or "UNREVIEWED"] += 1

    main_pass = sum(row.effective_status == "PASS" for row in main)
    factual = sum(bool((row.auto_evaluation or {}).get("factual_correct")) for row in answerable)
    useful = sum(bool((row.auto_evaluation or {}).get("useful")) for row in answerable)
    false_refusals = sum(bool((row.auto_evaluation or {}).get("false_refusal")) for row in answerable)
    critical = sum(row.effective_status == "CRITICAL" for row in scored)

    fact_total = sum(int((row.auto_evaluation or {}).get("required_facts_total", 0)) for row in answerable)
    fact_hit = sum(int((row.auto_evaluation or {}).get("required_facts_matched", 0)) for row in answerable)
    claims_total = sum(int((row.auto_evaluation or {}).get("claims_total", 0)) for row in answerable)
    claims_sourced = sum(int((row.auto_evaluation or {}).get("claims_with_source", 0)) for row in answerable)

    boundary: dict[str, list[Result]] = defaultdict(list)
    for row in scored:
        if row.is_boundary:
            boundary[row.base_case_id].append(row)
    stable_boundary = sum(
        len(group) == 3 and all(item.effective_status in {"PASS", "PARTIAL"} for item in group)
        for group in boundary.values()
    )
    actual_web = [row for row in web if (row.auto_evaluation or {}).get("web_search_used")]
    labeled_web = sum(
        bool((row.auto_evaluation or {}).get("web_search_labeled_correctly")) for row in actual_web
    )

    latencies = [row.latency_ms for row in rows if row.latency_ms is not None]
    completed = sum(row.state == "completed" for row in rows)
    total = len(rows)

    metrics = {
        "progress": {"completed": total, "total": len(all_rows), "percent": _pct(total, len(all_rows))},
        "statuses": status_counts,
        "gtsr": {"value": main_pass, "total": 40, "percent": _pct(main_pass, 40), "pass": main_pass >= 34},
        "factual_correctness": {"value": factual, "total": len(answerable), "percent": _pct(factual, len(answerable)), "pass": factual >= 29},
        "completeness": {"value": fact_hit, "total": fact_total, "percent": _pct(fact_hit, fact_total), "pass": bool(fact_total) and fact_hit / fact_total >= .9},
        "source_coverage": {"value": claims_sourced, "total": claims_total, "percent": _pct(claims_sourced, claims_total), "pass": bool(claims_total) and claims_sourced / claims_total >= .95},
        "usefulness": {"value": useful, "total": len(answerable), "percent": _pct(useful, len(answerable)), "pass": useful >= 26},
        "false_refusals": {"value": false_refusals, "total": len(answerable), "percent": _pct(false_refusals, len(answerable)), "pass": false_refusals <= 3},
        "stable_boundary": {"value": stable_boundary, "total": 8, "percent": _pct(stable_boundary, 8), "pass": stable_boundary >= 7},
        "web_labeling": {"value": labeled_web, "total": len(actual_web), "percent": _pct(labeled_web, len(actual_web)), "pass": bool(actual_web) and labeled_web == len(actual_web)},
        "critical": {"value": critical, "total": len(scored), "pass": critical == 0},
        "technical": {"completed": completed, "errors": total - completed},
        "latency": {
            "mean_ms": round(mean(latencies), 1) if latencies else None,
            "median_ms": round(median(latencies), 1) if latencies else None,
            "p95_ms": percentile(latencies, .95),
            "max_ms": round(max(latencies), 1) if latencies else None,
        },
    }
    gates = [
        metrics[key]["pass"]
        for key in (
            "gtsr", "factual_correctness", "completeness", "source_coverage",
            "usefulness", "false_refusals", "stable_boundary", "web_labeling", "critical",
        )
    ]
    is_full_suite = len(all_rows) == 59
    metrics["release_gate"] = "PASS" if is_full_suite and total == 59 and all(gates) else ("FAIL" if is_full_suite and total == 59 else "PENDING")
    return metrics
