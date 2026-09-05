# Agent Regression Lab

Публичный dashboard для воспроизводимой проверки `contractor-check-agent`:

- 40 основных сценариев;
- 16 повторов восьми boundary-сценариев;
- 3 сценария Web Search;
- 27 независимых диалогов и 86 вызовов агента вместе с setup-turns;
- оценка каждого ответа отдельной LLM-судьёй;
- независимая алгоритмическая проверка точных фактов и критических условий;
- ручная корректировка оценки с комментарием;
- метрики качества, latency, usage, citations и tool calls;
- сравнение версий промпта и моделей;
- PostgreSQL в облаке, SQLite локально.
- GitHub Actions: тесты, Docker build и smoke после деплоя.

## Архитектура

```mermaid
flowchart LR
    UI[Public dashboard] --> API[FastAPI backend]
    API --> YA[Yandex Responses API]
    API --> J[LLM judge via KAILA]
    API --> V[Deterministic validator]
    API --> DB[(PostgreSQL)]
```

Просмотр результатов публичный. Запуск прогонов, остановка и ручное изменение
оценки требуют `ADMIN_TOKEN`. API-ключи никогда не передаются в браузер.

## Быстрый запуск

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env            # Windows: copy .env.example .env
```

Заполните в `.env`:

- `YANDEX_API_KEY` — ключ проверяемого агента;
- `JUDGE_BASE_URL` и `JUDGE_API_KEY` — OpenAI-compatible KAILA endpoint;
- `JUDGE_MODELS` — разрешённые модели через запятую;
- `ADMIN_TOKEN` — длинная случайная строка.

Затем:

```bash
uvicorn app.main:app --reload
```

Сайт откроется на `http://localhost:8000`. Без `DATABASE_URL` используется
локальный `regression.db`.

## Как устроен полный прогон

Основные пять вопросов каждой из восьми компаний идут в одном диалоге после
setup-turn. Каждый из 16 повторов boundary-сценариев и каждый из трёх Web
сценариев получает отдельный setup-turn. Итого: 59 оцениваемых ответов,
27 setup-turns и 86 API-запросов.

Диалоги продолжаются через `previous_response_id`. Одновременно выполняется не
более `MAX_CONCURRENCY` диалогов. Внутри одного диалога порядок строго
последовательный.

## LLM-судья

Backend отправляет судье вопрос, ожидаемые факты, обязательные основания,
запрещённые формулировки, условие критической ошибки, ответ агента, citations и
tool calls. Судья возвращает JSON с:

- `PASS / PARTIAL / FAIL / CRITICAL`;
- фактической корректностью и полнотой;
- покрытием источниками;
- полезностью и ложными отказами;
- вердиктами за пользователя;
- использованием и маркировкой Web Search;
- причиной оценки, пропусками и неподтверждёнными тезисами.

Модель выбирается на сайте только из серверного `JUDGE_MODELS`. Это защищает от
подстановки произвольной дорогой модели в публичном интерфейсе.

## Алгоритмическая проверка

Правила из `app/data/algorithmic_rules.json` проверяют точные ИНН, компании,
даты, суммы, статусы, уровни риска, обязательные факты и явно запрещённые
утверждения. Валидатор использует только стандартную библиотеку Python и не
оценивает стиль, полезность или качество источников.

LLM-статус остаётся основным. Только алгоритмический `CRITICAL` меняет итоговый
`auto_status` на `CRITICAL`; любое другое расхождение сохраняет LLM-статус и
выставляет `requires_manual_review=true`. Ручная оценка по-прежнему имеет
приоритет при отображении эффективного статуса.

## PostgreSQL / Supabase

1. Создайте бесплатный проект Supabase.
2. Скопируйте PostgreSQL connection string.
3. Укажите его как `DATABASE_URL` в формате `postgresql://...`.

Приложение автоматически создаст таблицы `runs` и `results` при старте.

## Бесплатный деплой на Koyeb

1. Создайте GitHub-репозиторий и отправьте туда этот проект.
2. В Koyeb выберите **Create Web Service → GitHub**.
3. Выберите репозиторий и сборку через `Dockerfile`.
4. Выберите Free instance.
5. Добавьте все переменные из `.env.example` в Secrets/Environment Variables.
6. Для `DATABASE_URL` используйте строку подключения Supabase.
7. Проверьте `/api/health`: `agent_configured` и `judge_configured` должны быть `true`.

Важно: бесплатный публичный backend может «засыпать». Первый запрос после
простоя будет медленнее. История не потеряется, потому что она хранится во
внешнем PostgreSQL.

## Проверки

```bash
pytest -q
node --check app/static/app.js
python -m compileall -q app
```

## Ограничения первого релиза

- Для реального запуска нужно уточнить точный OpenAI-compatible URL KAILA и
  идентификаторы доступных моделей.
- Фоновый runner рассчитан на один backend worker. Для нескольких worker или
  долгого production-процесса нужен отдельный job queue.
- Оценка LLM-судьи не считается абсолютной истиной: ручная корректировка и
  комментарий сохраняются отдельно, не уничтожая исходную оценку.
