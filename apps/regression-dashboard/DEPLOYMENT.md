# Deployment regression dashboard

Dashboard разворачивается как один FastAPI web service с внешней PostgreSQL БД или локальной SQLite.

## Переменные окружения

| Переменная | Назначение |
|---|---|
| `YANDEX_API_KEY` | Вызов тестируемого агента |
| `YANDEX_FOLDER_ID` | Yandex Cloud folder |
| `YANDEX_AGENT_ID` | Saved agent ID |
| `MCP_SERVER_URL` | MCP Gateway |
| `JUDGE_API_KEY` | Доступ к KAILA |
| `JUDGE_BASE_URL` | OpenAI-compatible endpoint |
| `JUDGE_MODELS` | Allowlist моделей судьи |
| `DEFAULT_JUDGE_MODEL` | Модель по умолчанию |
| `DATABASE_URL` | PostgreSQL / SQLite |
| `ADMIN_TOKEN` | Защита запуска и manual review |
| `MAX_CONCURRENCY` | Параллельность диалогов |
| `REQUEST_TIMEOUT_SECONDS` | Тайм-аут интеграций |

Пример значений без секретов находится в `.env.example`.

## Docker

```bash
docker build -t contractor-regression .
docker run --env-file .env -p 8000:8000 contractor-regression
```

После запуска проверить:

```text
GET /api/health
```

`agent_configured` и `judge_configured` должны быть `true`.

## Koyeb / аналогичный PaaS

1. Подключить GitHub repository.
2. Выбрать сборку через `Dockerfile`.
3. Добавить переменные окружения как secrets.
4. Подключить PostgreSQL через `DATABASE_URL`.
5. Использовать один backend worker для runner.
6. Включить autodeploy для основной ветки.
7. Проверить `/api/health` после релиза.

## GitHub Actions

Репозиторий содержит:

- `CI` — pytest, Python compile, JavaScript checks и Docker build;
- `Deployment smoke` — проверка health endpoint после deployment.

Для deployment smoke задаётся repository secret:

```text
APP_HEALTH_URL=https://<service>/api/health
```

## Рекомендуемый release flow

```text
PR
 -> CI
 -> merge
 -> autodeploy
 -> /api/health
 -> smoke scope
 -> full frozen regression suite
 -> review результатов
```

Канонический полный suite содержит 59 scored cases. Финальный release gate проекта пройден; критерии описаны в [`../../docs/03_hypotheses_evaluation_and_pilot.md`](../../docs/03_hypotheses_evaluation_and_pilot.md).
