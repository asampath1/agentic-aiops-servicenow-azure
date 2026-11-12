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


def test_runbook_not_automated_on_a_target_it_never_ran_on():
    # inc:0312 on the PDI: an IIS recycle (only ever run on Windows VMs) chosen for an App Service.
    agent = RemediationAgent(MockAutomation(), SimulatedApprover())
    history = {"vm-ecom-web-01", "vm-ecom-web-02", "cmdb_ci_win_server"}
    plan = agent.execute(_inc("app-ecom-api-prod"),
                         agent.plan(_inc("app-ecom-api-prod"), _dec(), SAFE, {}, prior_targets=history,
                                    ci_class="cmdb_ci_appl"))
    assert plan.mode == "manual" and not plan.executed and "no prior use" in plan.reason
    never_used = agent.plan(_inc(), _dec(), SAFE, {}, prior_targets=set(), ci_class="cmdb_ci_win_server")
    assert never_used.mode == "manual"


def test_runbook_automated_on_same_ci_or_same_class():
    agent = RemediationAgent(MockAutomation(), SimulatedApprover())
    history = {"vm-ecom-web-01", "cmdb_ci_win_server"}
    assert agent.plan(_inc("vm-ecom-web-01"), _dec(), SAFE, {}, prior_targets=history).mode == "automated"
    assert agent.plan(_inc("vm-hr-batch-01"), _dec(), SAFE, {}, prior_targets=history,
                      ci_class="cmdb_ci_win_server").mode == "automated"


def test_work_note_never_claims_a_simulated_job_executed():
    from agents.models import Evidence, RemediationPlan, TriageResult
    from agents.ticket import render_work_note
    plan = RemediationPlan(runbook="RB-Safe", mode="automated", safe_to_automate=True, executed=True,
                           job={"job_id": "j1", "simulated": True})
    note = render_work_note(TriageResult(incident_key="inc:x", incident_number=None, short_description="t",
                                         decision=_dec(), remediation=plan,
                                         evidence=Evidence(kb_candidates=[], similar_incidents=[],
                                                           problem_candidates=[], change_candidates=[],
                                                           diagnostics={}, ci=None)))
    assert "SIMULATED" in note and "EXECUTED" not in note


def test_write_refuses_simulated_approver():
    import pytest
    from agents.__main__ import main
    with pytest.raises(SystemExit):
        main(["--source", "servicenow", "--write", "--approver", "simulate", "--automation", "mock"])
