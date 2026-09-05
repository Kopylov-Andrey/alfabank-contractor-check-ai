from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from .database import Result, Run
from .metrics import calculate_metrics


def generate_csv(run: Run) -> str:
    """Generate CSV export of all results in a run."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "case_id",
        "category",
        "company_code",
        "question",
        "answer",
        "llm_status",
        "algorithmic_status",
        "combined_status",
        "manual_status",
        "latency_ms",
        "factual_correct",
        "useful",
        "false_refusal",
        "llm_reason",
        "algorithmic_reason",
        "required_facts_matched",
        "required_facts_total",
        "forbidden_matches",
        "critical_flags",
        "critical_checks_inconclusive",
        "requires_manual_review",
        "technical_error",
    ])

    # Data rows
    for row in run.results:
        evaluation = row.auto_evaluation or {}
        algorithmic = evaluation.get("algorithmic", {})

        llm_status = evaluation.get("status", "")
        if not llm_status and not algorithmic:
            llm_status = row.auto_status or ""

        algorithmic_status = algorithmic.get("status", "")

        writer.writerow([
            row.case_id,
            row.category,
            row.company_code,
            row.question,
            row.answer or "",
            llm_status,
            algorithmic_status,
            row.effective_status or "",
            row.manual_status or "",
            row.latency_ms or "",
            evaluation.get("factual_correct", ""),
            evaluation.get("useful", ""),
            evaluation.get("false_refusal", ""),
            evaluation.get("reason", ""),
            algorithmic.get("reason", ""),
            algorithmic.get("required_facts_matched", ""),
            algorithmic.get("required_facts_total", ""),
            "; ".join(algorithmic.get("forbidden_matches", [])),
            "; ".join(algorithmic.get("critical_flags", [])),
            algorithmic.get("critical_checks_inconclusive", ""),
            algorithmic.get("requires_manual_review", ""),
            row.technical_error or "",
        ])

    return output.getvalue()


def generate_html_report(run: Run) -> str:
    """Generate HTML report for PDF conversion."""
    metrics = calculate_metrics(run.results)

    # Status colors
    status_colors = {
        "PASS": "#4ee28a",
        "PARTIAL": "#ffbd59",
        "FAIL": "#ff6c62",
        "CRITICAL": "#ff3459",
        "UNREVIEWED": "#64748b",
    }

    def status_badge(status: str) -> str:
        color = status_colors.get(status, "#64748b")
        return f'<span style="display:inline-block;padding:4px 8px;border-radius:6px;background:{color}22;color:{color};font-size:10px;font-weight:800;border:1px solid {color}44">{status}</span>'

    def metric_row(label: str, value: Any, total: Any = None, passed: bool | None = None) -> str:
        value_str = f"{value}/{total}" if total is not None else str(value)
        status_icon = "✓" if passed is True else "✗" if passed is False else "—"
        status_color = "#4ee28a" if passed is True else "#ff6c62" if passed is False else "#64748b"
        return f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid #1e293b">{label}</td>
            <td style="padding:8px;border-bottom:1px solid #1e293b;text-align:right;font-weight:700">{value_str}</td>
            <td style="padding:8px;border-bottom:1px solid #1e293b;text-align:center;color:{status_color};font-weight:800">{status_icon}</td>
        </tr>
        """

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <title>Regression Report — {run.name}</title>
    <style>
        @page {{ size: A4; margin: 1.5cm; }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0f1a; color: #e2e8f0; font-size: 11px; line-height: 1.5; }}
        .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1 {{ font-size: 24px; margin-bottom: 8px; color: #fff; }}
        h2 {{ font-size: 18px; margin: 24px 0 12px; color: #fff; border-bottom: 2px solid #1e293b; padding-bottom: 6px; }}
        h3 {{ font-size: 14px; margin: 16px 0 8px; color: #cbd5e1; }}
        .header {{ margin-bottom: 32px; padding-bottom: 16px; border-bottom: 2px solid #1e293b; }}
        .meta {{ color: #64748b; font-size: 10px; margin-top: 4px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 12px 0; background: #0e1722; border-radius: 8px; overflow: hidden; }}
        th {{ background: #1e293b; padding: 10px 8px; text-align: left; font-weight: 800; font-size: 10px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; }}
        td {{ padding: 8px; border-bottom: 1px solid #1e293b; }}
        .status-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 16px 0; }}
        .status-card {{ background: #0e1722; border: 1px solid #1e293b; border-radius: 8px; padding: 12px; }}
        .status-card strong {{ display: block; font-size: 28px; margin: 8px 0; }}
        .status-card small {{ color: #64748b; font-size: 9px; }}
        .gate-status {{ display: inline-block; padding: 8px 16px; border-radius: 8px; font-weight: 800; font-size: 14px; margin: 8px 0; }}
        .gate-pass {{ background: #4ee28a22; color: #4ee28a; border: 1px solid #4ee28a44; }}
        .gate-fail {{ background: #ff6c6222; color: #ff6c62; border: 1px solid #ff6c6244; }}
        .gate-pending {{ background: #64748b22; color: #64748b; border: 1px solid #64748b44; }}
        .footer {{ margin-top: 32px; padding-top: 16px; border-top: 1px solid #1e293b; color: #64748b; font-size: 9px; text-align: center; }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>Regression Report</h1>
        <div class="meta">{run.name} · {run.judge_model} · Scope: {run.scope}</div>
        <div class="meta">Generated: {now}</div>
    </div>

    <h2>Release Gate</h2>
    <div class="gate-status gate-{metrics['release_gate'].lower()}">{metrics['release_gate']}</div>
    <div class="meta">Progress: {metrics['progress']['completed']}/{metrics['progress']['total']} ({metrics['progress']['percent'] or 0}%)</div>

    <div class="status-grid">
        <div class="status-card">
            <small>Main GTSR</small>
            <strong>{metrics['gtsr']['value']}</strong>
            <small>/ 40 (≥34 required)</small>
        </div>
        <div class="status-card">
            <small>LLM Critical</small>
            <strong>{metrics['critical']['value']}</strong>
            <small>must be 0</small>
        </div>
        <div class="status-card">
            <small>Combined Critical</small>
            <strong>{metrics['combined']['critical']['value']}</strong>
            <small>must be 0</small>
        </div>
    </div>

    <h2>Quality Metrics</h2>
    <table>
        <thead>
            <tr>
                <th>Metric</th>
                <th style="text-align:right">Value</th>
                <th style="text-align:center">Status</th>
            </tr>
        </thead>
        <tbody>
            {metric_row("Factual Correctness", f"{metrics['factual_correctness']['percent'] or 0:.1f}%", None, metrics['factual_correctness']['pass'])}
            {metric_row("Completeness", f"{metrics['completeness']['percent'] or 0:.1f}%", None, metrics['completeness']['pass'])}
            {metric_row("Source Coverage", f"{metrics['source_coverage']['percent'] or 0:.1f}%", None, metrics['source_coverage']['pass'])}
            {metric_row("Usefulness", f"{metrics['usefulness']['percent'] or 0:.1f}%", None, metrics['usefulness']['pass'])}
            {metric_row("False Refusals", metrics['false_refusals']['value'], metrics['false_refusals']['total'], metrics['false_refusals']['pass'])}
            {metric_row("Stable Boundary", metrics['stable_boundary']['value'], metrics['stable_boundary']['total'], metrics['stable_boundary']['pass'])}
            {metric_row("Web Labeling", metrics['web_labeling']['value'], metrics['web_labeling']['total'], metrics['web_labeling']['pass'])}
        </tbody>
    </table>

    <h2>Status Distribution</h2>
    <table>
        <thead>
            <tr>
                <th>LLM Status</th>
                <th style="text-align:right">Count</th>
                <th>Algorithmic Status</th>
                <th style="text-align:right">Count</th>
            </tr>
        </thead>
        <tbody>
"""

    llm_statuses = ["PASS", "PARTIAL", "FAIL", "CRITICAL", "UNREVIEWED"]
    alg_statuses = metrics['algorithmic']['statuses']

    for i, status in enumerate(llm_statuses):
        llm_count = metrics['statuses'].get(status, 0)
        alg_status = ["PASS", "PARTIAL", "FAIL", "CRITICAL"][i] if i < 4 else ""
        alg_count = alg_statuses.get(alg_status, 0) if alg_status else ""
        html += f"""
            <tr>
                <td style="padding:8px;border-bottom:1px solid #1e293b">{status_badge(status)}</td>
                <td style="padding:8px;border-bottom:1px solid #1e293b;text-align:right;font-weight:700">{llm_count}</td>
                <td style="padding:8px;border-bottom:1px solid #1e293b">{status_badge(alg_status) if alg_status else ''}</td>
                <td style="padding:8px;border-bottom:1px solid #1e293b;text-align:right;font-weight:700">{alg_count}</td>
            </tr>
"""

    html += """
        </tbody>
    </table>

    <h2>Algorithmic Validation</h2>
    <table>
        <tbody>
"""

    alg = metrics['algorithmic']
    html += metric_row("Evaluated Cases", alg['evaluated'], alg['total'], None)
    html += metric_row("Required Facts Coverage", f"{alg['required_fact_coverage']['percent'] or 0:.1f}%", None, None)
    html += metric_row("Forbidden Matches", alg['forbidden_matches']['value'], f"in {alg['forbidden_matches']['cases']} cases", None)
    html += metric_row("Algorithmic CRITICAL", alg['critical']['value'], alg['critical']['total'], alg['critical']['value'] == 0)
    html += metric_row("Requires Manual Review", alg['manual_review']['value'], alg['manual_review']['total'], None)

    html += f"""
        </tbody>
    </table>

    <h2>Performance</h2>
    <table>
        <tbody>
            {metric_row("Mean Latency", f"{metrics['latency']['mean_ms'] or 0:.0f} ms", None, None)}
            {metric_row("Median Latency", f"{metrics['latency']['median_ms'] or 0:.0f} ms", None, None)}
            {metric_row("p95 Latency", f"{metrics['latency']['p95_ms'] or 0:.0f} ms", None, None)}
            {metric_row("Max Latency", f"{metrics['latency']['max_ms'] or 0:.0f} ms", None, None)}
        </tbody>
    </table>

    <h2>Technical Summary</h2>
    <table>
        <tbody>
            {metric_row("Completed", metrics['technical']['completed'], metrics['progress']['total'], None)}
            {metric_row("Errors", metrics['technical']['errors'], None, metrics['technical']['errors'] == 0)}
        </tbody>
    </table>

    <div class="footer">
        Agent Regression Lab · Контрагент по фактам<br>
        Report generated: {now}
    </div>
</div>
</body>
</html>
"""

    return html
