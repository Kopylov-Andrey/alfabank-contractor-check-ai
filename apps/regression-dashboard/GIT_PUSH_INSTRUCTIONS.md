# 🚀 Инструкция по коммиту и пушу всех изменений

## Шаг 1: Удалите временные файлы

```bash
# Удалить все временные MD документы
rm CAILA_MODELS_FIXED.md
rm CAILA_MODELS_VERIFIED.md
rm FINAL_STATUS.md
rm JUDGE_MODELS_FINAL.md
rm JUDGE_MODELS_SIMPLE.md
rm JUDGE_MODELS_SUMMARY.txt
rm CHANGE_REPORT.md
rm JUDGE.md
rm commit_plan.txt

# Удалить backup базы данных
rm regression.db.before-judge-followup-backup
```

## Шаг 2: Добавьте все изменения

```bash
# Добавить ВСЕ изменённые файлы приложения
git add .gitignore
git add DEPLOYMENT.md
git add README.md
git add app/
git add tests/
git add check_caila_models.py
git add HOW_TO_ADD_MODELS.md
```

## Шаг 3: Создайте коммит

```bash
git commit -m "feat: complete judge models and regression dashboard improvements

Judge Models:
- Configure only verified CAILA models (gpt-5.6-luna/terra/sol)
- Remove unavailable models (HTTP 400 unknown_model_by_proxy)
- Add check_caila_models.py to verify model availability
- Add HOW_TO_ADD_MODELS.md instruction
- Simplify judge_models.py with verified profiles
- Remove diagnostic endpoints and UI buttons

Regression Dashboard Improvements:
- Add algorithmic validation
- Add run management and lifecycle
- Add provenance tracking and comparison
- Add export functionality (CSV, HTML/PDF)
- Add judge contract tests
- Add browser smoke tests
- Improve metrics calculation

All 167 tests passing ✅"
```

## Шаг 4: Запушьте

```bash
git push origin main
```

Или если работаете в другой ветке:

```bash
git push origin <your-branch-name>
```

## 📋 Быстрая версия (все команды подряд)

```bash
# 1. Чистим временные файлы
rm CAILA_MODELS_*.md FINAL_STATUS.md JUDGE_MODELS_*.md JUDGE_MODELS_SUMMARY.txt CHANGE_REPORT.md JUDGE.md commit_plan.txt regression.db.before-judge-followup-backup 2>/dev/null

# 2. Добавляем все нужные изменения
git add .gitignore DEPLOYMENT.md README.md app/ tests/ check_caila_models.py HOW_TO_ADD_MODELS.md

# 3. Коммитим
git commit -m "feat: complete judge models and regression dashboard improvements

Judge Models:
- Configure only verified CAILA models (gpt-5.6-luna/terra/sol)
- Remove unavailable models (HTTP 400 unknown_model_by_proxy)
- Add check_caila_models.py to verify model availability
- Add HOW_TO_ADD_MODELS.md instruction
- Simplify judge_models.py with verified profiles
- Remove diagnostic endpoints and UI buttons

Regression Dashboard:
- Add algorithmic validation
- Add run management and lifecycle
- Add provenance tracking and comparison
- Add export functionality (CSV, HTML/PDF)
- Add judge contract tests
- Add browser smoke tests
- Improve metrics calculation

All 167 tests passing ✅"

# 4. Пушим
git push origin main
```

## ✅ Что будет закоммичено

### Изменённые файлы (M):
- `.gitignore` - обновлённые правила
- `DEPLOYMENT.md` - документация
- `README.md` - обновлённая документация
- `app/algorithmic_validation.py` - алгоритмическая валидация
- `app/clients.py` - упрощённый клиент judge
- `app/config.py` - только 3 рабочие модели
- `app/database.py` - обновлённая схема
- `app/evaluation.py` - улучшенная оценка
- `app/export.py` - экспорт результатов
- `app/main.py` - обновлённые endpoints
- `app/metrics.py` - расчёт метрик
- `app/runner.py` - улучшенный runner
- `app/static/app.js` - обновлённый UI
- `app/static/index.html` - обновлённый UI
- `app/static/styles.css` - обновлённые стили
- `tests/test_algorithmic_validation.py` - тесты

### Новые файлы (A):
- `app/comparison.py` - сравнение прогонов
- `app/judge_models.py` - профили моделей
- `app/lifecycle.py` - управление жизненным циклом
- `app/provenance.py` - отслеживание происхождения
- `check_caila_models.py` - скрипт проверки моделей
- `HOW_TO_ADD_MODELS.md` - инструкция
- `tests/browser-smoke.mjs` - browser тесты
- `tests/browser_server.py` - тестовый сервер
- `tests/conftest.py` - pytest конфигурация
- `tests/test_judge_contract.py` - тесты контракта judge
- `tests/test_judge_followup.py` - тесты judge
- `tests/test_lifecycle_extended.py` - тесты lifecycle
- `tests/test_provenance_comparison.py` - тесты provenance

### НЕ коммитится:
- ❌ Временные MD файлы (CAILA_MODELS_*.md и т.д.)
- ❌ `.env` (в .gitignore)
- ❌ `regression.db` (в .gitignore)
- ❌ Backup файлы базы

## 🔍 Проверка перед пушем

```bash
# Убедитесь что все тесты проходят
python -m pytest tests/ -v

# Должно быть: 167 passed

# Проверьте что добавлено в коммит
git status

# Проверьте содержимое коммита
git log -1 --stat
```

## ⚠️ Если что-то пошло не так

### Отменить последний коммит (до пуша)
```bash
git reset --soft HEAD~1
```

### Отменить добавленные файлы
```bash
git reset
```

### Проверить что будет запушено
```bash
git log origin/main..HEAD --oneline
```

## 🎯 Итого

После выполнения команд выше у вас будет:
- ✅ Один коммит со всеми изменениями
- ✅ Все временные файлы удалены
- ✅ 167 тестов проходят
- ✅ Чистый git status после пуша

Готово! 🎉
