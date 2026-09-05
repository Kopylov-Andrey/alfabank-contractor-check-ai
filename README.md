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
  product-ui/              Main end-user interface
  regression-dashboard/   Automated evaluation and quality dashboard
services/
  mcp-functions/           Yandex Cloud Functions exposed through MCP
prompts/                   Versioned agent system prompts
evals/                     Frozen evaluation artifacts and run results
docs/                      Product, MVP, evaluation and engineering documents
presentation/              Final pitch deck and demo materials
.github/workflows/         CI and deployment verification
```

## Current status

| Component | Status |
|---|---|
| Agent in Yandex AI Studio | Implemented |
| MCP tools | Implemented in Yandex Cloud; source code pending import |
| Product UI | Pending import |
| Regression dashboard | Implemented |
| Frozen evaluation suite | 40 main + 16 repeats + 3 Web Search scenarios |
| Production deployment | Pending configuration |

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

## Team

| Member | Role |
|---|---|
| Andrey Kopylov | AI Product |
| Sergey Shcherbakov | AI Engineer |
| Alexander Chernykh | AI Engineer |

## Security

Do not commit API keys, database URLs, Lockbox values, service-account keys,
raw credentials, or local `.env` files. Public access to regression results is
read-only; runs and manual reviews require an admin token.

