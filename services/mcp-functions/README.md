# MCP Cloud Functions

This directory contains source snapshots imported from the deployed Yandex Cloud Functions exposed through `contractor-check-mcp`.

## Functions

### `get-report-by-inn`

Files imported from the deployed function:

```text
get-report-by-inn/
  index.py
  report_projection.py
  requirements.txt
```

Observed deployment:

- Python 3.12
- entrypoint `index.handler`
- timeout 5 seconds
- memory 256 MB
- service account `storage-reader-sa`
- read-only mount of bucket `contractor-reports` at `/function/storage/contractor-reports`
- primary dataset key `reports_by_inn.json`

The function validates a 10- or 12-digit INN and supports `full`, `compact` and `sections` views. The projection module preserves semantic differences between absent fields, `null`, empty arrays and present values.

### `search-contractors`

Files imported from the deployed function:

```text
search-contractors/
  index.py
  requirements.txt
```

It normalizes text and searches contractor short/full names, address, main activity code/description and other activity descriptions. It returns at most 20 matches with `inn`, `name`, `riskLevel` and `address`.

The inspected deployment reads AWS-compatible Object Storage credentials from environment variables. Do not commit real values.

### `compare-contractors`

Files imported from the deployed function:

```text
compare-contractors/
  index.py
  report_projection.py
```

The deployed editor did not show a `requirements.txt` for this function. The function accepts 2-10 INNs, validates each value, loads reports from the same contractor dataset and applies the same projection contract used by `get-report-by-inn`.

## MCP server snapshot

- server label: `contractor-check-mcp`
- transport: HTTP with SSE
- access: private
- service account: `storage-reader-sa`
- exposed tools:
  - `get-report-by-inn`
  - `search-contractors`
  - `compare-contractors`

## Security and data

Do not commit:

- the full `reports_by_inn.json` contractor dataset;
- API keys;
- Lockbox values;
- service-account keys;
- AWS-compatible access/secret keys;
- local `.env` files.

See [`docs/07_deployed_architecture.md`](../../docs/07_deployed_architecture.md) for the deployment snapshot and component relationships.
