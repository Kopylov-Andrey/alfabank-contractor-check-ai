# Архитектура развёрнутого MVP

**Статус:** финальная версия к защите  
**Дата:** 7 сентября 2026 года

## 1. End-to-end путь

```text
Browser
  -> Yandex Object Storage static website
     contractor-check-agent-demo.website.yandexcloud.net
  -> Cloud Function proxy
     contractor-agent-demo-api
  -> Yandex AI Studio Responses API
     saved agent: contractor-check-agent
  -> MCP server: contractor-check-mcp
     -> get-report-by-inn
     -> search-contractors
     -> compare-contractors
  -> Object Storage: contractor-reports/reports_by_inn.json

Дополнительный инструмент агента: Web Search.
```

## 2. Saved AI Studio agent

| Параметр | Значение |
|---|---|
| Agent | `contractor-check-agent` |
| Model | `Qwen3.6-35B` |
| Temperature | `0` |
| Max output tokens | `12000` |
| MCP approval | `never` |
| Web Search context size | `medium` |

Агент получает системный prompt из сохранённой конфигурации AI Studio. Web Search подключён отдельно от MCP и используется по правилам production prompt.

## 3. MCP server

`contractor-check-mcp` работает через HTTP/SSE и предоставляет три инструмента.

### `get-report-by-inn`

- runtime: Python 3.12;
- читает `reports_by_inn.json` из Object Storage;
- принимает ИНН из 10 или 12 цифр;
- поддерживает `full`, `compact` и `sections` projections;
- сохраняет семантическое различие между отсутствующим полем, `null`, пустым массивом и значением.

### `search-contractors`

Выполняет нормализованный поиск по названиям, адресу и видам деятельности и возвращает до 20 релевантных совпадений.

### `compare-contractors`

Принимает 2–10 ИНН и возвращает данные по всем компаниям одним MCP-вызовом с тем же projection-контрактом.

## 4. Demo API proxy

`contractor-agent-demo-api` связывает публичный интерфейс с saved agent.

Основные функции:

- принимает `POST {"message": "...", "previous_response_id": "..."}`;
- использует `X-Demo-Token`;
- хранит Yandex API key только на серверной стороне;
- валидирует ИНН перед первым запросом;
- возвращает финальный текст, HTTPS citations, response id, latency и evidence whitelist;
- не передаёт в браузер raw MCP payload, reasoning и секреты;
- проверяет origin публичного сайта.

## 5. Evidence panel

Для первого ответа по новому отчёту demo API возвращает ограниченный набор точных оснований. UI показывает:

- название факта;
- поле отчёта;
- точное значение;
- дату отчёта;
- JSON-фрагмент.

Перед возвратом evidence proxy сверяет ИНН и проецирует только разрешённые значения.

## 6. Product UI

Публичный интерфейс размещён в Yandex Object Storage:

**https://contractor-check-agent-demo.website.yandexcloud.net/**

UI реализует основной пользовательский сценарий: запрос → сводка → evidence → follow-up → Web Search или сравнение при необходимости.

## 7. Данные

Приватный набор контрагентов хранится в Yandex Object Storage в `reports_by_inn.json`. Клиентская часть не получает прямого доступа к исходному dataset.

## 8. Безопасность

В серверном контуре остаются:

- Yandex API keys;
- Lockbox values;
- service-account credentials;
- Object Storage credentials;
- raw MCP payload;
- служебные данные выполнения агента.

Публичный браузер работает только через demo API proxy.

## 9. Контур качества

Отдельный regression dashboard обращается к тому же saved agent и выполняет frozen suite из 59 scored cases.

```text
Regression dashboard
  -> Yandex AI Studio agent
  -> LLM judge / KAILA
  -> deterministic validator
  -> manual review / override
  -> PostgreSQL/SQLite
```

Финальный release gate пройден. Подробные метрики описаны в [`03_hypotheses_evaluation_and_pilot.md`](03_hypotheses_evaluation_and_pilot.md).
