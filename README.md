# Alfa-Bank · Contractor Check AI

AI-агент для проверки контрагентов, созданный в рамках хакатон-кейса Альфа-Банка.

**«Контрагент — по фактам»** превращает банковский отчёт в короткую проверяемую сводку, отвечает на уточняющие вопросы, показывает основания, сравнивает несколько компаний и при необходимости проверяет конкретные внешние сведения через Web Search.

> Hackathon prototype. Репозиторий не является официальным продуктом Альфа-Банка.

## Что решает продукт

Основной пользователь — закупщик или менеджер юридического лица, которому перед договором, оплатой или выбором поставщика нужно быстро понять факты по новому контрагенту.

Агент:

- находит компанию по названию или точному ИНН;
- получает структурированный отчёт через MCP;
- формирует сводку и отвечает на точечные вопросы;
- показывает «Основание из отчёта» с полем, значением, датой и JSON-фрагментом;
- различает `0`, `null`, пустой список и отсутствующее поле;
- показывает общий риск и ЗСК как разные индикаторы;
- использует Web Search только для конкретных внешних вопросов и явно отделяет его от банковского отчёта;
- сравнивает 2–10 контрагентов по одинаковым фактическим показателям;
- не создаёт собственный рейтинг и не принимает решение за пользователя.

## Публичный demo

**Product demo:** https://contractor-check-agent-demo.website.yandexcloud.net/

Путь запроса:

```text
Browser
  -> Yandex Object Storage static website
  -> contractor-agent-demo-api
  -> Yandex AI Studio / contractor-check-agent
     -> contractor-check-mcp
        -> get-report-by-inn
        -> search-contractors
        -> compare-contractors
     -> Web Search
  -> contractor reports in Object Storage
```

## AI-конфигурация

| Параметр | Значение |
|---|---|
| Платформа | Yandex AI Studio / Agent Atelier |
| Модель | `Qwen3.6-35B` |
| Temperature | `0` |
| Max output tokens | `12000` |
| MCP tools | `get-report-by-inn`, `search-contractors`, `compare-contractors` |
| Web Search | enabled |

## Проверка качества

Для MVP реализован отдельный regression/evaluation dashboard:

- **40** основных кейсов;
- **16** повторов 8 boundary-сценариев;
- **3** Web Search сценария;
- **59** оцениваемых ответов;
- LLM judge через KAILA;
- deterministic validator;
- manual review / override;
- метрики factual correctness, completeness, source coverage, usefulness, boundary stability, Web labeling и latency.

### Финальный результат

- **40/40 main PASS**;
- **8/8 stable boundary**;
- **100% Web labeling**;
- **0 effective CRITICAL**;
- **59/59 полный suite**;
- **p95 latency 8.52 с**;
- **release gate: PASS**.

Подробности: [`docs/03_hypotheses_evaluation_and_pilot.md`](docs/03_hypotheses_evaluation_and_pilot.md).

## Структура репозитория

```text
apps/
  product-ui/                 Публичный продуктовый интерфейс и deployment notes
  regression-dashboard/      Автоматизированный evaluation dashboard
services/
  mcp-functions/              MCP Cloud Functions для отчётов, поиска и сравнения
  contractor-agent-demo-api/  HTTP proxy публичного demo
prompts/                      Конфигурация и контракт поведения production-агента
evals/                        Описание evaluation suite и результатов
docs/                         Продуктовые и технические документы
presentation/                 Материалы защиты и demo
.github/workflows/            CI и deployment smoke
```

## Документация

1. [Проблема клиента и ценность](docs/01_client_problem_and_value.md)
2. [MVP и продуктовые решения](docs/02_mvp_and_product_decisions.md)
3. [Гипотезы и evaluation](docs/03_hypotheses_evaluation_and_pilot.md)
4. [Эталонный набор AI-тестов](docs/04_ai_evaluation_test_cases.md)
5. [Техническая спецификация MVP](docs/05_engineering_spec_mvp.md)
6. [Требования к AI-агенту и production prompt](docs/06_agent_prompt_spec.md)
7. [Архитектура deployment](docs/07_deployed_architecture.md)

## Команда

| Участник | Роль |
|---|---|
| Копылов Андрей Михайлович | AI Product |
| Щербаков Сергей Владимирович | AI Engineer |
| Черных Александр Владимирович | AI Engineer |

## Безопасность

API-ключи и сервисные credentials хранятся на серверной стороне. В браузер не передаются Yandex API key, raw MCP payload, reasoning и служебные секреты. Приватный набор отчётов хранится в Yandex Object Storage и не публикуется в репозитории.
