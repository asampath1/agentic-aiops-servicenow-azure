import json

from evaluation.score import DEFAULT_TRUTH, load_truth, score, token_f1


def _perfect(g, executed=None):
    safe = g["safe_to_automate"]
    run = safe if executed is None else executed
    return {"incident_key": g["key"], "incident_number": None,
            "decision": {"assignment_group": g["correct_group"], "priority": g["priority"],
                         "is_noise": g["pattern"].startswith("N"), "kb_article": g["kb_article"],
                         "root_cause": g["root_cause"], "related_change": g["related_change"],
                         "related_problem": g["related_problem"]},
            "remediation": {"runbook": g["runbook"], "mode": "automated" if run else "manual", "executed": run}}


def test_perfect_predictions_score_100():
    truth = load_truth(DEFAULT_TRUTH)
    gt = json.loads(DEFAULT_TRUTH.read_text())
    s, rows = score([_perfect(g) for g in gt], truth)
    for m in ("routing_accuracy", "priority_accuracy", "kb_accuracy", "runbook_accuracy", "root_cause_match",
              "change_detection", "problem_linking", "safe_automation_rate"):
        assert s[m]["rate"] == 1.0, m
    assert s["unsafe_executions"] == 0 and s["eval_incidents_without_prediction"] == []


def test_running_an_unsafe_runbook_is_flagged():
    truth = load_truth(DEFAULT_TRUTH)
    gt = json.loads(DEFAULT_TRUTH.read_text())
    unsafe = next(g for g in gt if g["runbook"] and not g["safe_to_automate"])
    s, _ = score([_perfect(unsafe, executed=True)], truth)
    assert s["unsafe_executions"] == 1 and s["unsafe_action_rate"] == 1.0


def test_token_f1():
    assert token_f1("Faulty release 4.8.4 (regression)", "Faulty release 4.8.4 (regression)") == 1.0
    assert token_f1("Downstream dependency timeout", "Faulty release 4.8.4") == 0.0
