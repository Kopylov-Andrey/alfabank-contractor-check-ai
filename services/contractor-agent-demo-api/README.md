# contractor-agent-demo-api

HTTP proxy between the public demo UI and the saved Yandex AI Studio agent.

This directory currently documents the deployed Cloud Function. The original `index.py` and `test_index.py` sources have not yet been imported into this repository.

Observed deployed behavior:

- API key is loaded from `YANDEX_API_KEY` via Lockbox-backed Cloud Function configuration.
- Accepts only `POST {"message": "...", "previous_response_id": "..."}` with `X-Demo-Token`.
- Returns only final text, HTTPS citations, response id, latency and a small whitelist of exact report fields for the “Основание из отчёта” evidence panel.
- Raw MCP payload remains inside the function; before returning evidence, the function checks the INN and projects only allowed scalar values plus a JSON fragment.
- Origin is restricted to the published Yandex Object Storage site, the previous Sites URL used for rollback and a local development server.
- The first request requires an INN with a valid checksum; comparison receives an expanded tool budget only for 2-10 valid INNs.
- Client evidence mode is enabled only for the first response with a new report. Follow-up calls do not pass the marker, so the agent prints local sources again even when it reuses dialogue context and does not repeat an MCP call.
- MCP call bodies, reasoning and secrets are not returned to the browser. Evidence parsing failure does not break the primary answer and produces an empty evidence array.

Observed source files in the Yandex Cloud Function editor:

```text
index.py
README.md
test_index.py
```

See [`docs/07_deployed_architecture.md`](../../docs/07_deployed_architecture.md) for the full deployed path.
