# Live AI Studio agent configuration

Snapshot inspected on 2026-09-06.

## Agent

- name: `contractor-check-agent`
- platform: Yandex AI Studio / Agent Atelier
- model: `Qwen3.6-35B`
- temperature: `0`
- max output tokens: `12000`
- saved prompt id: `fvtq3dj5gqmo38h4mk94`
- project/folder id: `b1gfdj9gscod1qetbbpj`

## Tools

### MCP

- label: `contractor-check-mcp`
- URL: `https://db81uub1t2h5sr9vjs0u.fi4781wp.mcpgw.serverless.yandexcloud.net`
- approval: `never`
- transport observed in Yandex Cloud: HTTP with SSE

Tools exposed by the MCP server:

- `get-report-by-inn`
- `search-contractors`
- `compare-contractors`

### Web Search

- enabled
- `search_context_size = medium`
- no allowed-domain restriction was configured in the generated call example

## Prompt behavior captured from the live configuration

The live system instruction supplied during the repository audit defines these core contracts:

- use MCP as the authoritative source for company identity and report facts;
- never use Web Search to discover or verify an INN;
- keep general risk (`baseInfo.riskLevel`) and ZSK risk (`zskRiskLevel`) separate;
- distinguish `0`, `null`, `[]` and an absent field;
- use `compact`, `sections` and `full` report projections intentionally;
- separate report evidence from Web Search evidence;
- do not issue a final work / do-not-work verdict or rank companies by reliability;
- use the `[CLIENT_EVIDENCE_V1]` marker only for the client evidence-tab mode;
- enforce source labels and narrow answer formats for point questions;
- handle technical errors and ambiguous contractor selection without guessing.

The full live system instruction was exported during the audit but is not duplicated in this file. Keep any future full prompt export free of credentials and secret infrastructure values.

## Responses API call shape

```python
import openai

client = openai.OpenAI(
    api_key="<API_key_value>",
    base_url="https://ai.api.cloud.yandex.net/v1",
    project="b1gfdj9gscod1qetbbpj",
)

response = client.responses.create(
    prompt={"id": "fvtq3dj5gqmo38h4mk94"},
    input="some message",
    tools=[
        {
            "type": "mcp",
            "server_label": "contractor-check-mcp",
            "server_url": "https://db81uub1t2h5sr9vjs0u.fi4781wp.mcpgw.serverless.yandexcloud.net",
            "server_description": "",
            "require_approval": "never",
        },
        {
            "type": "web_search",
            "filters": {"allowed_domains": []},
            "search_context_size": "medium",
        },
    ],
)
```

Never commit a real API key.
