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
- Done (2026-11-15): Azure Phase 2: Automation account `aa-skr-aiops` in Southeast Asia (trial can't create Automation in
  Central India), custom role (VM read + Run Command, RG only), runbooks published via `infra/publish-runbooks.sh`.
  Verified through `agents.connectors.azure.AzureAutomation`: cleanup job Completed; restart job refused `sshd`.
- Done (2026-11-16): Azure Phase 3: `infra/alerts.bicep` (deployed by the user from VS Code with SN creds): alert rules
  `vm-cpu-high` / `vm-disk-low` -> `ag-skr-servicenow` -> Logic App `la-skr-alert-to-snow` -> PDI incident tagged
  `correlation_id=SYNTH-SKR-LIVE` (alert id in `correlation_display`). Tested with a crafted Fired + Resolved payload:
  created INC0010597 (CI + caller resolved) and added the resolved work note. INC0010597 is a test incident.
- Done (2026-11-16): Azure Phase 4, first live loop (CPU): `infra/faults/inject.sh cpu` -> `vm-cpu-high` fired 06:42Z ->
  INC0010598 -> `--live --telemetry azure --automation azure --approver interactive --write` (KB high CPU, `python3`
  from real Syslog, RB-VM-Restart-Service approved) -> runaway stopped -> alert resolved 06:55Z -> resolved work note.
  The first job "Completed" while its bash failed (PowerShell quoting); fixed, and runbooks now FAIL on any stderr.
- Done (2026-11-16): auto-resolve. `--live --write` sets live incidents In Progress (eval set stays New). On a cleared
  alert the Logic App (managed identity, Reader on the Automation account) resolves the incident only if a Completed
  runbook job with that IncidentNumber started after the alert fired: state Resolved, close code
  `Auto-remediated (AIOps)` (choice added by `infra/servicenow/add_close_code.py`); otherwise a "needs review" note.
  Verified: INC0010598 (CPU, replayed resolved alert) and INC0010599 (disk, fully live: fired ~08:10Z, cleanup job,
  cleared 08:35Z, auto-resolved). Phase 4 complete.
- Open findings: live root cause for the CPU run was "Batch job overlapping with peak traffic" (history vote; "Runaway
  python3 process" fits); `http_status` signal regex matches Perf numbers (e.g. 526 MB); Diagnostics' 24 h lookback
  carried the CPU fault's `python3` Syslog line into the disk proposal (ServiceName, harmless for cleanup); resolved log
  alerts carry no measured value, so close notes show "(Log query result: )".
- Next: tidy the findings above; README/portfolio write-up of the live demo.
  Phase 4 fixes: Diagnostics KQL uses `Available MBytes` (Linux reports `Available MBytes Memory`) and needs Syslog
  for the process name (Linux Perf has no per-process data).
