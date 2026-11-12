from agents.models import Incident, KBArticle, TriageDecision
from agents.connectors.local import MockAutomation
from agents.remediation import DenyAll, RemediationAgent, SimulatedApprover


def _inc(ci="vm-ecom-web-01"):
    return Incident(key="inc:x", short_description="test", ci=ci)


def _dec(noise=False, conf=0.95):
    return TriageDecision(assignment_group="SKR Azure Infra Ops", priority=3, is_noise=noise,
                          kb_article="kb", root_cause="x", confidence=conf)


SAFE = KBArticle(key="kb1", title="kb", text="", runbook="RB-Safe", safe_to_automate=True)
UNSAFE = KBArticle(key="kb2", title="kb", text="", runbook="RB-Unsafe", safe_to_automate=False)


def test_unsafe_runbook_is_never_automated_even_if_everyone_approves():
    auto = MockAutomation()
    agent = RemediationAgent(auto, SimulatedApprover())
    plan = agent.execute(_inc(), agent.plan(_inc(), _dec(), UNSAFE, {}))
    assert plan.mode == "manual" and not plan.executed and auto.jobs == []


def test_safe_runbook_runs_only_after_approval():
    auto = MockAutomation()
    denied = RemediationAgent(auto, DenyAll())
    plan = denied.execute(_inc(), denied.plan(_inc(), _dec(), SAFE, {}))
    assert plan.mode == "automated" and not plan.executed and auto.jobs == []
    approved = RemediationAgent(auto, SimulatedApprover())
    plan = approved.execute(_inc(), approved.plan(_inc(), _dec(), SAFE, {"process": ["w3wp.exe"]}))
    assert plan.executed and auto.jobs[0]["runbook"] == "RB-Safe"
    assert auto.jobs[0]["parameters"]["ServiceName"] == "w3wp.exe"


def test_noise_low_confidence_and_missing_ci_are_not_automated():
    agent = RemediationAgent(MockAutomation(), SimulatedApprover())
    assert agent.plan(_inc(), _dec(noise=True), SAFE, {}).mode == "none"
    assert agent.plan(_inc(), _dec(conf=0.1), SAFE, {}).mode == "manual"
    assert agent.plan(_inc(ci=None), _dec(), SAFE, {}).mode == "manual"
