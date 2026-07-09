"""
agent/rag_engine.py
====================
Turns a SignalPayload into a RAG verdict. This is the ONLY place a
Red/Amber/Green status gets decided. It is pure, deterministic, unit-testable
Python — no LLM involved — so the same inputs always produce the same status,
and every verdict comes with a traceable "why" trail (not just a color).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import yaml

from agent.signals import SignalPayload


@dataclass
class RagVerdict:
    status: str                 # "Green" | "Amber" | "Red"
    composite_score: float       # 0-100, before overrides
    sub_scores: dict             # per-signal 0-100 scores
    overrides_triggered: list    # list of {id, description, effect}
    reasoning_trail: list        # ordered list of short factual strings (inputs to the narrative layer)


def _score_schedule(s: SignalPayload) -> tuple[float, str]:
    if s.tasks_with_variance == 0:
        return 70.0, "No schedule-variance data available at task level — scored neutral-cautious."
    slip_penalty = min(s.pct_tasks_slipped, 100) * 0.6
    mean_penalty = min(abs(s.mean_variance_days or 0), 30) * 1.2 if (s.mean_variance_days or 0) < 0 else 0
    score = max(0.0, 100 - slip_penalty - mean_penalty)
    detail = (f"{s.pct_tasks_slipped}% of tasks with recorded variance are behind baseline "
              f"(mean variance {s.mean_variance_days} days; worst case {s.worst_variance_days} days "
              f"on '{s.worst_variance_task}').")
    return round(score, 1), detail


def _score_milestone(s: SignalPayload) -> tuple[float, str]:
    if not s.phase_rag_counts:
        return 70.0, "No phase-level rollups available — scored neutral-cautious."
    total = len(s.phase_rag_counts)
    reds = sum(1 for v in s.phase_rag_counts.values() if v == "Red")
    ambers = sum(1 for v in s.phase_rag_counts.values() if v == "Amber")
    score = max(0.0, 100 - (reds / total * 100) - (ambers / total * 40))
    detail = (f"{reds} of {total} phases are currently Red and {ambers} Amber "
              f"(current phase: '{s.current_phase}').")
    if s.overdue_not_started:
        score -= min(s.overdue_not_started * 3, 20)
        detail += f" {s.overdue_not_started} task(s) are Not Started despite a baseline finish date already in the past."
    return round(max(0.0, score), 1), detail


def _score_blockers(s: SignalPayload) -> tuple[float, str]:
    score = 100.0
    parts = []
    if s.on_hold_count:
        score -= min(s.on_hold_count * 10, 40)
        parts.append(f"{s.on_hold_count} task(s) On Hold ({', '.join(s.on_hold_examples[:3])})")
    if s.stalled_in_progress:
        score -= min(s.stalled_in_progress * 6, 30)
        parts.append(f"{s.stalled_in_progress} in-progress task(s) past their baseline finish with no completion")
    if s.at_risk_count:
        score -= min(s.at_risk_count * 8, 20)
        parts.append(f"{s.at_risk_count} task(s) explicitly flagged At Risk")
    if s.negative_float_critical_count:
        score -= min(s.negative_float_critical_count * 15, 30)
        parts.append(f"{s.negative_float_critical_count} critical task(s) with negative float")
    detail = "; ".join(parts) if parts else "No open blockers, on-hold items, or at-risk flags detected."
    return round(max(0.0, score), 1), detail


def _score_sentiment(s: SignalPayload) -> tuple[float, str]:
    # Deliberately capped influence: sentiment is a lexical proxy over free-text
    # PM comments, not a validated survey. It nudges the score by at most +/-15
    # points and is flagged to the reader as low-confidence in the report.
    if s.sentiment_sample_size < 3:
        return 70.0, "Too few free-text comments to assess stakeholder tone reliably (low-confidence signal)."
    score = 70 + s.sentiment_score * 15
    detail = (f"Lexical scan of {s.sentiment_sample_size} PM/stakeholder comments skews "
              f"{'negative' if s.sentiment_score < -0.15 else ('positive' if s.sentiment_score > 0.15 else 'neutral')} "
              f"(score {s.sentiment_score}); flagged as a low-confidence signal, capped influence on the overall score.")
    return round(max(0.0, min(100.0, score)), 1), detail


def _score_critical_path(s: SignalPayload) -> tuple[float, str]:
    if s.critical_total == 0:
        return 100.0, "No tasks are flagged Critical in the plan."
    frac = s.critical_slipped / s.critical_total
    score = max(0.0, 100 - frac * 100)
    detail = f"{s.critical_slipped} of {s.critical_total} critical-path tasks have slipped their baseline."
    return round(score, 1), detail


def evaluate(signals: SignalPayload, cfg_path="config/rag_config.yaml") -> RagVerdict:
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    w = cfg["signal_weights"]

    sched_score, sched_detail = _score_schedule(signals)
    mile_score, mile_detail = _score_milestone(signals)
    block_score, block_detail = _score_blockers(signals)
    sent_score, sent_detail = _score_sentiment(signals)
    crit_score, crit_detail = _score_critical_path(signals)

    sub_scores = {
        "schedule": sched_score,
        "milestone": mile_score,
        "blockers": block_score,
        "sentiment": sent_score,
        "critical_path": crit_score,
    }
    composite = (
        sched_score * w["schedule"]
        + mile_score * w["milestone"]
        + block_score * w["blockers"]
        + sent_score * w["sentiment"]
        + crit_score * w["critical_path"]
    )
    composite = round(composite, 1)

    thresholds = cfg["score_thresholds"]
    if composite >= thresholds["green_min"]:
        status = "Green"
    elif composite >= thresholds["amber_min"]:
        status = "Amber"
    else:
        status = "Red"

    # --- hard overrides (can only downgrade) ---
    overrides = []
    rank = {"Green": 2, "Amber": 1, "Red": 0}

    if signals.critical_slipped > 0:
        overrides.append({
            "id": "critical_task_slipped",
            "description": f"{signals.critical_slipped} critical-path task(s) have slipped their baseline.",
            "effect": "capped at Amber",
        })
        if rank[status] > rank["Amber"]:
            status = "Amber"

    if signals.on_hold_count > 0:
        overrides.append({
            "id": "unresolved_blocker",
            "description": f"{signals.on_hold_count} task(s) are On Hold: {', '.join(signals.on_hold_examples[:3])}.",
            "effect": "capped at Amber",
        })
        if rank[status] > rank["Amber"]:
            status = "Amber"

    if signals.phases_red and (signals.current_phase in signals.phases_red or len(signals.phases_red) >= 2):
        overrides.append({
            "id": "milestone_red_and_slipping",
            "description": f"{len(signals.phases_red)} phase(s) are Red, including possibly the active phase.",
            "effect": "forced to Red",
        })
        status = "Red"

    reasoning_trail = [
        f"Schedule ({int(w['schedule']*100)}% weight, score {sched_score}/100): {sched_detail}",
        f"Milestones ({int(w['milestone']*100)}% weight, score {mile_score}/100): {mile_detail}",
        f"Blockers ({int(w['blockers']*100)}% weight, score {block_score}/100): {block_detail}",
        f"Stakeholder sentiment ({int(w['sentiment']*100)}% weight, score {sent_score}/100): {sent_detail}",
        f"Critical path ({int(w['critical_path']*100)}% weight, score {crit_score}/100): {crit_detail}",
        f"Composite score: {composite}/100 -> baseline status before overrides: "
        f"{'Green' if composite >= thresholds['green_min'] else ('Amber' if composite >= thresholds['amber_min'] else 'Red')}.",
    ]
    for o in overrides:
        reasoning_trail.append(f"Override [{o['id']}]: {o['description']} -> {o['effect']}.")
    reasoning_trail.append(f"Final status: {status}.")

    return RagVerdict(
        status=status,
        composite_score=composite,
        sub_scores=sub_scores,
        overrides_triggered=overrides,
        reasoning_trail=reasoning_trail,
    )


def to_dict(verdict: RagVerdict) -> dict:
    return asdict(verdict)
