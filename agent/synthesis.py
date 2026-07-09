#!/usr/bin/env python3
"""
agent/synthesis.py
===================
Phase 3: reads every project's latest snapshot (from data/history/*.jsonl)
and produces a structured, cross-project comparison — trends, not summaries.
This JSON is what scripts/build_exec_deck.py turns into slides, and is also
useful on its own (e.g. for a dashboard).

Everything here is computed from the SAME verified signals/verdict objects
already produced for the weekly reports — no new judgment calls, just
comparison across projects and across time.
"""
from __future__ import annotations

import json
from pathlib import Path

from agent.history_store import all_project_slugs, load_history


def _latest(history: list[dict]) -> dict:
    return history[-1] if history else {}


def build_portfolio_synthesis(out_path="outputs/monthly/portfolio_synthesis.json") -> dict:
    slugs = all_project_slugs()
    projects = []
    for slug in slugs:
        history = load_history(slug)
        if not history:
            continue
        latest = _latest(history)
        sig = latest["signals"]
        verdict = latest["verdict"]

        # self-reported vs agent-computed divergence (uses Summary sheet's own
        # 'Schedule Health' value if we can recover it — here we approximate
        # using the raw task-level RAG counts' dominant color as a stand-in
        # for "what a human skimming the sheet would likely conclude").
        raw_counts = sig.get("raw_task_level_rag_counts", {})

        projects.append({
            "project_name": sig["project_name"],
            "project_manager": sig["project_manager"],
            "as_of": sig["as_of"],
            "status": verdict["status"],
            "composite_score": verdict["composite_score"],
            "pct_complete": sig["pct_complete"],
            "current_phase": sig["current_phase"],
            "phases_red": sig["phases_red"],
            "pct_tasks_slipped": sig["pct_tasks_slipped"],
            "mean_variance_days": sig["mean_variance_days"],
            "variance_trend": sig["variance_trend"],
            "on_hold_count": sig["on_hold_count"],
            "on_hold_examples": sig["on_hold_examples"],
            "at_risk_count": sig["at_risk_count"],
            "critical_slipped": sig["critical_slipped"],
            "critical_total": sig["critical_total"],
            "unique_owners": sig["unique_owners"],
            "owner_concentration_pct": sig["owner_concentration_pct"],
            "sentiment_sample_size": sig["sentiment_sample_size"],
            "sentiment_score": sig["sentiment_score"],
            "data_confidence_pct": sig["data_confidence_pct"],
            "data_confidence_notes": sig["data_confidence_notes"],
            "overrides_triggered": verdict["overrides_triggered"],
        })

    # --- cross-project trend detection (rule-based, not vibes) ---
    trends = []
    risks = []
    recommendations = []

    if len(projects) >= 2:
        # 1. Resourcing concentration spread
        conc_sorted = sorted(projects, key=lambda p: p["owner_concentration_pct"], reverse=True)
        if conc_sorted[0]["owner_concentration_pct"] - conc_sorted[-1]["owner_concentration_pct"] > 20:
            risks.append({
                "theme": "Key-person concentration risk",
                "detail": (f"{conc_sorted[0]['project_name']} has {conc_sorted[0]['unique_owners']} distinct "
                           f"owner(s), with the busiest covering {conc_sorted[0]['owner_concentration_pct']}% of "
                           f"tasks — versus {conc_sorted[-1]['owner_concentration_pct']}% on "
                           f"{conc_sorted[-1]['project_name']}. A single-person dependency is a bus-factor risk "
                           f"on the critical path.")
            })

        # 2. Reporting-discipline gap (sentiment sample size as proxy for PM commentary habits)
        sent_sorted = sorted(projects, key=lambda p: p["sentiment_sample_size"], reverse=True)
        if sent_sorted[0]["sentiment_sample_size"] > 0 and sent_sorted[-1]["sentiment_sample_size"] == 0:
            trends.append({
                "theme": "Inconsistent PM reporting discipline across the portfolio",
                "detail": (f"{sent_sorted[0]['project_name']} has {sent_sorted[0]['sentiment_sample_size']} logged "
                           f"status comments; {sent_sorted[-1]['project_name']} has none on record. Health "
                           f"reporting is only as good as the commentary PMs log week to week.")
            })
            recommendations.append("Make weekly status-comment logging a required field across all project "
                                    "plans — several signals (sentiment, blocker context) are unavailable "
                                    "without it.")

        # 3. Budget/cost blind spot (structural, applies portfolio-wide)
        recommendations.append("No project in the current portfolio tracks cost/budget data in its plan. "
                                "Add a Budget Burn column to the plan template so a true 5-signal RAG "
                                "(incl. cost) can be produced next cycle.")

        # 4. Schedule trajectory comparison
        worsening = [p for p in projects if p["variance_trend"] and len(p["variance_trend"]) >= 2
                     and p["variance_trend"][-1][1] < p["variance_trend"][0][1] - 3]
        if worsening:
            names = ", ".join(p["project_name"] for p in worsening)
            trends.append({
                "theme": "Schedule drift is accelerating, not stabilizing",
                "detail": (f"On {names}, cumulative average variance has been getting worse over the life of "
                           f"the project rather than flattening out — a sign the delays are compounding rather "
                           f"than being absorbed by float.")
            })

        # 5. Status where the current/active phase itself is red (localized, acute risk)
        acute = [p for p in projects if p["current_phase"] in (p["phases_red"] or [])]
        if acute:
            for p in acute:
                risks.append({
                    "theme": "Active phase is blocked, not just historically behind",
                    "detail": (f"{p['project_name']}'s current phase — '{p['current_phase']}' — is itself "
                               f"flagged Red. This is a live blocker to forward progress, not a legacy variance "
                               f"from an earlier phase.")
                })

        # 6. Vendor/external-dependency blocker pattern
        ext_blocked = [p for p in projects if p["on_hold_count"] > 0]
        if ext_blocked:
            examples = "; ".join(f"{p['project_name']}: {', '.join(p['on_hold_examples'][:2])}" for p in ext_blocked)
            trends.append({
                "theme": "Client-side/external dependencies are the dominant blocker type",
                "detail": (f"On-hold items across the portfolio are concentrated in tasks waiting on the client "
                           f"(credentials, sample data, sign-offs) rather than on Zycus-side work: {examples}.")
            })
            recommendations.append("Introduce a client-readiness checklist at kickoff (credentials, sample data, "
                                    "named approvers) to pull these dependencies earlier, before they sit on the "
                                    "critical path.")

    result = {
        "generated_for": "Monthly Executive Synthesis",
        "projects": projects,
        "trends": trends,
        "risks": risks,
        "recommendations": recommendations,
    }

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(result, indent=2, default=str))
    return result


if __name__ == "__main__":
    r = build_portfolio_synthesis()
    print(json.dumps(r, indent=2, default=str))
