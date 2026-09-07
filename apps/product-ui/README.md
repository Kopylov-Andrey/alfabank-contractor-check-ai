# Product UI

Публичный demo интерфейс продукта размещён в Yandex Object Storage:

**https://contractor-check-agent-demo.website.yandexcloud.net/**

## Пользовательский сценарий

```text
Browser
  -> Object Storage static website
  -> contractor-agent-demo-api
  -> Yandex AI Studio saved agent
```

Интерфейс поддерживает:

- ввод ИНН или названия компании;
- получение сводки по контрагенту;
- уточняющий диалог;
- панель «Основание из отчёта»;
- отображение Web citations;
- сравнение нескольких компаний.

## Evidence panel

Для первого ответа по новому отчёту UI показывает ограниченный набор точных оснований:

- название факта;
- поле отчёта;
- значение;
- дату отчёта;
- JSON-фрагмент.

## Security

Браузер не получает Yandex API key и raw MCP payload. Все обращения к saved agent проходят через `contractor-agent-demo-api`.

Полная архитектура: [`docs/07_deployed_architecture.md`](../../docs/07_deployed_architecture.md).
