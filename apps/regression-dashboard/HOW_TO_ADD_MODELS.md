# Настройка моделей LLM-судьи в CAILA

Regression dashboard использует отдельную модель-судью через OpenAI-compatible API CAILA.

## Проверенная конфигурация

```env
JUDGE_BASE_URL=https://caila.io/api/adapters/openai
JUDGE_MODELS=gpt-5.6-luna,gpt-5.6-terra,gpt-5.6-sol
DEFAULT_JUDGE_MODEL=gpt-5.6-luna
```

Финальный regression run использует `gpt-5.6-luna` как judge model.

## Проверка доступных моделей

После настройки `JUDGE_API_KEY` запустите:

```bash
python check_caila_models.py
```

Скрипт проверит список candidate models через Chat Completions и покажет, какие model ID доступны текущему аккаунту.

## Добавление модели

1. Убедитесь, что model ID доступен в CAILA.
2. Добавьте его в `JUDGE_MODELS`.
3. Если для модели нужен отдельный профиль, добавьте его в `app/judge_models.py`.
4. Перезапустите dashboard.
5. Выполните smoke/evaluation run и проверьте корректность JSON-ответа судьи.

## Важное правило

В публичном UI можно выбирать только модели из серверного allowlist `JUDGE_MODELS`. Это исключает подстановку произвольного model ID со стороны клиента.
