# Как добавить модели CAILA

## Проблема

Не все модели из каталога CAILA доступны в вашем тарифном плане.
При попытке использовать недоступную модель вы получите:
```
HTTP 400: {"code":"mlp.open.ai.proxy.unknown_model_by_proxy","message":"The model XXX is unknown by proxy. Add model to pricing list"}
```

## Решение: проверить доступные модели

### Шаг 1: Запустите тестовый скрипт

```bash
# Убедитесь что JUDGE_API_KEY в .env
python test_caila_models.py
```

Скрипт проверит ~20 популярных моделей и покажет какие работают с вашим API ключом.

### Пример вывода:

```
🔍 Testing CAILA models with your API key...
📊 Testing 20 models...

Testing gpt-5.6-luna                  ✅ WORKS
Testing gpt-5.6-terra                 ✅ WORKS
Testing gpt-5.6-sol                   ✅ WORKS
Testing gpt-4.1                       ❌ NOT IN PRICING
Testing claude-opus-5                 ❌ NOT IN PRICING
...

===========================================
SUMMARY
===========================================

✅ WORKING MODELS (3):
  gpt-5.6-luna                   — OpenAI GPT-5.6 Luna
  gpt-5.6-terra                  — OpenAI GPT-5.6 Terra
  gpt-5.6-sol                    — OpenAI GPT-5.6 Sol

CONFIGURATION
===========================================

Add these to your .env file:

JUDGE_MODELS=gpt-5.6-luna,gpt-5.6-terra,gpt-5.6-sol
DEFAULT_JUDGE_MODEL=gpt-5.6-luna
```

### Шаг 2: Обновите .env

Скопируйте строки `JUDGE_MODELS` и `DEFAULT_JUDGE_MODEL` в ваш `.env`:

```bash
# .env
JUDGE_API_KEY=your-caila-key
JUDGE_BASE_URL=https://caila.io/api/adapters/openai
JUDGE_MODELS=gpt-5.6-luna,gpt-5.6-terra,gpt-5.6-sol
DEFAULT_JUDGE_MODEL=gpt-5.6-luna
```

### Шаг 3: Перезапустите сервер

```bash
uvicorn app.main:app --reload
```

### Шаг 4: Проверьте UI

Откройте UI и создайте новый прогон — в dropdown должны быть только рабочие модели.

## Как добавить больше моделей

### Вариант 1: Обновить тарифный план CAILA

1. Зайдите на https://caila.io
2. Перейдите в настройки тарифного плана
3. Добавьте нужные модели в pricing list
4. Снова запустите `test_caila_models.py`
5. Обновите `JUDGE_MODELS` в `.env`

### Вариант 2: Добавить model ID вручную

Если вы знаете точный model ID (из документации провайдера или CAILA support):

1. Добавьте в `.env`:
   ```bash
   JUDGE_MODELS=gpt-5.6-luna,gpt-5.6-terra,gpt-5.6-sol,your-new-model-id
   ```

2. Добавьте профиль в `app/judge_models.py`:
   ```python
   PROFILES = {
       # ... existing ...
       "your-new-model-id": JudgeModelProfile(
           "your-new-model-id", "Provider", "Display Name", "standard"
       ),
   }
   ```

3. Протестируйте прогон с новой моделью

4. Если получаете HTTP 400 → модель недоступна, уберите из `.env`

## Текущая конфигурация

По умолчанию включены только **проверенные рабочие модели**:
```python
# config.py
JUDGE_MODELS = "gpt-5.6-luna,gpt-5.6-terra,gpt-5.6-sol"
```

Это минимальный набор, который работает на базовом CAILA тарифе.

## Часто задаваемые вопросы

### Q: Почему модели из каталога не работают?

A: Каталог CAILA (https://caila.io/catalog) показывает все доступные модели на платформе, но доступность конкретных моделей зависит от вашего тарифного плана. Не все модели автоматически добавлены в ваш pricing list.

### Q: Как узнать какие модели в моём плане?

A: Запустите `python test_caila_models.py` — он проверит популярные модели и покажет доступные.

### Q: Могу ли я использовать claude-opus-5 или gemini-3.1-pro?

A: Да, если они есть в вашем CAILA тарифном плане. Проверьте через тестовый скрипт или обратитесь в support CAILA для добавления моделей в ваш pricing list.

### Q: Что делать если ни одна модель не работает?

A: Проверьте:
1. Правильность API ключа в `.env`
2. Баланс на аккаунте CAILA
3. Активность тарифного плана
4. Обратитесь в support: https://t.me/justai_devs

### Q: Сколько стоит добавить модель в pricing list?

A: Зависит от модели и тарифа. Обратитесь в CAILA support для уточнения цен: https://caila.io

## Полезные ссылки

- Каталог моделей: https://caila.io/catalog
- Документация API: https://docs.caila.io/hub/api/openai-api
- Чат разработчиков: https://t.me/justai_devs
- Тестовый скрипт: `test_caila_models.py`

## Что делать дальше

1. ✅ Запустите `python test_caila_models.py`
2. ✅ Обновите `.env` с рабочими моделями
3. ✅ Перезапустите сервер
4. ✅ Создайте тестовый прогон
5. ✅ Если нужно больше моделей — обратитесь в CAILA support
