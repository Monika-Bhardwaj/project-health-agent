# Project Health Reporting Agent

Built for: **AI Engineering Intern assignment — Zycus Professional Services**
Author: Monika · July 2026

An agentic system that reads raw project-plan exports (the kind PMs already
maintain in Smartsheet/MS Project), figures out RAG status without a human
chasing anyone, explains *why* in plain English, and rolls multiple projects
up into an executive-ready narrative every month.

This README is the "design decisions" deliverable requested in the brief
(in place of a Loom video).

---

## 1. What's actually in this repo

```
project_health_agent/
├── config/rag_config.yaml       # every weight/threshold/lexicon — the methodology, in code
├── agent/
│   ├── ingest.py                 # messy .xlsx -> normalized ProjectData
│   ├── signals.py                 # ProjectData -> auditable SignalPayload (pure math, no judgment)
│   ├── rag_engine.py              # SignalPayload -> RagVerdict (the ONLY place a color is decided)
│   ├── narrative.py                # RagVerdict -> plain-English prose (LLM, with a free fallback)
│   ├── report.py                  # renders the weekly Markdown report
│   ├── history_store.py           # append-only JSONL snapshots per project (the "database")
│   └── synthesis.py                # Phase 3: cross-project trend detection
├── scripts/
│   ├── run_weekly_report.py       # CLI: the whole Phase-2 pipeline, one file per project
│   ├── run_monthly_synthesis.py    # CLI: Phase-3 cross-project rollup
│   └── scheduler.py                # optional standalone weekly scheduler (APScheduler)
├── .github/workflows/weekly_report.yml   # bonus: fully automated weekly run in CI
├── tests/test_agent.py             # 16 unit tests on the deterministic core
├── data/                            # put your .xlsx plans here; data/history/ accumulates snapshots
└── outputs/weekly/, outputs/monthly/  # generated reports land here
```

## 2. How to run it

```bash
pip install -r requirements.txt

# Phase 2 — weekly report for every project plan in data/
python scripts/run_weekly_report.py data/*.xlsx

# Phase 3 — monthly executive synthesis across whatever's in data/history/
python scripts/run_monthly_synthesis.py

# tests
python -m pytest tests/ -v
```

Each weekly run writes, per project: a Markdown report (`outputs/weekly/*.md`),
a machine-readable JSON twin of the same report, and an appended snapshot in
`data/history/<project>.jsonl`. Run it again next week and the history file
grows — that's what makes the monthly trend view possible without a database.

To use the LLM narrative layer, set `ANTHROPIC_API_KEY` in your environment.
Without it, the agent runs in fully deterministic mode automatically — see
§4 below for why that's a feature, not a degraded fallback.

## 3. Framework: how RAG actually gets decided

Full one-pager: **`RAG_Methodology.docx`** (submitted alongside this repo).
Short version: five signals, each scored 0–100, combined with fixed weights
into a composite score, then subjected to hard override rules that can only
make the status *worse*, never better:

| Signal | Weight | What it measures |
|---|---|---|
| Schedule slippage | 35% | % of tasks behind baseline + magnitude of the worst slip |
| Milestone health | 25% | % of phases currently Red/Amber, current phase, overdue not-started tasks |
| Blockers | 25% | On-Hold tasks, stalled in-progress tasks, At-Risk flags, negative float on critical tasks |
| Stakeholder sentiment | 10% | Lexical scan of free-text PM comments — capped influence, flagged low-confidence |
| Critical path | 5% | Share of Critical-flagged tasks that have slipped |

**Score → status:** ≥80 Green, 60–79 Amber, <60 Red — then overrides apply
(e.g. *any* slipped critical-path task caps the status at Amber; an unresolved
on-hold blocker does the same; the active phase itself being Red forces Red
regardless of the composite score). This asymmetry is intentional: an
aggregate score can look fine while one acute, specific problem is actually
blocking progress — the overrides exist to catch exactly that case, and it's
not hypothetical: it's what happened on the UniSan plan (composite 91.2,
which alone would round to Green) once the active phase-Red override fired.

