"""Remediation agent with a human approval gate.

Policy (enforced in code, not by any model):
1. A runbook is only ever taken from the matched KB article, never generated.
2. Only runbooks the KB marks "safe to run automatically" can be proposed for automation.
   Everything else becomes a manual recommendation for the resolver group.
3. Noise tickets, missing CIs and low-confidence triage never get automation.
4. A runbook is only automated on a target it has been used on before: the same CI, or a CI of the
   same class (e.g. an IIS recycle that only ever ran on Windows VMs is not auto-run on an App Service).
5. Nothing runs without an ``Approver`` returning approved=True.
"""
from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from .connectors.base import AutomationClient
from .models import Incident, KBArticle, RemediationPlan, TriageDecision


class Approver(ABC):
    @abstractmethod
    def review(self, inc: Incident, plan: RemediationPlan) -> dict[str, Any]:
        """Return {"approved": bool, "approver": str, "reason": str}."""


class DenyAll(Approver):
    """Default: propose only. A person approves in ServiceNow / Teams later."""

    def review(self, inc, plan):
        return {"approved": False, "approver": "policy:deny-all", "reason": "no approver configured; proposal only"}


class SimulatedApprover(Approver):
    """Evaluation only: stands in for an engineer who approves every proposal.

    Scoring with this approver measures the worst case: if the agent ever proposes an unsafe
    or wrong runbook, it would have run.
    """

    def review(self, inc, plan):
        return {"approved": True, "approver": "simulated-engineer", "reason": "eval: approve every proposal"}


class InteractiveApprover(Approver):
    def review(self, inc, plan):
        print(f"\n[{inc.key}] {inc.short_description}\n  Proposed runbook {plan.runbook} {plan.parameters}\n  {plan.reason}",
              file=sys.stderr)
        ans = input("  Approve? [y/N] ").strip().lower()
        return {"approved": ans == "y", "approver": "console-user", "reason": "approved at console" if ans == "y" else "declined"}


class RemediationAgent:
    name = "remediation"

    def __init__(self, automation: AutomationClient, approver: Approver | None = None, min_confidence: float = 0.5):
        self.automation = automation
        self.approver = approver or DenyAll()
        self.min_confidence = min_confidence

    def plan(self, inc: Incident, decision: TriageDecision, kb: Optional[KBArticle],
             signals: dict[str, list[str]], prior_targets: Optional[set[str]] = None,
             ci_class: str = "") -> RemediationPlan:
        """``prior_targets``: CI names and classes this runbook was used on in past incidents
        (``None`` skips the check, e.g. when no history is available)."""
        if decision.is_noise or not kb or not kb.runbook:
            return RemediationPlan(runbook=None, mode="none", safe_to_automate=False,
                                   reason="no runbook applies (end-user issue or no KB runbook)")
        params: dict[str, Any] = {"ResourceName": inc.ci, "IncidentNumber": inc.number or inc.key}
        if signals.get("process"):
            params["ServiceName"] = signals["process"][0]
        if not kb.safe_to_automate:
            return RemediationPlan(runbook=kb.runbook, mode="manual", safe_to_automate=False, parameters=params,
                                   reason=f"KB '{kb.title}' marks {kb.runbook} as manual / do not auto-run")
        if not inc.ci:
            return RemediationPlan(runbook=kb.runbook, mode="manual", safe_to_automate=True, parameters=params,
                                   reason="no CI on the incident to target")
        if decision.confidence < self.min_confidence:
            return RemediationPlan(runbook=kb.runbook, mode="manual", safe_to_automate=True, parameters=params,
                                   reason=f"triage confidence {decision.confidence:.2f} < {self.min_confidence}")
        if prior_targets is not None and inc.ci not in prior_targets and not (ci_class and ci_class in prior_targets):
            target = f"{inc.ci}" + (f" or any {ci_class}" if ci_class else "")
            return RemediationPlan(runbook=kb.runbook, mode="manual", safe_to_automate=True, parameters=params,
                                   reason=f"{kb.runbook} has no prior use on {target} in incident history")
        return RemediationPlan(runbook=kb.runbook, mode="automated", safe_to_automate=True, parameters=params,
                               reason=f"KB '{kb.title}' marks {kb.runbook} safe to run with approval")

    def execute(self, inc: Incident, plan: RemediationPlan) -> RemediationPlan:
        if plan.mode != "automated":
            return plan
        decision = self.approver.review(inc, plan)
        decision["at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        plan.approval = decision
        if decision.get("approved"):
            plan.job = self.automation.start_runbook(plan.runbook, plan.parameters)
            plan.executed = True
        return plan
