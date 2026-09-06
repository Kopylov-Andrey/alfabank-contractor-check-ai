from __future__ import annotations

import csv
import io
import json
from html import escape

from .database import Run
from .metrics import execution_summary, gate_explanation, is_technical_error, run_metrics
from .provenance import public_provenance


def _json(value):
    return json.dumps(value, ensure_ascii=False)


def _safe_cell(value):
    if isinstance(value, str):
        index = 0
        while index < len(value) and (value[index].isspace() or ord(value[index]) < 32 or value[index] == "\ufeff"):
            index += 1
        candidate = value[index:]
        if candidate.startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
            return "'" + value
    return value


def _export_rows(run):
    provenance, execution = public_provenance(run), execution_summary(run.results)
    incomplete = gate_explanation(run)["preliminary"]
    for row in run.results:
        evaluation = row.auto_evaluation or {}
        algorithmic = evaluation.get("algorithmic") or {}
        llm = evaluation.get("status") or (row.auto_status if not algorithmic else "")
        yield {
            "run_id": run.id, "run_name": run.name, "run_status": run.status,
            "cancel_requested": run.cancel_requested, "run_error": run.error or "",
            "run_created_at": str(run.created_at or ""), "run_finished_at": str(run.finished_at or ""),
            "processed": execution["processed"], "total": execution["total"],
            "evaluated": execution["evaluated"], "incomplete": incomplete,
            "judge_model": run.judge_model, "prompt_version": run.prompt_version or "Версия неизвестна",
            "prompt_source": provenance["prompt_source"], "agent_prompt_verified": provenance["agent_prompt_verified"],
            "evaluator_sha256": provenance.get("evaluator_sha256") or "Версия неизвестна",
            "suite_sha256": provenance.get("suite_sha256") or "Версия неизвестна",
            "metrics_version": provenance["metrics_version"], "provenance": _json(provenance),
            "case_id": row.case_id, "base_case_id": row.base_case_id, "attempt": row.attempt,
            "state": row.state, "category": row.category, "company_code": row.company_code,
            "question": row.question, "answer": row.answer or "", "expected": row.expected,
            "evidence": row.evidence, "forbidden": row.forbidden, "critical_if": row.critical_if,
            "llm_status": "" if is_technical_error(row) else llm or "",
            "algorithmic_status": algorithmic.get("status", ""),
            "combined_status": row.auto_status or "", "effective_status": row.effective_status or "",
            "manual_status": row.manual_status or "", "manual_comment": row.manual_comment or "",
            "latency_ms": row.latency_ms if row.latency_ms is not None else "",
            "factual_correct": evaluation.get("factual_correct", ""), "useful": evaluation.get("useful", ""),
            "false_refusal": evaluation.get("false_refusal", ""), "llm_reason": evaluation.get("reason", ""),
            "algorithmic_reason": algorithmic.get("reason", ""),
            "required_facts_matched": algorithmic.get("required_facts_matched", ""),
            "required_facts_total": algorithmic.get("required_facts_total", ""),
            "forbidden_matches": _json(algorithmic.get("forbidden_matches", [])),
            "critical_flags": _json(algorithmic.get("critical_flags", [])),
            "critical_checks_inconclusive": algorithmic.get("critical_checks_inconclusive", ""),
            "requires_manual_review": algorithmic.get("requires_manual_review", ""),
            "technical_error": row.technical_error or ("Техническая ошибка" if is_technical_error(row) else ""),
            "technical_error_kind": getattr(row, "technical_error_kind", None) or "",
            "citations": _json(row.citations or []), "evaluation": _json(evaluation),
        }


def generate_csv(run: Run) -> str:
    output = io.StringIO()
    output.write("\ufeff")
    rows = list(_export_rows(run)) or [{"run_id": run.id, "run_name": run.name, "run_status": run.status,
                                      "prompt_version": run.prompt_version or "Версия неизвестна",
                                      "provenance": _json(public_provenance(run))}]
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _safe_cell(value) for key, value in row.items()})
    return output.getvalue()


