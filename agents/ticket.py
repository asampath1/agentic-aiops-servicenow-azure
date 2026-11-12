"""Ticket updater: write the triage outcome back to the incident as a work note."""
from __future__ import annotations

from typing import Any

from .connectors.base import ITSMClient
from .models import Incident, TriageResult


def render_work_note(r: TriageResult) -> str:
    d, rem, ev = r.decision, r.remediation, r.evidence
    lines = [f"[AIOps triage] reasoner={d.reasoner} confidence={d.confidence:.2f}",
             f"Assignment group: {d.assignment_group}" + (" (end-user / service desk)" if d.is_noise else ""),
             f"Priority (impact x urgency): P{d.priority}",
             f"Probable root cause: {d.root_cause}"]
    if d.kb_article:
        lines.append(f"KB: {d.kb_article}")
    if d.related_change:
        c = next((c for c in ev.change_candidates if c["key"] == d.related_change), None)
        when = f", {c['hours_before_incident']}h before the incident" if c else ""
        lines.append(f"Suspected change: {c['number'] or c['key'] if c else d.related_change}{when} - please confirm and set Caused by Change")
    if d.related_problem:
        lines.append(f"Matches known error: {d.related_problem} - please link the problem record")
    if ev.diagnostics.get("ran"):
        lines.append(f"Log Analytics: {ev.diagnostics.get('row_count', 0)} rows; signals {ev.diagnostics.get('signals')}")
    if rem.mode == "automated":
        if rem.executed and (rem.job or {}).get("simulated"):
            status = f"SIMULATED run only (mock automation, nothing changed), job {rem.job['job_id']}"
        elif rem.executed:
            status = "EXECUTED job " + rem.job["job_id"]
        else:
            status = f"awaiting approval ({(rem.approval or {}).get('reason', 'pending')})"
        lines.append(f"Remediation: runbook {rem.runbook} proposed, {status}")
    elif rem.mode == "manual":
        lines.append(f"Remediation: manual, follow {rem.runbook} ({rem.reason})")
    if ev.similar_incidents:
        refs = ", ".join(s["number"] or s["key"] for s in ev.similar_incidents[:3])
        lines.append(f"Similar resolved incidents: {refs}")
    lines.append(f"Rationale: {d.rationale}")
    return "\n".join(lines)


class TicketUpdater:
    name = "ticket"

    def __init__(self, itsm: ITSMClient):
        self.itsm = itsm

    def run(self, inc: Incident, result: TriageResult) -> dict[str, Any]:
        note = render_work_note(result)
        result.work_note = note
        return self.itsm.update_incident(inc, {"assignment_group": result.decision.assignment_group}, note)
