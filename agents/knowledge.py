"""Knowledge agent: RAG over KB articles, resolved incidents and known-error problems."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Optional

from .connectors.base import ITSMClient
from .models import Incident, KBArticle, Problem
from .retrieval import BM25

_ROOT = re.compile(r"Root cause:\s*(.+?)\.?\s*$", re.M)
_RB = re.compile(r"\b(RB-[A-Za-z0-9-]+)")


def root_cause_of(inc: Incident) -> Optional[str]:
    m = _ROOT.search(inc.work_notes or "") or _ROOT.search(inc.close_notes or "")
    return m.group(1).strip().rstrip(".") if m else None


def runbook_of(inc: Incident) -> Optional[str]:
    m = _RB.search(inc.work_notes or "")
    return m.group(1) if m else None


class KnowledgeAgent:
    name = "knowledge"

    def __init__(self, itsm: ITSMClient, k_similar: int = 10):
        self.kb = itsm.kb_articles()
        self.kb_by_title = {a.title: a for a in self.kb}
        self.kb_by_runbook = {a.runbook: a for a in self.kb if a.runbook}
        self.history = itsm.resolved_incidents()
        self.problems: dict[str, Problem] = {p.key: p for p in itsm.problems()}
        self.k_similar = k_similar
        self._kb_index = BM25(self.kb, [f"{a.title} {a.title} {a.symptoms} {a.meta} {a.cause}" for a in self.kb])
        self._inc_index = BM25(self.history, [f"{i.short_description} {i.description}" for i in self.history])

    def kb_article(self, title: Optional[str]) -> Optional[KBArticle]:
        return self.kb_by_title.get(title) if title else None

    def run(self, inc: Incident) -> dict[str, Any]:
        query = inc.text + (f" {inc.ci}" if inc.ci else "")
        similar = []
        for h, s in self._inc_index.search(query, self.k_similar):
            rb = runbook_of(h)
            kb = self.kb_by_runbook.get(rb) if rb else None
            similar.append({"key": h.key, "number": h.number, "short_description": h.short_description,
                            "ci": h.ci, "assignment_group": h.assignment_group, "root_cause": root_cause_of(h),
                            "runbook": rb, "kb_article": kb.title if kb else None,
                            "change_caused": bool(h.caused_by), "problem": h.problem_id,
                            "resolution": (h.close_notes or "")[:240], "score": round(s, 3)})

        # KB ranking = direct BM25 match + votes from the runbooks used on similar past incidents.
        kb_scores: dict[str, float] = defaultdict(float)
        direct = self._kb_index.search(query, len(self.kb))
        top_direct = direct[0][1] if direct else 1.0
        for a, s in direct:
            kb_scores[a.title] += s / top_direct
        top_sim = similar[0]["score"] if similar else 1.0
        for s in similar:
            if s["kb_article"]:
                kb_scores[s["kb_article"]] += 0.5 * s["score"] / top_sim
        kb_candidates = []
        for title, sc in sorted(kb_scores.items(), key=lambda x: -x[1])[:5]:
            a = self.kb_by_title[title]
            kb_candidates.append({"title": title, "key": a.key, "score": round(sc, 3), "resolver_group": a.resolver_group,
                                  "runbook": a.runbook, "safe_to_automate": a.safe_to_automate,
                                  "symptoms": a.symptoms, "cause": a.cause})

        # Known-error problems seen on similar incidents, or recorded against this CI.
        pc: dict[str, dict[str, Any]] = {}
        for s in similar:
            if s["problem"]:
                d = pc.setdefault(s["problem"], {"votes": 0.0, "same_ci_votes": 0.0, "runbooks": set()})
                d["votes"] += s["score"] / top_sim
                d["same_ci_votes"] += (s["score"] / top_sim) if s["ci"] == inc.ci else 0.0
                if s["runbook"]:
                    d["runbooks"].add(s["runbook"])
        problem_candidates = []
        for key, p in self.problems.items():
            d = pc.get(key)
            if not d and p.ci != inc.ci:
                continue
            d = d or {"votes": 0.0, "same_ci_votes": 0.0, "runbooks": set()}
            problem_candidates.append({"key": key, "number": p.number, "short_description": p.short_description,
                                       "ci": p.ci, "known_error": p.known_error, "cause_notes": p.cause_notes,
                                       "votes": round(d["votes"], 3), "same_ci_votes": round(d["same_ci_votes"], 3),
                                       "runbooks": sorted(d["runbooks"])})
        problem_candidates.sort(key=lambda x: -x["votes"])
        return {"kb_candidates": kb_candidates, "similar_incidents": similar, "problem_candidates": problem_candidates}
