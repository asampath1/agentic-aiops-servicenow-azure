"""Run the triage orchestrator over the open incidents.

Offline (default, no credentials):
    python -m agents --out runs/latest

With Claude as the reasoner (needs ANTHROPIC_API_KEY or `ant auth login`):
    python -m agents --reasoner claude --out runs/claude

Against the live PDI + Azure (dry-run writes unless --write):
    python -m agents --source servicenow --telemetry azure --automation azure --out runs/pdi
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .connectors.local import DEFAULT_DATA_DIR, LocalITSM, MockAutomation, SyntheticLogAnalytics
from .orchestrator import TriageOrchestrator
from .reasoner import ClaudeReasoner, HeuristicReasoner
from .remediation import DenyAll, InteractiveApprover, SimulatedApprover


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m agents", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["local", "servicenow"], default="local")
    ap.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="synthetic dataset folder (local source)")
    ap.add_argument("--telemetry", choices=["synthetic", "azure"], default="synthetic")
    ap.add_argument("--automation", choices=["mock", "azure"], default="mock")
    ap.add_argument("--reasoner", choices=["heuristic", "claude"], default="heuristic")
    ap.add_argument("--model", default=None, help="Claude model id (default claude-opus-5-5)")
    ap.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--approver", choices=["deny", "simulate", "interactive"], default="simulate",
                    help="who approves runbooks. 'simulate' approves every proposal (worst case for safety "
                         "scoring) and is only allowed with --automation mock")
    ap.add_argument("--write", action="store_true", help="actually PATCH ServiceNow (servicenow source only)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=None, help="output folder (default runs/<timestamp>)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(message)s")

    if a.approver == "simulate" and a.automation != "mock":
        ap.error("--approver simulate is only allowed with --automation mock")
    if a.write and a.approver == "simulate":
        ap.error("--write with --approver simulate would record approvals nobody gave; "
                 "use --approver deny (proposals only) or interactive")

    out = Path(a.out or f"runs/{datetime.now(timezone.utc):%Y%m%d-%H%M%S}")
    out.mkdir(parents=True, exist_ok=True)

    if a.source == "local":
        itsm = LocalITSM(a.data_dir, outbox=out / "ticket_updates.jsonl")
    else:
        from .connectors.servicenow import ServiceNowITSM
        itsm = ServiceNowITSM(write=a.write)

    if a.telemetry == "synthetic":
        # Works with either source: the stand-in workspace is built from the alert payloads in the incidents.
        logs = SyntheticLogAnalytics(itsm)
    else:
        from .connectors.azure import AzureLogAnalytics
        logs = AzureLogAnalytics()

    if a.automation == "mock":
        automation = MockAutomation()
    else:
        from .connectors.azure import AzureAutomation
        automation = AzureAutomation()

    approver = {"deny": DenyAll, "simulate": SimulatedApprover, "interactive": InteractiveApprover}[a.approver]()
    groups = itsm.groups()
    if a.reasoner == "claude":
        reasoner = ClaudeReasoner(groups, [k.title for k in itsm.kb_articles()], model=a.model, effort=a.effort,
                                  fallback=HeuristicReasoner(groups))
    else:
        reasoner = HeuristicReasoner(groups)

    orch = TriageOrchestrator(itsm, logs, automation, reasoner=reasoner, approver=approver)
    incidents = itsm.open_incidents()[: a.limit]
    print(f"Source {a.source}: {len(incidents)} open incidents, {len(orch.knowledge.history)} resolved incidents, "
          f"{len(orch.knowledge.kb)} KB articles, {len(orch.knowledge.problems)} problems, {len(groups)} groups")
    if not orch.knowledge.kb or not orch.knowledge.history:
        print("WARNING: no KB articles or no resolved incidents found - triage will be poor. Check the source data.")
    results = orch.run(incidents)

    preds = [r.to_dict() for r in results]
    (out / "predictions.json").write_text(json.dumps(preds, indent=1, default=list))
    (out / "automation_jobs.json").write_text(json.dumps(getattr(automation, "jobs", []), indent=1))
    if a.source != "local":
        (out / "ticket_updates.json").write_text(json.dumps(orch.ticket_writes, indent=1))
    meta = {"source": a.source, "telemetry": a.telemetry, "automation": a.automation, "reasoner": a.reasoner,
            "model": getattr(reasoner, "model", None), "effort": a.effort if a.reasoner == "claude" else None,
            "approver": a.approver, "incidents": len(results), "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "llm_usage": getattr(reasoner, "usage", None)}
    (out / "run.json").write_text(json.dumps(meta, indent=1))

    for r in results:
        d, rem = r.decision, r.remediation
        print(f"{r.incident_key:10} {d.assignment_group:36} P{d.priority}  {(rem.runbook or '-'):28} "
              f"{rem.mode:9} {'RAN' if rem.executed else ''}")
    print(f"\n{len(results)} incidents triaged -> {out}/predictions.json")
    print(f"Score with: python -m evaluation.score {out}/predictions.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
