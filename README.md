# agentic-aiops-servicenow-azure

Multi-agent AI that triages, diagnoses and remediates Azure incidents in ServiceNow, with
human-in-the-loop approval. The repo includes a synthetic enterprise dataset and an evaluation set.

> **Disclaimer:** *ShopKart Retails (SKR)* is a fictional company. All people, emails, IPs, systems and
> tickets in this repo are synthetic. No client or employer data is used.

## Why this project

IT managed-services work is shifting from people working tickets to AI-run operations that are
accountable for outcomes. This project shows that shift end to end on a realistic Azure + ServiceNow estate:

- **Faster triage.** Each incident is routed to the right resolver group with the right priority.
- **Root cause with evidence.** The system uses similar past incidents, KB articles, recent changes and Azure telemetry.
- **Safe automation.** Runbooks run only when the KB marks them safe, and only after a person approves.
- **Measured results.** Everything is scored against a labelled evaluation set, not demo anecdotes.

## Architecture

```mermaid
flowchart TD
    SN[ServiceNow PDI<br/>incidents, KB, changes, CMDB] --> O[Triage orchestrator<br/>classify, route, plan]
    O --> K[Knowledge agent<br/>RAG over KB + resolved incidents]
    O --> C[Change agent<br/>recent changes on CI]
    O --> D[Diagnostics agent<br/>Azure Monitor / Log Analytics]
    O --> R[Remediation agent<br/>Azure Automation runbooks]
    R --> H{Human approval}
    H -->|approved| AZ[Azure]
    D <--> AZ
    O --> U[Ticket updater<br/>work notes, resolution back to SNOW]
```

## Repo layout

```
synthetic-data/      ShopKart Retails ITSM dataset generator + ServiceNow loader (start here)
agents/              triage orchestrator, specialist agents, ServiceNow/Azure connectors (offline mocks included)
evaluation/          scoring against synthetic-data/data/ground_truth.json, plus committed results
tests/               pytest suite, including answer-key isolation and remediation safety
docs/                (planned) design notes, demo screenshots
```

## Roadmap

- [x] Synthetic enterprise data: 300+ incidents, CMDB, KB, changes, problems, and a 24-incident eval set
- [ ] Load data into a ServiceNow PDI
- [x] Triage orchestrator (routing + priority), heuristic and Claude reasoners
- [x] Knowledge agent (BM25 over KB and resolved incidents; swap for vector search later)
- [x] Change-correlation agent
- [x] Diagnostics agent (KQL per resource type; synthetic workspace offline, Log Analytics connector for live)
- [x] Remediation agent with approval gate (Azure Automation connector, KB-safe runbooks only)
- [x] Evaluation scoring: routing, KB, runbook, root-cause match, change/problem linking, unsafe-action rate
- [ ] Run against the live PDI and a free-tier Log Analytics workspace
- [ ] Claude reasoner vs heuristic comparison on the eval set
- [ ] MTTR saved (needs live timings)
- [ ] Demo video

## Quick start

```bash
cd synthetic-data
pip install requests
python3 generate_data.py
export SN_INSTANCE=devXXXXXX SN_USER=admin SN_PASSWORD='...'
python3 load_to_snow.py --dry-run && python3 load_to_snow.py
```

See [synthetic-data/README.md](synthetic-data/README.md) for details.

### Triage and score (offline, no credentials)

```bash
python -m agents --out runs/latest          # triage the 24 open incidents
python -m evaluation.score runs/latest/predictions.json
pip install pytest && python -m pytest -q
```

Baseline results: [evaluation/README.md](evaluation/README.md). How the agents work, the live
ServiceNow / Azure / Claude options and the guardrails: [agents/README.md](agents/README.md).
