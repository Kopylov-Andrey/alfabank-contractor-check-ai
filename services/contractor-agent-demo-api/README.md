# contractor-agent-demo-api

HTTP proxy между публичным Product UI и saved agent в Yandex AI Studio.

## Назначение

Proxy обеспечивает безопасный браузерный доступ к агенту без передачи Yandex API key на клиент.

Основные функции:

- принимает `POST {"message": "...", "previous_response_id": "..."}`;
- использует `X-Demo-Token`;
- получает Yandex API key из серверной конфигурации;
- валидирует ИНН перед первым запросом;
- возвращает финальный текст, HTTPS citations, response id и latency;
- формирует небольшой whitelist точных полей отчёта для панели «Основание из отчёта»;
- сверяет ИНН перед возвратом evidence;
- не возвращает в браузер raw MCP payload, reasoning и секреты;
- проверяет разрешённый origin публичного сайта.

## Evidence mode

Для первого ответа по новому отчёту proxy включает client evidence mode и возвращает разрешённые скалярные значения и JSON-фрагмент. Follow-up сообщения продолжают диалог через `previous_response_id`.

## Сравнение

Для явного сравнения 2–10 валидных ИНН proxy предоставляет агенту расширенный tool budget, необходимый для работы `compare-contractors`.

Полная схема: [`docs/07_deployed_architecture.md`](../../docs/07_deployed_architecture.md).
