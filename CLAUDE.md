# Project context for Claude

Portfolio project: multi-agent AI triage for a fictional retailer, ShopKart Retails (SKR), on Azure + a
ServiceNow Personal Developer Instance (PDI). All data is synthetic (tag `SYNTH-SKR`).

## Layout
- `synthetic-data/` dataset generator, CSVs, `load_plan.json`, `load_to_snow.py` (ServiceNow loader)
- `agents/` triage orchestrator + Knowledge, Change, Diagnostics, Remediation, Ticket agents; connectors in
  `agents/connectors/` (local CSV / ServiceNow / Azure). See `agents/README.md`.
- `evaluation/score.py` scores a run against `synthetic-data/data/ground_truth.json`. See `evaluation/README.md`.
- `tests/` pytest suite (`python -m pytest -q`)
- `infra/` Bicep for the live Azure demo (subscription-scope `main.bicep` + `modules/demo.bicep`). See `infra/README.md`.

## Hard rules
- Agents must never read `ground_truth.json` (or `ground_truth.loaded.json`). Only `evaluation/score.py` may.
  `tests/test_answer_key_isolation.py` enforces this.
- Open eval incidents are redacted before agents see them (assignment group, caused_by, problem_id, notes).
- Runbooks come only from KB articles; "do NOT auto-run" runbooks are never automated; nothing runs without approval.
- ServiceNow writes are dry-run unless `--write` is passed.
- Claude via the Anthropic API defaults to `claude-opus-5-5` (`--reasoner claude`).

## Commands (run from the repo root)
```bash
python -m agents --out runs/latest && python -m evaluation.score runs/latest/predictions.json     # offline
python -m agents --source servicenow --telemetry synthetic --automation mock --approver simulate --out runs/pdi -v
python -m evaluation.score runs/pdi/predictions.json --truth synthetic-data/data/ground_truth.loaded.json
cd synthetic-data && python3 load_to_snow.py --check                                              # PDI login test
```

## Environment
- PDI credentials: env vars `SN_INSTANCE` (bare name, e.g. dev123456), `SN_USER`, `SN_PASSWORD`.
  Use the API-only user `svc.aiops.loader` (identity type Machine, admin role); the browser admin login
  gets 401 on the REST API on this PDI. Never commit credentials.
- The PDI's assignment rules pre-fill the assignment group from the CI on new incidents, and KB articles
  may stay in Draft after insert; the ServiceNow connector accounts for both.
- This PDI's incident table has no `problem_id` / `caused_by` fields (writes to them are silently dropped).
  `load_to_snow.py --relink` creates `u_problem_id` / `u_caused_by` and patches the links; the connector reads
  either name. KB HTML on the PDI is entity-escaped (`&amp;`); `kb_parse` unescapes it.
- `data/manifest.json` and `ground_truth.loaded.json` are local loader state (gitignored).
- Azure: free-trial subscription `sub-skr-aiops-demo` (spending limit on, 4 vCPU per region), region Central India.
  The trial is blocked from B1s/B2s; B2ats_v2 / B2als_v2 work only non-zonal. `az login --use-device-code`.
  Everything lives in `rg-skr-aiops-demo`; `az group delete -n rg-skr-aiops-demo` is the teardown.
  The 24-incident eval stays on synthetic telemetry; Azure is a live end-to-end demo of single alerts.

## Status (2026-11-12)
- Done: dataset loaded into the PDI (612 records); offline heuristic baseline 24/24 routing, 0 unsafe actions.
- Done: live PDI triage matches the offline baseline on all 24 incidents (24/24 routing, 22/22 KB, 5/5 problems,
  root cause 21/24, 13/13 safe auto-remediation, 0 unsafe). Root cause was 22/24 before retrieval ties were made
  deterministic; inc:0302 was right by row-order luck (history majority favours the wrong cause).
- Done: `--write` work notes posted to all 24 open eval incidents (`--approver deny`, 24x HTTP 200; also sets the
  assignment group). Work notes are a journal: another `--write` run adds a second note to every ticket.
  `--write` refuses `--approver simulate`; simulated jobs are labelled SIMULATED in notes.
- Deferred (2026-11-15): the live Claude reasoner run, until an Anthropic API key is bought. Code + stub tests are ready
  (`python -m agents --reasoner claude --out runs/claude -v`, ~$1-2, no `--write`).
- Done (2026-11-15): Azure Phase 1 deployed: workspace `law-skr-aiops`, `vm-orders-app-01` (Ubuntu, B2ats_v2, no public
  IP, AMA + DCR for Perf/Syslog/Heartbeat, auto-shutdown 22:00 IST). Linux only; the Windows/IIS scenario was dropped
  to save credit.
- Next: Phase 2 Automation account + `RB-VM-Restart-Service` / `RB-VM-Cleanup-Disk`; Phase 3 alerts -> Logic App ->
  ServiceNow; Phase 4 fault scripts + `--telemetry azure --automation azure` run.
