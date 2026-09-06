# Alfa-Bank · Contractor Check AI

AI-powered counterparty verification platform created for the Alfa-Bank
hackathon case. The system turns contractor reports into concise, verifiable
summaries, answers follow-up questions, compares companies without making the
decision for the user, and clearly separates report data from web sources.

> Hackathon prototype. This repository is not an official Alfa-Bank product.

## Product

The primary user is a procurement specialist or company manager who needs to
evaluate a new supplier or contractor before signing an agreement or making a
payment.

The agent:

- finds a contractor by name or exact tax ID;
- retrieves a structured report through MCP tools;
- keeps general risk and the KYC platform indicator separate;
- distinguishes zero, null, an empty list, and a missing field;
- answers questions with explicit evidence;
- uses Web Search only as a clearly labelled secondary source;
- compares several contractors without selecting a “winner”;
- never issues a final “work / do not work” verdict.

## Repository structure

```text
apps/
  product-ui/              Main end-user interface deployment notes; source pending recovery
  regression-dashboard/   Automated evaluation and quality dashboard
services/
  mcp-functions/           Imported Yandex Cloud Function source snapshots exposed through MCP
  contractor-agent-demo-api/  Deployed demo proxy documentation; source pending import
prompts/                   Live AI Studio configuration and versioned prompt material
evals/                     Frozen evaluation artifacts and run results
docs/                      Product, MVP, evaluation, engineering and deployment documents
presentation/              Final pitch deck and demo materials
.github/workflows/         CI and deployment verification
```

## Current status

| Component | Status |
|---|---|
| Agent in Yandex AI Studio | Implemented and deployed |
| MCP tools | Implemented; deployed source snapshots imported |
| Product UI | Deployed in Yandex Object Storage; original source tree not yet recovered |
| Demo API proxy | Deployed; behavior documented, source pending import |
| Regression dashboard | Implemented |
| Frozen evaluation suite | 40 main + 16 repeats + 3 Web Search scenarios |
| Public product demo | Available in Yandex Object Storage static hosting |

## Deployed path

```text
Browser
  -> contractor-check-agent-demo.website.yandexcloud.net
  -> contractor-agent-demo-api
  -> Yandex AI Studio saved agent contractor-check-agent
     -> contractor-check-mcp
        -> get-report-by-inn
        -> search-contractors
        -> compare-contractors
     -> Web Search
  -> contractor-reports Object Storage dataset
```

The inspected deployment snapshot, runtime parameters and security boundaries are documented in
[`docs/07_deployed_architecture.md`](docs/07_deployed_architecture.md).

## Regression dashboard

The dashboard runs 59 scored scenarios across 27 dialogue chains, evaluates
every answer with an independent LLM judge, stores raw and manual reviews, and
calculates the release gate metrics.

Local setup and deployment instructions are in
[`apps/regression-dashboard/README.md`](apps/regression-dashboard/README.md).

## Documentation

- [Client problem and value](docs/01_client_problem_and_value.md)
- [MVP and product decisions](docs/02_mvp_and_product_decisions.md)
- [Hypotheses and evaluation](docs/03_hypotheses_evaluation_and_pilot.md)
- [Frozen AI test cases](docs/04_ai_evaluation_test_cases.md)
- [Engineering specification](docs/05_engineering_spec_mvp.md)
- [Agent and prompt requirements](docs/06_agent_prompt_spec.md)
- [Deployed architecture snapshot](docs/07_deployed_architecture.md)
- [Live AI Studio configuration](prompts/agent-live-config.md)

## Team

| Member | Role |
|---|---|
| Andrey Kopylov | AI Product |
| Sergey Shcherbakov | AI Engineer |
| Alexander Chernykh | AI Engineer |

## Security

Do not commit API keys, database URLs, Lockbox values, service-account keys,
AWS-compatible credentials, the private contractor dataset, raw credentials,
or local `.env` files. The browser-facing UI must call the backend proxy rather
than receive a Yandex API key directly.
