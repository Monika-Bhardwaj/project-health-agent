"""
agent/report.py
================
Renders the final weekly, human-facing Markdown report from a
SignalPayload + RagVerdict + narrative. This is Phase 2's primary
deliverable artifact: one file per project, per run.
"""
from __future__ import annotations

from pathlib import Path

from agent.rag_engine import RagVerdict
from agent.signals import SignalPayload

STATUS_EMOJI = {"Green": "🟢", "Amber": "🟡", "Red": "🔴"}


def render_markdown(signals: SignalPayload, verdict: RagVerdict, narrative: dict, pdata_warnings: list) -> str:
    lines = []
    lines.append(f"# Weekly Project Health Report — {signals.project_name}")
    lines.append("")
    lines.append(f"**Status:** {STATUS_EMOJI[verdict.status]} **{verdict.status}**  "
                 f"&nbsp;&nbsp;|&nbsp;&nbsp; **Composite score:** {verdict.composite_score}/100  "
                 f"&nbsp;&nbsp;|&nbsp;&nbsp; **As of:** {signals.as_of}")
    lines.append(f"**Project Manager:** {signals.project_manager}  "
                 f"&nbsp;&nbsp;|&nbsp;&nbsp; **% Complete:** "
                 f"{f'{signals.pct_complete*100:.0f}%' if signals.pct_complete is not None else 'n/a'}  "
                 f"&nbsp;&nbsp;|&nbsp;&nbsp; **Data confidence:** {signals.data_confidence_pct:.0f}/100")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Why this status (plain English)")
    lines.append(f"*Narrative mode: `{narrative['mode']}`*")
    lines.append("")
    lines.append(narrative["text"])
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Signal scorecard")
    lines.append("")
    lines.append("| Signal | Weight | Score /100 |")
    lines.append("|---|---|---|")
    weight_map = {"schedule": "35%", "milestone": "25%", "blockers": "25%", "sentiment": "10%", "critical_path": "5%"}
    label_map = {"schedule": "Schedule slippage", "milestone": "Milestone health", "blockers": "Blockers",
                 "sentiment": "Stakeholder sentiment*", "critical_path": "Critical path"}
    for k, v in verdict.sub_scores.items():
        lines.append(f"| {label_map[k]} | {weight_map[k]} | {v} |")
    lines.append("")
    lines.append("*Sentiment is a lexical proxy over free-text PM comments, not a formal survey — "
                 "treated as low-confidence and capped in influence. Budget/cost burn is not scored: "
                 "no cost data was present in this plan (see assumptions in the RAG methodology doc).")
    lines.append("")

    if verdict.overrides_triggered:
        lines.append("## Overrides applied")
        for o in verdict.overrides_triggered:
            lines.append(f"- **[{o['id']}]** {o['description']} → *{o['effect']}*")
        lines.append("")

    lines.append("## Full reasoning trail (auditable)")
    for step in verdict.reasoning_trail:
        lines.append(f"1. {step}")
    lines.append("")

    lines.append("## Key facts")
    lines.append(f"- Current phase: **{signals.current_phase}**")
    if verdict.overrides_triggered or signals.phases_red:
        lines.append(f"- Phases currently Red: {', '.join(signals.phases_red) if signals.phases_red else 'none'}")
    lines.append(f"- Tasks tracked: {signals.total_tasks} (variance data available for {signals.tasks_with_variance})")
    lines.append(f"- On-Hold tasks: {signals.on_hold_count}" + (f" — {', '.join(signals.on_hold_examples)}" if signals.on_hold_examples else ""))
    lines.append(f"- Stalled in-progress tasks (past baseline finish): {signals.stalled_in_progress}")
    lines.append(f"- Overdue not-started tasks: {signals.overdue_not_started}")
    lines.append(f"- Critical-path tasks slipped: {signals.critical_slipped} / {signals.critical_total}")
    lines.append(f"- Resourcing: {signals.unique_owners} distinct owner(s)/assignees; "
                 f"busiest owner covers {signals.owner_concentration_pct}% of tasks")
    lines.append("")

    if pdata_warnings:
        lines.append("## Data-quality notes")
        lines.append("*The agent handled the following issues in the source file automatically:*")
        for w in pdata_warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines.append("---")
    lines.append(f"*Generated automatically by the Project Health Reporting Agent. "
                 f"Composite score and status are deterministic and reproducible from the source file; "
                 f"only the narrative prose above may vary between runs.*")
    return "\n".join(lines)


def write_report(signals: SignalPayload, verdict: RagVerdict, narrative: dict, pdata_warnings: list, out_dir="outputs/weekly") -> Path:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    slug = signals.project_name.lower().replace(" ", "_").replace("-", "").replace("__", "_")
    slug = "".join(c for c in slug if c.isalnum() or c == "_")
    path = Path(out_dir) / f"{slug}_{signals.as_of}.md"
    path.write_text(render_markdown(signals, verdict, narrative, pdata_warnings))
    return path