**Budget burn is explicitly not scored.** Neither sample plan contains a
cost/budget column. Rather than fabricate a number, the agent omits the
signal, documents the assumption in every report, and the config file has a
commented slot ready for a `budget` signal the moment cost data exists. This
was a deliberate choice: a system that silently invents budget health when
it has zero budget data is worse than one that says "I don't have that."

## 4. Why deterministic-core + optional-LLM, not "ask Claude for the RAG status"

The brief asks for "clear, plain-English reasoning... not just the color."
The tempting shortcut is to hand an LLM the whole task list and ask it for
a status + reasoning in one shot. Three reasons this design avoids that:

1. **Cost & speed.** These plans run 300–500 rows. Scoring them with pure
   pandas takes single-digit milliseconds and costs nothing. An LLM call per
   project per week is one short completion (a few hundred tokens of
   already-computed facts in, a paragraph out) — not a call per row, and not
   on the critical path of computing the status itself.
2. **Auditability.** A VP asking "why is this Red" deserves an answer that's
   the same today as it will be if re-run tomorrow. `rag_engine.py` is
   ordinary Python: same input, same output, every time. The LLM only
   rephrases an already-frozen set of facts (`reasoning_trail`) into prose —
   it cannot invent a number or flip a status, and the prompt says so
   explicitly.
3. **Reliability.** `narrative.py` tries the Anthropic API only if
   `ANTHROPIC_API_KEY` is set and the package is installed; any failure
   (rate limit, network, missing key) falls through to a template-based
   narrative built from the exact same `reasoning_trail`. The report tells
   you which mode (`llm` vs `deterministic_fallback`) produced the prose.
   The agent never goes down because an API call did.

## 5. Handling messy/incomplete data (Phase 2 requirement)

The two sample plans are a good stress test — they don't share a schema:

- `S2P_Project.xlsx` has a `Level` column, a real `RAG` column, and a
  populated `Phase/Milestone` column. `Project_Plan_B.xlsx` has none of
  those — hierarchy depth comes from `Ancestors` instead, task color comes
  from `Schedule Health` instead of `RAG`, and phases are inferred from
  depth-1 task names.
- `Project_Plan_B.xlsx`'s primary `Variance`/`Baseline Start`/`Baseline
  Finish` columns are populated on the root row only (a duplicate-column
  artifact in the source spreadsheet); the real per-task data lives in
  `Variance2`/`Baseline Start2`/`Baseline Finish2`. The agent detects which
  column is actually populated at task level and uses that one.
- `#UNPARSEABLE` placeholder strings, blank cells, and string-typed day
  deltas (`"-2d"`) are all normalized in `ingest.py` before anything else
  touches the data.
- Every substitution is recorded as a warning and surfaced in the report's
  "Data-quality notes" section — never silently.
- A **Data Confidence** score (0–100) travels alongside every RAG status,
  penalizing missing required fields, so a VP can tell "this is Red and we
  trust the data" apart from "this is Red but we're missing half the fields
  that would confirm it."

## 6. Phase 3: what makes the exec deck about *trends*, not summaries

`agent/synthesis.py` deliberately does not just concatenate two project
summaries. It runs rule-based comparisons across whatever's in
`data/history/` and only surfaces a trend/risk if a real threshold is
crossed (e.g. "owner concentration differs by >20 points between projects"),
same philosophy as the RAG engine: comparisons are computed, not vibed. On
the two sample plans this surfaced things a per-project summary would
miss — e.g. one project's composite score is strong (91.2) but its *active*
phase is blocked, which is a materially different risk than a project with a
uniformly low score; and reporting discipline (status-comment logging)
varies enough between PMs that the sentiment signal is only usable on one of
the two plans. Those became the deck's actual content instead of "Project A
is Red, Project B is Red, the end."

## 7. What I'd add with more time / real data

- A real Budget Burn signal once plans carry cost data.
- Swap the lexical sentiment scan for a small classifier once there's enough
  labeled comment history to justify it — right now the honest move is to
  keep it simple, transparent, and capped rather than dress up a keyword
  match as NLP.
- A lightweight web dashboard over `data/history/*.jsonl` (the data's already
  there; this is a rendering exercise, not a new data problem).
- Slack/email delivery of the weekly Markdown report (the render layer is
  already decoupled from the CLI, so this is a new consumer of
  `report.render_markdown`, not a rewrite).
