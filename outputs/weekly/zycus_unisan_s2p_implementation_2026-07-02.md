# Weekly Project Health Report — Zycus - UniSan S2P Implementation

**Status:** 🔴 **Red**  &nbsp;&nbsp;|&nbsp;&nbsp; **Composite score:** 91.2/100  &nbsp;&nbsp;|&nbsp;&nbsp; **As of:** 2026-07-02
**Project Manager:** Rajat Bothra  &nbsp;&nbsp;|&nbsp;&nbsp; **% Complete:** 44%  &nbsp;&nbsp;|&nbsp;&nbsp; **Data confidence:** 92/100

---

## Why this status (plain English)
*Narrative mode: `deterministic_fallback`*

Zycus - UniSan S2P Implementation is at serious risk and needs leadership attention now. As of 2026-07-02, the project is 44% complete and the composite health score is 91.2/100.

Schedule: 0.8% of tasks with tracked variance are running ahead of baseline, averaging 1.2 days. The single worst slip is 'Review SOW with UniSan' at -8.0 days.

Milestones: 4 phase(s) are currently marked Red — Training Phase I, Hypercare Phase I, Configuration Validation & Documentation, Supplier Information Management with Integration. The active phase is 'Training Phase I'.

Blockers: 1 in-progress task(s) stuck past their baseline finish.

Why the status may look stricter than the raw score: 4 phase(s) are Red, including possibly the active phase.

---

## Signal scorecard

| Signal | Weight | Score /100 |
|---|---|---|
| Schedule slippage | 35% | 99.5 |
| Milestone health | 25% | 83.7 |
| Blockers | 25% | 94.0 |
| Stakeholder sentiment* | 10% | 70.0 |
| Critical path | 5% | 100.0 |

*Sentiment is a lexical proxy over free-text PM comments, not a formal survey — treated as low-confidence and capped in influence. Budget/cost burn is not scored: no cost data was present in this plan (see assumptions in the RAG methodology doc).

## Overrides applied
- **[milestone_red_and_slipping]** 4 phase(s) are Red, including possibly the active phase. → *forced to Red*

## Full reasoning trail (auditable)
1. Schedule (35% weight, score 99.5/100): 0.8% of tasks with recorded variance are behind baseline (mean variance 1.2 days; worst case -8.0 days on 'Review SOW with UniSan').
1. Milestones (25% weight, score 83.7/100): 4 of 33 phases are currently Red and 1 Amber (current phase: 'Training Phase I'). 1 task(s) are Not Started despite a baseline finish date already in the past.
1. Blockers (25% weight, score 94.0/100): 1 in-progress task(s) past their baseline finish with no completion
1. Stakeholder sentiment (10% weight, score 70.0/100): Too few free-text comments to assess stakeholder tone reliably (low-confidence signal).
1. Critical path (5% weight, score 100.0/100): 0 of 45 critical-path tasks have slipped their baseline.
1. Composite score: 91.2/100 -> baseline status before overrides: Green.
1. Override [milestone_red_and_slipping]: 4 phase(s) are Red, including possibly the active phase. -> forced to Red.
1. Final status: Red.

## Key facts
- Current phase: **Training Phase I**
- Phases currently Red: Training Phase I, Hypercare Phase I, Configuration Validation & Documentation, Supplier Information Management with Integration
- Tasks tracked: 343 (variance data available for 129)
- On-Hold tasks: 0
- Stalled in-progress tasks (past baseline finish): 1
- Overdue not-started tasks: 1
- Critical-path tasks slipped: 0 / 45
- Resourcing: 26 distinct owner(s)/assignees; busiest owner covers 19.1% of tasks

## Data-quality notes
*The agent handled the following issues in the source file automatically:*
- No 'Level' column found; used 'Ancestors' as the WBS hierarchy depth instead.
- No task-level 'RAG' column found; used 'Schedule Health' as a proxy for task color.
- 'Variance' column was empty at task level; used 'Variance2' instead (duplicate-column artifact in source file).
- 'Baseline Start' column was empty at task level; used 'Baseline Start2' instead (duplicate-column artifact in source file).
- 'Baseline Finish' column was empty at task level; used 'Baseline Finish2' instead (duplicate-column artifact in source file).
- Phase/Milestone column is empty; inferring phases from depth-1 task names instead.

---
*Generated automatically by the Project Health Reporting Agent. Composite score and status are deterministic and reproducible from the source file; only the narrative prose above may vary between runs.*