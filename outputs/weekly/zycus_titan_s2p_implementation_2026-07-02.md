# Weekly Project Health Report — Zycus - Titan S2P Implementation

**Status:** 🔴 **Red**  &nbsp;&nbsp;|&nbsp;&nbsp; **Composite score:** 44.6/100  &nbsp;&nbsp;|&nbsp;&nbsp; **As of:** 2026-07-02
**Project Manager:** Aftab Hashambhai  &nbsp;&nbsp;|&nbsp;&nbsp; **% Complete:** 71%  &nbsp;&nbsp;|&nbsp;&nbsp; **Data confidence:** 100/100

---

## Why this status (plain English)
*Narrative mode: `deterministic_fallback`*

Zycus - Titan S2P Implementation is at serious risk and needs leadership attention now. As of 2026-07-02, the project is 71% complete and the composite health score is 44.6/100.

Schedule: 62.6% of tasks with tracked variance are running behind baseline, averaging 11.2 days. The single worst slip is 'Load delta master data via integration' at -63.0 days.

Milestones: no phases are currently Red. The active phase is 'Configuration and Build phase'.

Blockers: 3 task(s) On Hold (Supplier Notification template, OTK to share D&B creds); 13 in-progress task(s) stuck past their baseline finish; 4 task(s) flagged At Risk.

Stakeholder tone: a lexical scan of 16 PM comments reads negative (this is a low-confidence proxy signal, not a survey, and is capped in its influence on the score).

Why the status may look stricter than the raw score: 11 critical-path task(s) have slipped their baseline.; 3 task(s) are On Hold: Supplier Notification template, OTK to share D&B creds, Enable D & B App.

---

## Signal scorecard

| Signal | Weight | Score /100 |
|---|---|---|
| Schedule slippage | 35% | 49.0 |
| Milestone health | 25% | 60.3 |
| Blockers | 25% | 20.0 |
| Stakeholder sentiment* | 10% | 63.5 |
| Critical path | 5% | 21.4 |

*Sentiment is a lexical proxy over free-text PM comments, not a formal survey — treated as low-confidence and capped in influence. Budget/cost burn is not scored: no cost data was present in this plan (see assumptions in the RAG methodology doc).

## Overrides applied
- **[critical_task_slipped]** 11 critical-path task(s) have slipped their baseline. → *capped at Amber*
- **[unresolved_blocker]** 3 task(s) are On Hold: Supplier Notification template, OTK to share D&B creds, Enable D & B App. → *capped at Amber*

## Full reasoning trail (auditable)
1. Schedule (35% weight, score 49.0/100): 62.6% of tasks with recorded variance are behind baseline (mean variance -11.2 days; worst case -63.0 days on 'Load delta master data via integration').
1. Milestones (25% weight, score 60.3/100): 0 of 13 phases are currently Red and 9 Amber (current phase: 'Configuration and Build phase'). 4 task(s) are Not Started despite a baseline finish date already in the past.
1. Blockers (25% weight, score 20.0/100): 3 task(s) On Hold (Supplier Notification template, OTK to share D&B creds, Enable D & B App); 13 in-progress task(s) past their baseline finish with no completion; 4 task(s) explicitly flagged At Risk
1. Stakeholder sentiment (10% weight, score 63.5/100): Lexical scan of 16 PM/stakeholder comments skews negative (score -0.43); flagged as a low-confidence signal, capped influence on the overall score.
1. Critical path (5% weight, score 21.4/100): 11 of 14 critical-path tasks have slipped their baseline.
1. Composite score: 44.6/100 -> baseline status before overrides: Red.
1. Override [critical_task_slipped]: 11 critical-path task(s) have slipped their baseline. -> capped at Amber.
1. Override [unresolved_blocker]: 3 task(s) are On Hold: Supplier Notification template, OTK to share D&B creds, Enable D & B App. -> capped at Amber.
1. Final status: Red.

## Key facts
- Current phase: **Configuration and Build phase**
- Phases currently Red: none
- Tasks tracked: 476 (variance data available for 254)
- On-Hold tasks: 3 — Supplier Notification template, OTK to share D&B creds, Enable D & B App
- Stalled in-progress tasks (past baseline finish): 13
- Overdue not-started tasks: 4
- Critical-path tasks slipped: 11 / 14
- Resourcing: 2 distinct owner(s)/assignees; busiest owner covers 66.7% of tasks

---
*Generated automatically by the Project Health Reporting Agent. Composite score and status are deterministic and reproducible from the source file; only the narrative prose above may vary between runs.*