def generate_html_report(run: Run) -> str:
    metrics, execution, provenance = run_metrics(run), execution_summary(run.results), public_provenance(run)
    gate = gate_explanation(run, metrics)
    esc = lambda value: escape(str(value if value is not None else "Нет данных"))

    def metric_row(label, value):
        return f"<tr><th>{esc(label)}</th><td>{esc(value)}</td></tr>"

    def fraction(value):
        percentage = "Нет данных" if value.get("percent") is None else f"{value['percent']}%"
        return f"{percentage} · {value['value']}/{value['total']}"

    quality = "".join(metric_row(label, fraction(metrics[key])) for key, label in [
        ("gtsr", "GTSR · ≥34/40"), ("factual_correctness", "Факты · ≥29 ответов"),
        ("completeness", "Полнота · ≥90%"), ("source_coverage", "Источники · ≥95%"),
        ("usefulness", "Полезность · ≥26 ответов"), ("false_refusals", "Ложные отказы · ≤3"),
        ("stable_boundary", "Устойчивость · ≥7/8"), ("web_labeling", "Маркировка Web · 100%")])
    details = []
    for row in _export_rows(run):
        parts = [f"<article><h3>{esc(row['case_id'])} · повтор {row['attempt']}</h3>"]
        for label, key in [
            ("Вопрос", "question"), ("Ответ агента", "answer"), ("LLM", "llm_status"),
            ("Алгоритм", "algorithmic_status"), ("Combined", "combined_status"),
            ("Ручная оценка", "manual_status"), ("Итог", "effective_status"),
            ("Состояние", "state"), ("Техническая ошибка", "technical_error"),
            ("Причина LLM", "llm_reason"), ("Причина алгоритма", "algorithmic_reason"),
            ("Требуется ручная проверка", "requires_manual_review"),
            ("Критическая проверка не определена", "critical_checks_inconclusive"),
            ("Критические флаги", "critical_flags"), ("Комментарий", "manual_comment"),
            ("Ожидаемое поведение", "expected"), ("Основания", "evidence"),
            ("Источники", "citations"), ("Полная оценка", "evaluation")]:
            parts.append(f"<h4>{label}</h4><pre>{esc(row[key])}</pre>")
        details.append("".join(parts) + "</article>")
    legacy = "Исторический расчёт legacy-v1 сохранён: технические ошибки с ответом могли входить в quality-метрики." if provenance["metrics_version"] == "legacy-v1" else "quality-v2: технические ошибки исключены из качества; покрытие показано отдельно."
    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><title>Regression Report · #{run.id} · {esc(run.name)}</title>
<style>
@page {{size:A4;margin:15mm}} * {{box-sizing:border-box}} body {{font:14px/1.55 Arial,sans-serif;color:#202124;background:white;margin:0 auto;padding:28px;max-width:1000px}}
h1 {{font-size:26px}} h2 {{font-size:20px;border-bottom:2px solid #d92332;padding-bottom:8px;margin-top:28px}} h3 {{font-size:17px}}
p,pre,td {{overflow-wrap:anywhere}} pre {{white-space:pre-wrap;font:inherit;background:#f5f5f6;padding:12px}} table {{width:100%;border-collapse:collapse}}
th,td {{text-align:left;border-bottom:1px solid #ddd;padding:8px}} th {{font-weight:600}} article {{border-top:1px solid #aaa;margin-top:24px;padding-top:12px}}
.notice {{background:#fff4df;padding:14px}} .meta {{color:#54565b}} @media print {{body {{padding:0}} h2,h3,h4 {{break-after:avoid}} tr {{break-inside:avoid}}}}
</style></head><body>
<h1>Regression Report · #{run.id}</h1><p>{esc(run.name)}</p>
<p>Статус: {esc(run.status)} · Остановка запрошена: {esc(run.cancel_requested)} · Судья: {esc(run.judge_model)} · Набор: {esc(run.scope)}</p>
<p>Создан: {esc(run.created_at)} · Завершён: {esc(run.finished_at)}</p><p>{esc(run.error or '')}</p>
<p>Промпт: {esc(run.prompt_version or 'Версия неизвестна')} · Источник: {esc(provenance['prompt_source'])}. Установка на внешнем агенте не подтверждена.</p>
<h2>Release Gate</h2><p><b>{esc(metrics['release_gate'])}</b> · {'Предварительно; итоговая оценка недоступна' if gate['preliminary'] else 'Полный результат'}</p>
<ul>{''.join(f'<li>{esc(reason)}</li>' for reason in gate['reasons'])}</ul>
<p>Обработано {execution['processed']}/{execution['total']}; оценено {execution['evaluated']}/{execution['total']}; технических ошибок {execution['errors']}; без оценки {execution['unscored']}.</p>
<p class="notice">{esc(legacy)} GTSR: фиксированный знаменатель 40. LLM-метрики учитывают ручной статус по существующей политике.</p>
<h2>Quality Metrics</h2><table>{quality}</table>
<h2>Status Distribution</h2><table>{metric_row('LLM + ручная оценка', _json(metrics['statuses']))}{metric_row('Combined + ручная оценка', _json(metrics['combined']['statuses']))}</table>
<h2>Algorithmic Validation</h2><table>{metric_row('Алгоритмические статусы', _json(metrics['algorithmic']['statuses']))}{metric_row('Покрытие обязательных фактов', fraction(metrics['algorithmic']['required_fact_coverage']))}{metric_row('Алгоритмические CRITICAL, включая сохранённые при сбое судьи', execution['algorithmic_critical'])}{metric_row('Review flags / требуют проверки', f"{execution['review_flags']} / {execution['review_pending']}")}</table>
<h2>Скорость ответа</h2><table>{''.join(metric_row(label, f'{value} мс' if value is not None else 'Нет данных') for label, value in metrics['latency'].items())}</table>
<h2>Происхождение данных</h2><pre>{esc(_json(provenance))}</pre>
<h2>Результаты</h2>{''.join(details) or '<p>Нет результатов</p>'}
<p class="meta">Regression Lab · Хакатонный проект, не официальный банковский сервис. Отчёт / Печать в PDF: откройте HTML в браузере и выберите печать.</p>
</body></html>"""
