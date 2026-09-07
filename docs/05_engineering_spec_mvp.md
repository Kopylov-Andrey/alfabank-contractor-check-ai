# Техническая спецификация реализованного MVP «Контрагент — по фактам»

**Статус:** финальная версия к защите  
**Дата:** 7 сентября 2026 года  
**Команда:** Команда 2

## 1. Назначение

Документ фиксирует фактически развёрнутую архитектуру MVP и ключевые инженерные решения.

Продукт доступен как публичный веб-demo. Пользователь работает с интерфейсом, который через серверный proxy обращается к сохранённому агенту Yandex AI Studio. Агент использует MCP для работы с отчётами и Web Search для конкретных внешних вопросов.

## 2. Архитектура

```text
Browser
  -> Yandex Object Storage static website
  -> Cloud Function proxy: contractor-agent-demo-api
  -> Yandex AI Studio Responses API
     -> saved agent: contractor-check-agent
        -> MCP server: contractor-check-mcp
           -> get-report-by-inn
           -> search-contractors
           -> compare-contractors
        -> Web Search
  -> Object Storage: contractor-reports/reports_by_inn.json
```

Контур качества:

```text
Regression dashboard
  -> Yandex Responses API / тот же saved agent
  -> LLM judge через KAILA
  -> deterministic validator
  -> PostgreSQL/SQLite
  -> manual review / override
```

## 3. Конфигурация production-агента

| Параметр | Значение |
|---|---|
| Платформа | Yandex AI Studio / Agent Atelier |
| Агент | `contractor-check-agent` |
| Модель | `Qwen3.6-35B` |
| Temperature | `0` |
| Max output tokens | `12000` |
| MCP approval | `never` |
| Web Search | enabled |
| Search context size | `medium` |

Модель и системный prompt задаются конфигурацией AI Studio. API-ключ хранится на серверной стороне и не передаётся во frontend.

## 4. MCP-сервер

`contractor-check-mcp` предоставляет три инструмента.

### `get-report-by-inn`

- принимает ИНН из 10 или 12 цифр;
- получает один отчёт из `reports_by_inn.json`;
- поддерживает `full`, `compact` и `sections` projections;
- сохраняет различия между отсутствующим полем, `null`, пустым массивом и существующим значением.

### `search-contractors`

- выполняет нормализованный текстовый поиск;
- использует название, адрес и виды деятельности;
- возвращает до 20 совпадений с ИНН, названием, `riskLevel` и адресом.

### `compare-contractors`

- принимает `inn_list` из 2–10 ИНН;
- получает данные по всем указанным компаниям одним вызовом;
- использует те же projection modes, что и `get-report-by-inn`.

## 5. Web Search

Web Search подключён к агенту как отдельный инструмент и используется по правилам production prompt для конкретных внешних сведений: новости, санкции, сайт/адрес и события после даты отчёта.

Основные правила:

- Web Search не используется для определения ИНН;
- внешний факт явно отделяется от банковского отчёта;
- для событий после даты отчёта показывается `reportDate` как граница банковских данных;
- нерелевантный поиск «чего-нибудь» не выполняется.

## 6. Demo API proxy

Cloud Function `contractor-agent-demo-api` связывает публичный UI с Responses API.

Функции proxy:

- принимает `POST` с `message` и `previous_response_id`;
- использует `X-Demo-Token`;
- хранит Yandex API key на серверной стороне;
- валидирует ИНН перед первым запросом;
- возвращает финальный текст, HTTPS-citations, response id, latency и evidence whitelist;
- не передаёт в браузер raw MCP payload, reasoning и секреты;
- ограничивает разрешённые origins опубликованным сайтом и служебными окружениями.

Для сравнения proxy выделяет расширенный tool budget при 2–10 валидных ИНН.

## 7. Панель «Основание из отчёта»

Для первого ответа по новому отчёту UI получает ограниченный набор evidence и показывает:

- название факта;
- исходный JSON-фрагмент;
- поле отчёта;
- точное значение;
- дату отчёта.

Перед возвратом evidence proxy сверяет ИНН и проецирует только разрешённые значения.

## 8. Сессия и продолжение диалога

Responses API использует `previous_response_id` для продолжения разговора.

Системный prompt задаёт правила контекста:

- активная компания сохраняется до явной смены или сравнения;
- неоднозначный поиск требует уточнения;
- отдельный вопрос о другой компании не приводит к скрытому переключению;
- сравнение запускается только по явному запросу.

## 9. Данные и безопасность

Набор отчётов хранится в Yandex Object Storage как `reports_by_inn.json`. Доступ к данным и интеграциям организован через серверные компоненты и переменные окружения.

В клиентскую часть не передаются:

- API keys;
- Lockbox values;
- service-account keys;
- AWS-compatible credentials;
- локальные `.env` данные;
- raw MCP payload.

## 10. Regression/evaluation

Dashboard реализован на FastAPI и поддерживает:

- 59 scored cases;
- LLM judge;
- deterministic validator;
- manual review / override;
- latency, usage, citations и tool calls;
- CSV export и HTML report для печати;
- PostgreSQL в облаке и SQLite локально;
- GitHub Actions для тестов, Docker build и smoke.

Полный suite: 40 main + 16 boundary repeats + 3 Web scenarios. Финальный release gate пройден; критерии и результат описаны в документе [03](03_hypotheses_evaluation_and_pilot.md).

## 11. Инженерные принципы MVP

| Принцип | Реализация |
|---|---|
| Минимизация доступа клиента к секретам | Все ключи остаются на серверной стороне |
| Проверяемость фактов | Evidence panel + source labeling |
| Разделение источников | MCP как источник отчёта, Web Search как внешний источник |
| Контроль контекста | Явные правила выбора, смены и сравнения компаний |
| Воспроизводимая оценка | Frozen suite + LLM judge + deterministic validator |
| Наблюдаемость | latency, usage, citations, tool calls и история прогонов |

## 12. Критерий технической готовности

Техническая готовность MVP подтверждается одновременно тремя уровнями:

1. публичный end-to-end пользовательский сценарий работает через web UI;
2. MCP/Web-инструменты доступны production-агенту по заданным правилам;
3. полный regression release gate пройден на зафиксированном suite.
