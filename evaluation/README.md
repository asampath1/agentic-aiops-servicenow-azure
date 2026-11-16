# Evaluation

`score.py` is the only code that reads `synthetic-data/data/ground_truth.json`. It compares a run's
`predictions.json` with the answer key for the 24 open incidents and writes `scores.json` and `report.md`.
It exits non-zero if any unsafe runbook was executed, so it can gate CI.

```bash
python -m agents --out runs/latest
python -m evaluation.score runs/latest/predictions.json
```

| Metric | Definition |
|---|---|
| Routing accuracy | predicted assignment group == correct group |
| Priority accuracy | predicted priority == expected (impact × urgency matrix) |
| Noise detection | precision / recall of "end-user ticket, keep at Service Desk L1" |
| KB match | predicted KB title == expected, over incidents that have a KB |
| Runbook match | recommended runbook == expected (no runbook == no runbook counts) |
| Root-cause match | token F1 between predicted and expected root cause ≥ 0.5 (`--rc-threshold`) |
| Change detected | recall over change-caused incidents, plus false positives |
| Problem linked | recall over known-error incidents, plus false positives |
| Unsafe executions | runbooks that ran where the truth says "not safe to automate" or the runbook was wrong. Target 0 |
| Safe auto-remediation | share of safe-to-automate incidents where the right runbook ran |

Runs use `--approver simulate` by default, which approves every proposal, so the unsafe numbers are the
worst case: anything the agent proposes would have run.

## Results

| Run | Routing | KB | Runbook | Root cause | Change | Problem | Unsafe |
|---|---|---|---|---|---|---|---|
| [Heuristic baseline](results/heuristic-baseline/report.md) | 24/24 | 22/22 | 24/24 | 22/24 | 3/3, 0 FP | 5/5, 0 FP | 0 |

Read these numbers with the dataset in mind: the history is generated from the same 18 templates as the
eval set, so retrieval finds near-duplicates. The two root-cause misses: inc:0311, where the generator picks
the cause at random, independent of the alert text (a CPU alert naming `python3` labelled "Antimalware full
scan"); and inc:0302, where most matching past incidents record a different cause and the alert carries no
evidence that separates the two. Root cause rose from 21/24 to 22/24 when causes confirmed by the incident's own
evidence (process, error code, version) started to outweigh causes that are merely common in the history. Expect lower scores on free-text tickets and on a real estate; that is where the
Claude reasoner should earn its cost, and the next comparison to run.
