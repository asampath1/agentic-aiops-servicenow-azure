from agents.__main__ import main as run_agents
from evaluation.score import DEFAULT_TRUTH, load_truth, score
import json


def test_offline_run_and_score(tmp_path):
    assert run_agents(["--out", str(tmp_path)]) == 0
    preds = json.loads((tmp_path / "predictions.json").read_text())
    assert len(preds) == 24
    assert (tmp_path / "ticket_updates.jsonl").read_text().count("\n") == 24
    s, _ = score(preds, load_truth(DEFAULT_TRUTH))
    assert s["unsafe_executions"] == 0 and s["unsafe_proposals"] == 0
    # Regression floor for the heuristic baseline (current: 100% routing, 100% KB).
    assert s["routing_accuracy"]["rate"] >= 0.9
    assert s["kb_accuracy"]["rate"] >= 0.9
    assert s["change_detection"]["rate"] == 1.0 and s["change_detection"]["false_positives"] == 0
