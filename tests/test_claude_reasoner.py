"""ClaudeReasoner with a stubbed client: schema constraints, parsing, and fallback."""
import json
from types import SimpleNamespace

import pytest

anthropic = pytest.importorskip("anthropic")

from agents.connectors.local import LocalITSM, SyntheticLogAnalytics, MockAutomation  # noqa: E402
from agents.orchestrator import TriageOrchestrator  # noqa: E402
from agents.reasoner import ClaudeReasoner  # noqa: E402


class FakeMessages:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    def create(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(self.reply))],
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5))


def _reasoner(monkeypatch, fake):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    itsm = LocalITSM()
    r = ClaudeReasoner(itsm.groups(), [k.title for k in itsm.kb_articles()])
    r.client = SimpleNamespace(beta=SimpleNamespace(messages=fake))
    return itsm, r


def test_claude_decision_is_parsed_and_constrained(monkeypatch):
    fake = FakeMessages(reply={"assignment_group": "SKR Backup & DR", "is_noise": False,
                               "kb_article": "Azure Backup job failures - common error codes",
                               "root_cause": "Transient snapshot extension failure", "related_change": "NONE",
                               "related_problem": "NONE", "confidence": 0.9, "rationale": "matches"})
    itsm, r = _reasoner(monkeypatch, fake)
    orch = TriageOrchestrator(itsm, SyntheticLogAnalytics(itsm), MockAutomation(), reasoner=r, update_tickets=False)
    res = orch.triage(itsm.open_incidents()[1])
    kw = fake.calls[0]
    assert kw["model"] == "claude-opus-5-5"
    schema = kw["output_config"]["format"]["schema"]
    assert "SKR Backup & DR" in schema["properties"]["assignment_group"]["enum"]
    assert schema["properties"]["related_change"]["enum"][-1] == "NONE"
    assert res.decision.related_change is None and res.decision.reasoner == "claude-opus-5-5"
    assert res.remediation.runbook == "RB-Backup-Retry"      # runbook comes from the KB, not the model


def test_falls_back_to_heuristic_on_api_error(monkeypatch):
    err = anthropic.APIConnectionError(request=SimpleNamespace(method="POST", url="x"))
    itsm, r = _reasoner(monkeypatch, FakeMessages(error=err))
    orch = TriageOrchestrator(itsm, SyntheticLogAnalytics(itsm), MockAutomation(), reasoner=r, update_tickets=False)
    res = orch.triage(itsm.open_incidents()[1])
    assert res.decision.reasoner == "heuristic" and "Claude unavailable" in res.decision.rationale
