# Project context for Claude

Portfolio project: multi-agent AI triage for a fictional retailer, ShopKart Retails (SKR), on Azure + a
ServiceNow Personal Developer Instance (PDI). All data is synthetic (tag `SYNTH-SKR`).

## Layout
- `synthetic-data/` dataset generator, CSVs, `load_plan.json`, `load_to_snow.py` (ServiceNow loader)
- `agents/` triage orchestrator + Knowledge, Change, Diagnostics, Remediation, Ticket agents; connectors in
  `agents/connectors/` (local CSV / ServiceNow / Azure). See `agents/README.md`.
- `evaluation/score.py` scores a run against `synthetic-data/data/ground_truth.json`. See `evaluation/README.md`.
- `tests/` pytest suite (`python -m pytest -q`)

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
- `data/manifest.json` and `ground_truth.loaded.json` are local loader state (gitignored).

## Status (2026-11-12)
- Done: dataset loaded into the PDI (612 records); offline heuristic baseline 24/24 routing, 0 unsafe actions.
- Next: re-run triage against the live PDI and compare with the offline baseline; then `--write` work notes;
  then the Claude reasoner run; then the Azure side (Log Analytics workspace, VMs named like the CMDB CIs,
  Automation account with the safe runbooks, alert rule -> ServiceNow).
