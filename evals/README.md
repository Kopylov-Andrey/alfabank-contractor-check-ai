# Evaluation

Evaluation-контур MVP построен вокруг frozen suite версии 1.1.

## Состав suite

- 40 основных кейсов;
- 16 повторов 8 boundary-сценариев;
- 3 Web Search сценария;
- 59 оцениваемых ответов.

Канонические определения тестов находятся в:

- `apps/regression-dashboard/app/data/test_cases.json`;
- `docs/04_ai_evaluation_test_cases.md`.

## Оценка

Каждый ответ проходит:

1. LLM judge через KAILA;
2. deterministic validator;
3. manual review при необходимости.

## Финальный результат

- 40/40 main PASS;
- 8/8 stable boundary;
- 100% Web labeling;
- 0 effective CRITICAL;
- 59/59 полный suite;
- p95 latency 8.52 с;
- release gate: PASS.

Подробное описание критериев и результата: [`docs/03_hypotheses_evaluation_and_pilot.md`](../docs/03_hypotheses_evaluation_and_pilot.md).
