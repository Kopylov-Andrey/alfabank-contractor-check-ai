# Настройка публичного стенда

Перед обновлением 6 сентября прочитайте [CHANGE_REPORT.md](CHANGE_REPORT.md):
остановить старую версию, сделать backup БД, запустить один новый worker.
Добавляется nullable runs.provenance без заполнения исторических версий.
Для PostgreSQL необходим session/direct connection; transaction pooler
несовместим с блокировкой единственного worker. Реальное обновление стенда
и платные smoke-прогоны в этой задаче не выполнялись.

## Секреты Koyeb

| Переменная | Назначение | Публичная |
|---|---|---|
| `YANDEX_API_KEY` | Вызов тестируемого агента | Нет |
| `YANDEX_FOLDER_ID` | Каталог Yandex Cloud | Нет |
| `YANDEX_AGENT_ID` | ID сохранённого агента | Нет |
| `MCP_SERVER_URL` | MCP Gateway | Нет |
| `JUDGE_API_KEY` | Доступ к KAILA | Нет |
| `JUDGE_BASE_URL` | OpenAI-compatible endpoint | Нет |
| `JUDGE_MODELS` | Allowlist моделей для UI | Можно |
| `DEFAULT_JUDGE_MODEL` | Модель по умолчанию | Можно |
| `DATABASE_URL` | PostgreSQL Supabase | Нет |
| `ADMIN_TOKEN` | Запуск и ручная оценка | Нет |

## Проверка после деплоя

1. Открыть `/api/health`.
2. Убедиться, что обе интеграции имеют состояние `true`.
3. Ввести `ADMIN_TOKEN` через кнопку «Токен запуска».
4. Выполнить сначала набор `boundary` или отдельный smoke до полного прогона.
5. Проверить, что после перезапуска сервиса созданный прогон сохранился.

## GitHub Actions и автодеплой

В репозитории уже есть два workflow:

- `CI` — запускает pytest, компиляцию Python, проверку JavaScript и сборку
  production Docker image на каждый push и pull request;
- `Deployment smoke` — после успешного CI ждёт автодеплой Koyeb и проверяет
  `/api/health`.

В настройках репозитория добавьте Actions secret:

```text
APP_HEALTH_URL=https://<ваш-сервис>.koyeb.app/api/health
```

В Koyeb включите autodeploy для ветки `main`. Чтобы не развернуть commit с
падающими тестами, включите в GitHub branch protection для `main`:

1. Require a pull request before merging.
2. Require status checks to pass.
3. Выберите проверки `Tests and static checks` и `Docker build`.

Поток: PR → CI → merge в `main` → Koyeb autodeploy → deployment health-check.

## Рекомендуемый порядок релиза

1. Локальная проверка с SQLite.
2. Подключение Supabase.
3. Деплой в Koyeb из GitHub.
4. Smoke на минимальном наборе.
5. Полный frozen-прогон без изменения тестов и промпта.
6. Ручной аудит всех `PARTIAL`, `FAIL`, `CRITICAL` и случайной выборки `PASS`.
