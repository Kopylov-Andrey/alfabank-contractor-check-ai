# Live AI Studio agent configuration

**Дата:** 7 сентября 2026 года

## Agent

- name: `contractor-check-agent`
- platform: Yandex AI Studio / Agent Atelier
- model: `Qwen3.6-35B`
- temperature: `0`
- max output tokens: `12000`
- saved prompt id: `fvtq3dj5gqmo38h4mk94`

## Tools

### MCP

Server label: `contractor-check-mcp`.

Подключённые инструменты:

- `get-report-by-inn`;
- `search-contractors`;
- `compare-contractors`.

MCP используется как основной источник данных банковского отчёта.

### Web Search

- enabled;
- `search_context_size = medium`;
- используется для конкретных внешних вопросов по правилам production prompt;
- внешние сведения явно отделяются от данных отчёта.

## Ключевые правила поведения

- ИНН определяется только через MCP;
- активная компания не меняется неявно;
- общий риск и ЗСК показываются отдельно;
- `0`, `null`, `[]` и отсутствующее поле имеют разную семантику;
- Web Search не подменяет банковский отчёт;
- сравнение нескольких компаний не превращается в собственный рейтинг;
- итоговое решение остаётся за пользователем;
- фактические ответы сопровождаются источником.

Полный system prompt: [`agent-system-v1.md`](agent-system-v1.md).

Поведенческий контракт: [`../docs/06_agent_prompt_spec.md`](../docs/06_agent_prompt_spec.md).
