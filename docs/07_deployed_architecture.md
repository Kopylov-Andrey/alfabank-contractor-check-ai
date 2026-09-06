# Deployed architecture snapshot

This document records the Yandex Cloud deployment inspected on 2026-09-06. It is a deployment snapshot, not a replacement for the product or engineering specifications.

## End-user path

```text
Browser
  -> Yandex Object Storage static website
     contractor-check-agent-demo.website.yandexcloud.net
  -> Cloud Function proxy
     contractor-agent-demo-api
  -> Yandex AI Studio Responses API
     saved agent: contractor-check-agent
  -> MCP server: contractor-check-mcp
     -> get-report-by-inn
     -> search-contractors
     -> compare-contractors
  -> Object Storage bucket contractor-reports
     -> reports_by_inn.json

The agent also has Web Search enabled with search_context_size=medium.
```

## Saved AI Studio agent

Observed configuration:

- name: `contractor-check-agent`
- model: `Qwen3.6-35B`
- temperature: `0`
- max output tokens: `12000`
- Responses API base URL: `https://ai.api.cloud.yandex.net/v1`
- project/folder id: `b1gfdj9gscod1qetbbpj`
- saved prompt id: `fvtq3dj5gqmo38h4mk94`
- MCP server label: `contractor-check-mcp`
- MCP server URL: `https://db81uub1t2h5sr9vjs0u.fi4781wp.mcpgw.serverless.yandexcloud.net`
- MCP approval mode: `never`
- Web Search context size: `medium`

Reference call shape from AI Studio:

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

## MCP server

Observed MCP server properties:

- transport: HTTP with SSE
- access: private
- service account: `storage-reader-sa`
- tools:
  - `get-report-by-inn`
  - `search-contractors`
  - `compare-contractors`

### get-report-by-inn

Cloud Function runtime snapshot:

- runtime: Python 3.12
- entrypoint: `index.handler`
- timeout: 5 seconds
- memory: 256 MB
- service account: `storage-reader-sa`
- mounted bucket: `contractor-reports`
- mount path: `/function/storage/contractor-reports`
- mount mode: read-only

The function reads `reports_by_inn.json` from the mounted bucket and falls back to S3-compatible Object Storage access. It supports `full`, `compact` and `sections` projections.

### search-contractors

The function searches normalized text over contractor names, address and activity descriptions, returns at most 20 results and exposes `inn`, `name`, `riskLevel` and `address`.

The inspected deployment uses `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment variables for S3-compatible Object Storage access. Real values must not be committed.

### compare-contractors

The function accepts 2-10 INNs, validates them, returns a report or a per-INN not-found marker, and applies the same `full`, `compact` or `sections` projection contract as `get-report-by-inn`.

## Demo API proxy

Observed Cloud Function: `contractor-agent-demo-api`.

Its deployed README states that it:

- is an HTTP proxy between the public demo UI and the saved AI Studio agent;
- reads `YANDEX_API_KEY` from Lockbox-backed environment configuration;
- accepts only `POST {"message": "...", "previous_response_id": "..."}` with `X-Demo-Token`;
- returns final text, HTTPS citations, response id, latency and a small evidence whitelist;
- keeps raw MCP payload, reasoning and secrets server-side;
- validates INN before the first request;
- uses an evidence mode for the first response with a new report;
- restricts allowed origins to the published Object Storage site, a rollback Sites URL and local development.

Source files observed in the Cloud Function editor:

```text
index.py
README.md
test_index.py
```

The source code itself has not yet been imported into this repository.

## Product UI deployment

The public UI is deployed from Yandex Object Storage bucket `contractor-check-agent-demo` and is available at:

`https://contractor-check-agent-demo.website.yandexcloud.net/`

Observed bucket contents:

```text
assets/
favicon.svg
index.html
og.png
```

The `assets/` directory contains hashed JavaScript and CSS bundles from several successive builds. No source maps were observed. Therefore the bucket contains a production build, not the original frontend source tree.

Original frontend sources have not yet been located. Until they are recovered, `apps/product-ui/` documents the deployed artifact and the missing-source status.

## Data boundary

The private contractor dataset is stored in Object Storage bucket `contractor-reports` as `reports_by_inn.json`.

Do not commit the full dataset, Lockbox values, service-account keys, AWS-compatible credentials, local `.env` files or Yandex API keys.

## Still missing from the repository

- original Product UI source tree (`src/`, `package.json`, build config, etc.);
- source code of `contractor-agent-demo-api`;
- deployment metadata/scripts for publishing the Product UI build;
- frozen production evaluation exports, when the final run is ready.
