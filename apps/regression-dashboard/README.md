# Agent Regression Lab

Автоматизированный dashboard для воспроизводимой проверки `contractor-check-agent`.

## Что проверяется

Полный regression suite:

- 40 основных сценариев;
- 16 повторов 8 boundary-сценариев;
- 3 Web Search сценария;
- 59 оцениваемых ответов;
- 27 независимых диалогов;
- 86 вызовов агента вместе с setup-turns.

## Архитектура

```text
Public dashboard
  -> FastAPI backend
  -> Yandex Responses API / contractor-check-agent
  -> LLM judge via KAILA
  -> deterministic validator
  -> PostgreSQL / SQLite
```

Dashboard поддерживает:

- запуск полного, main и boundary scope;
- LLM judge с `PASS / PARTIAL / FAIL / CRITICAL`;
- deterministic validation точных фактов и критических условий;
- manual review / override;
- latency, usage, citations и tool calls;
- сравнение прогонов;
- CSV export;
- HTML report для печати в PDF;
- PostgreSQL в облаке и SQLite локально.

## Release gate

| Метрика | Порог |
|---|---:|
| GTSR | ≥34/40 |
| Factual correctness | ≥90% |
| Completeness | ≥90% |
| Source coverage | ≥95% |
| Usefulness | ≥80% |
| False refusals | ≤3 |
| Stable boundary | ≥7/8 |
| Web labeling | 100% |
| LLM CRITICAL | 0 |
| Combined CRITICAL | 0 |

Финальный suite завершён: 59/59, 40/40 main PASS, 8/8 stable boundary, 100% Web labeling, 0 effective CRITICAL. Release gate — PASS.

## Быстрый запуск

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env            # Windows: copy .env.example .env
```

Заполните `.env` и запустите:

```bash
uvicorn app.main:app --env-file .env --workers 1
```

Локально интерфейс доступен на `http://localhost:8000`.

## Основные переменные

- `YANDEX_API_KEY` — доступ к тестируемому агенту;
- `YANDEX_AGENT_ID` — saved agent ID;
- `MCP_SERVER_URL` — MCP Gateway;
- `JUDGE_API_KEY` — доступ к KAILA;
- `JUDGE_BASE_URL` — OpenAI-compatible endpoint;
- `JUDGE_MODELS` — allowlist моделей судьи;
- `DEFAULT_JUDGE_MODEL` — модель по умолчанию;
- `DATABASE_URL` — PostgreSQL или SQLite;
- `ADMIN_TOKEN` — защита управляющих действий.

## LLM judge

Judge получает:

- вопрос;
- expected facts;
- обязательные основания;
- запрещённые утверждения;
- условие CRITICAL;
- ответ агента;
- citations;
- tool calls.

Результат включает статус и отдельные признаки factual correctness, completeness, source coverage, usefulness, false refusal и Web Search behavior.

## Deterministic validator

`app/data/algorithmic_rules.json` содержит машинные правила для проверки:

- ИНН и компании;
- дат и сумм;
- уровней общего риска и ЗСК;
- обязательных фактов;
- запрещённых формулировок;
- критических условий.

LLM judge и deterministic validator работают независимо. Спорные расхождения могут быть отмечены для manual review.

## Экспорт

### CSV

`GET /api/runs/{run_id}/export/csv`

Содержит вопросы, ответы, статусы, judge/algorithmic детали, версии и latency.

### HTML report

`GET /api/runs/{run_id}/export/pdf`

Возвращает HTML-отчёт с release gate, quality metrics и performance, подготовленный для печати в PDF.

## Проверки репозитория

```bash
pytest -q
node --check app/static/app.js
python -m compileall -q app
node tests/browser-smoke.mjs
```

## Связанные документы

- [`../../docs/03_hypotheses_evaluation_and_pilot.md`](../../docs/03_hypotheses_evaluation_and_pilot.md) — критерии и финальный результат;
- [`../../docs/04_ai_evaluation_test_cases.md`](../../docs/04_ai_evaluation_test_cases.md) — человекочитаемая спецификация suite;
- [`app/data/test_cases.json`](app/data/test_cases.json) — канонические машинные test cases;
- [`HOW_TO_ADD_MODELS.md`](HOW_TO_ADD_MODELS.md) — конфигурация моделей судьи;
- [`DEPLOYMENT.md`](DEPLOYMENT.md) — deployment dashboard.
