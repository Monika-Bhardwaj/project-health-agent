"""
agent/narrative.py
===================
Turns an already-computed RagVerdict + SignalPayload into plain-English
reasoning for a human reader (Phase 2 requirement: "clear, plain-English
reasoning behind the status, not just the color").

Design choice (cost / speed / efficiency):
  The RAG status and every number are decided upstream in rag_engine.py,
  in pure deterministic Python. The LLM is used ONLY to phrase an already-
  fixed set of facts into readable prose — it cannot change the status or
  invent a figure. This keeps the system:
    - Cheap: one short completion per project per week, not per task.
    - Fast: no LLM call is on any critical path; ingestion/scoring/history
      all work with zero API calls, so the agent still functions (in
      "deterministic mode") with the model unavailable, rate-limited, or
      simply disabled to save cost.
    - Auditable: a Red status always comes with the same reasoning_trail
      regardless of which narrative backend rendered it.

If ANTHROPIC_API_KEY is not set (or the call fails for any reason), the
agent transparently falls back to a template-based narrative built from the
same reasoning_trail. The report always states which mode produced it.
"""
from __future__ import annotations

import os
import textwrap

from agent.rag_engine import RagVerdict
from agent.signals import SignalPayload

STATUS_OPENER = {
    "Green": "is tracking in good health",
    "Amber": "needs attention in a few specific areas",
    "Red": "is at serious risk and needs leadership attention now",
}


def _fallback_narrative(signals: SignalPayload, verdict: RagVerdict) -> str:
    """Deterministic, template-based narrative — always available, zero cost."""
    lines = []
    lines.append(
        f"{signals.project_name} {STATUS_OPENER[verdict.status]}. "
        f"As of {signals.as_of}, the project is {signals.pct_complete*100:.0f}% complete "
        f"and the composite health score is {verdict.composite_score}/100."
        if signals.pct_complete is not None else
        f"{signals.project_name} {STATUS_OPENER[verdict.status]}. "
        f"As of {signals.as_of}, the composite health score is {verdict.composite_score}/100."
    )

    if signals.tasks_with_variance:
        direction = "behind" if (signals.mean_variance_days or 0) < 0 else "ahead of"
        lines.append(
            f"Schedule: {signals.pct_tasks_slipped}% of tasks with tracked variance are running "
            f"{direction} baseline, averaging {abs(signals.mean_variance_days)} days. "
            f"The single worst slip is '{signals.worst_variance_task}' at {signals.worst_variance_days} days."
        )
    else:
        lines.append("Schedule: variance data was not available at the task level for this plan, "
                      "so schedule slippage could not be measured directly this cycle.")

    if signals.phases_red:
        lines.append(
            f"Milestones: {len(signals.phases_red)} phase(s) are currently marked Red — "
            f"{', '.join(signals.phases_red[:4])}{' and others' if len(signals.phases_red) > 4 else ''}. "
            f"The active phase is '{signals.current_phase}'."
        )
    else:
        lines.append(f"Milestones: no phases are currently Red. The active phase is '{signals.current_phase}'.")

    blocker_bits = []
    if signals.on_hold_count:
        blocker_bits.append(f"{signals.on_hold_count} task(s) On Hold ({', '.join(signals.on_hold_examples[:2])})")
    if signals.stalled_in_progress:
        blocker_bits.append(f"{signals.stalled_in_progress} in-progress task(s) stuck past their baseline finish")
    if signals.at_risk_count:
        blocker_bits.append(f"{signals.at_risk_count} task(s) flagged At Risk")
    lines.append(
        "Blockers: " + ("; ".join(blocker_bits) + "." if blocker_bits else "no open blockers were detected this cycle.")
    )

    if signals.sentiment_sample_size >= 3:
        tone = "negative" if signals.sentiment_score < -0.15 else ("positive" if signals.sentiment_score > 0.15 else "neutral")
        lines.append(
            f"Stakeholder tone: a lexical scan of {signals.sentiment_sample_size} PM comments reads {tone} "
            f"(this is a low-confidence proxy signal, not a survey, and is capped in its influence on the score)."
        )

    if verdict.overrides_triggered:
        ov = "; ".join(o["description"] for o in verdict.overrides_triggered)
        lines.append(f"Why the status may look stricter than the raw score: {ov}")

    return "\n\n".join(lines)


def _llm_narrative(signals: SignalPayload, verdict: RagVerdict, cfg: dict) -> str | None:
    """Attempt an Anthropic API call. Returns None on any failure so the
    caller can fall back cleanly — this function must never raise."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic  # imported lazily so the package is optional
    except ImportError:
        return None

    prompt = textwrap.dedent(f"""
        You are writing the "reasoning" section of a weekly project-health report
        for a Professional Services VP. You are given ALREADY-DECIDED, verified
        facts below. Do not change the status, do not invent numbers, and do not
        add facts that are not listed. Write 4-6 short paragraphs in clear,
        plain English, no bullet points, professional but not robotic tone.

        PROJECT: {signals.project_name}
        STATUS (already decided, do not change): {verdict.status}
        COMPOSITE SCORE: {verdict.composite_score}/100

        VERIFIED REASONING TRAIL:
        {chr(10).join('- ' + l for l in verdict.reasoning_trail)}

        Write the narrative now.
    """).strip()

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=cfg.get("model", "claude-sonnet-4-6"),
            max_tokens=cfg.get("max_tokens", 900),
            messages=[{"role": "user", "content": prompt}],
        )
        text_parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        text = "\n".join(text_parts).strip()
        return text or None
    except Exception:
        return None


def generate(signals: SignalPayload, verdict: RagVerdict, cfg: dict | None = None) -> dict:
    """Returns {"text": str, "mode": "llm" | "deterministic_fallback"}."""
    cfg = cfg or {}
    if cfg.get("enabled_by_default", True):
        llm_text = _llm_narrative(signals, verdict, cfg)
        if llm_text:
            return {"text": llm_text, "mode": "llm"}
    return {"text": _fallback_narrative(signals, verdict), "mode": "deterministic_fallback"}
