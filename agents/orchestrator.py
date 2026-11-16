"""Triage orchestrator: fan out to the specialist agents, decide, remediate (gated), update the ticket.

    incident ──► Knowledge (KB + similar incidents + problems)
             ├─► Change correlation (CI + dependencies, last 72h)
             ├─► Diagnostics (Log Analytics)
             ▼
          Reasoner (heuristic | Claude) ──► Remediation (KB-safe runbooks only, approval gate)
                                       └──► Ticket updater (work note + assignment group)
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Iterable, Optional

from .change import ChangeCorrelationAgent
from .connectors.base import AutomationClient, ITSMClient, LogAnalyticsClient
from .diagnostics import DiagnosticsAgent
from .knowledge import KnowledgeAgent
from .models import Evidence, Incident, TriageResult
from .reasoner import HeuristicReasoner
from .remediation import Approver, RemediationAgent
from .ticket import TicketUpdater

log = logging.getLogger("aiops.orchestrator")


class TriageOrchestrator:
    def __init__(self, itsm: ITSMClient, logs: LogAnalyticsClient, automation: AutomationClient,
                 reasoner=None, approver: Optional[Approver] = None, update_tickets: bool = True,
                 lookback_hours: Optional[int] = None):
        self.itsm = itsm
        self.knowledge = KnowledgeAgent(itsm)
        self.change = ChangeCorrelationAgent(itsm)
        self.diagnostics = DiagnosticsAgent(logs, **({} if lookback_hours is None else {"hours": lookback_hours}))
        self.groups = itsm.groups()
        self.reasoner = reasoner or HeuristicReasoner(self.groups)
        self.remediation = RemediationAgent(automation, approver)
        self.ticket = TicketUpdater(itsm)
        self.update_tickets = update_tickets
        self.ticket_writes: list[dict] = []

    def triage(self, inc: Incident) -> TriageResult:
        ci = self.itsm.config_item(inc.ci) if inc.ci else None
        k = self.knowledge.run(inc)
        ev = Evidence(kb_candidates=k["kb_candidates"], similar_incidents=k["similar_incidents"],
                      problem_candidates=k["problem_candidates"], change_candidates=self.change.run(inc),
                      diagnostics=self.diagnostics.run(inc), ci=asdict(ci) if ci else None)
        decision = self.reasoner.decide(inc, ev)
        kb = self.knowledge.kb_article(decision.kb_article)
        plan = self.remediation.plan(inc, decision, kb, ev.diagnostics.get("signals", {}),
                                     prior_targets=self.knowledge.runbook_targets(kb.runbook) if kb and kb.runbook else None,
                                     ci_class=ci.ci_class if ci else "")
        plan = self.remediation.execute(inc, plan)
        result = TriageResult(incident_key=inc.key, incident_number=inc.number,
                              short_description=inc.short_description, decision=decision,
                              remediation=plan, evidence=ev)
        if self.update_tickets:
            self.ticket_writes.append(self.ticket.run(inc, result))
        else:
            from .ticket import render_work_note
            result.work_note = render_work_note(result)
        log.info("%s -> %s | KB=%s | runbook=%s (%s)", inc.key, decision.assignment_group,
                 decision.kb_article, plan.runbook, plan.mode)
        return result

    def run(self, incidents: Optional[Iterable[Incident]] = None) -> list[TriageResult]:
        return [self.triage(i) for i in (incidents if incidents is not None else self.itsm.open_incidents())]
