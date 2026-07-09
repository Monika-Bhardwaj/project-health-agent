# Project Health Reporting Agent — Complete Technical Deep Dive

**For:** Personal learning record / interview prep
**Author:** Monika
**Context:** Zycus AI Engineering Intern take-home assignment
**Repo:** `project-health-agent`

---

## A note before you read this

This document is written to be honest about what was actually built, not what
would look most impressive. One thing up front: **there is no frontend and no
API server in this system.** It is a Python CLI pipeline that reads `.xlsx`
files and writes Markdown/JSON reports to disk. If an interviewer asks you to
"walk through the frontend," the correct answer is "there isn't one — here's
why, and here's what I'd build if this needed one," not a scramble to
pretend otherwise. Section 11 gives you that answer in full, including a
concrete proposed architecture, clearly labeled as *not built*.

Everything else in this document — the architecture, the code, the bugs, the
fixes, the results — is real, and matches what's in the repo.

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Research & Approach Curation](#2-research--approach-curation)
3. [System Architecture](#3-system-architecture)
4. [Tech Stack & Why](#4-tech-stack--why)
5. [Codeflow: End-to-End Walkthrough](#5-codeflow-end-to-end-walkthrough)
6. [Core Functionalities](#6-core-functionalities)
7. [Key Differentiators](#7-key-differentiators)
8. [Build Journey: Step by Step, What Broke, How It Was Fixed](#8-build-journey-step-by-step-what-broke-how-it-was-fixed)
9. [Results](#9-results)
10. [How the Pieces Connect (No Frontend/Backend Split — Here's What Actually Exists)](#10-how-the-pieces-connect)
11. [Future Advancements](#11-future-advancements)

---

## 1. Problem Statement

Zycus Professional Services wanted visibility into project health without a
human manually chasing Project Managers every week. The assignment, in three
phases:

- **Phase 1** — define, on paper, how RAG (Red/Amber/Green) status gets
  decided from signals like schedule slippage, budget burn, milestone health,
  blockers, and stakeholder sentiment.
- **Phase 2** — build an agent that reads a project plan, determines RAG
  status, explains *why* in plain English (not just the color), and handles
  incomplete/messy data gracefully. Bonus: runnable on a weekly schedule.
- **Phase 3** — synthesize outputs across multiple project plans into a
  5–7 slide executive presentation that identifies **trends across projects**
  (not per-project summaries), highlights emerging risks, and gives
  executive-level recommendations.

Two real project-plan exports were provided as the test data:
`S2P_Project.xlsx` (Zycus Titan implementation for Outokumpu) and
`Project_Plan_B.xlsx` (Zycus UniSan implementation). Both are MS
Project/Smartsheet-style hierarchical task exports — and, importantly, they
**do not share a schema**. That mismatch turned out to be the single biggest
design driver in the whole project (see Section 8).

---

## 2. Research & Approach Curation

### The tempting shortcut, and why it was rejected

The fastest way to satisfy "reads a project plan, determines RAG status,
explains why" is: dump the task list into an LLM prompt and ask it for a
color and a paragraph. This was seriously considered and deliberately
rejected, for three concrete reasons:

1. **Cost.** These plans run 300–500 rows. An LLM call that has to reason
   over the raw table every time is doing real work (and burning real
   tokens) for something pandas can compute in single-digit milliseconds.
2. **Auditability.** A VP asking "why is this Red" deserves the same answer
   today and tomorrow, re-run against the same data. An LLM asked to *decide*
   the status, not just phrase it, will not reliably reproduce the same
   verdict twice, and there's no way to point to a specific rule that fired.
3. **Reliability.** A system whose core function (computing a status) depends
   on an external API call is a system that goes down when that API is
   rate-limited, slow, or the key is missing — during, say, a live demo.

### The approach that was chosen: deterministic core + optional LLM skin

The system is split into a **judgment layer** (pure Python, zero API calls,
fully deterministic) and a **language layer** (LLM-assisted, optional,
can fail over silently). The judgment layer decides the RAG status and
produces a `reasoning_trail` — an ordered list of plain factual strings. The
language layer's *only* job is to turn that trail into readable prose. It is
explicitly instructed (in the prompt, see Section 5.4) not to invent a number
or change the status.

This mirrors a pattern worth knowing the name of: **retrieval/compute-then-
generate**, as opposed to **generate-only**. The facts are settled before the
LLM ever sees them; the LLM narrates, it doesn't decide.

### Alternatives considered and rejected

| Alternative | Why rejected |
|---|---|
| Ask an LLM to read the raw table and output RAG + reasoning in one shot | Non-reproducible, expensive per row, no audit trail, fragile to API issues |
| Train a small classifier on historical RAG labels | No labeled history exists yet; a rule-based system is also more explainable to a VP who wants to know "why," which a trained model can't cleanly give |
| Use only the self-reported `Schedule Health` field already in the sheet | This is exactly the "manually chasing PMs" problem the assignment exists to solve — self-reports are inconsistent between PMs (see Section 9) and don't carry a documented methodology |
| A single unweighted rule ("any Red task = Red project") | Too brittle; one stale task shouldn't sink an otherwise healthy 400-task program. Needed weighted aggregation *plus* targeted overrides for the cases where a single fact should dominate |

### Why weights + hard overrides, not just weights

A pure weighted average has one specific failure mode that mattered a lot
once real data was in hand: it can look fine in aggregate while one acute,
specific problem is actively blocking the project. This is exactly what
happened with the UniSan plan — composite score 91.2 (would round to Green)
but the *currently active phase* was Red. A weighted average alone would
have called that Green. The override rules exist specifically to catch that
class of case, and they're asymmetric on purpose: they can only make a
status *worse*, never better, so they can't be used to paper over a real
problem with a good score elsewhere.

---

## 3. System Architecture

```
                         ┌─────────────────────────┐
   .xlsx project plan    │                         │
   (Smartsheet / MS      │      agent/ingest.py    │   ProjectData
   Project export)  ───► │  normalize messy schema │ ─────────────┐
                         └─────────────────────────┘               │
                                                                    ▼
                         ┌─────────────────────────┐   SignalPayload
                         │     agent/signals.py    │ ◄──────────────┘
                         │  pure pandas, no LLM,   │
                         │  no judgment            │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐   RagVerdict
                         │   agent/rag_engine.py   │   (status +
                         │  weighted score + hard  │    reasoning_trail)
                         │  override rules         │
                         └────────────┬────────────┘
                                      │
                        ┌─────────────┴─────────────┐
                        ▼                            ▼
           ┌─────────────────────────┐   ┌─────────────────────────┐
           │   agent/narrative.py    │   │  agent/history_store.py │
           │  LLM (optional) or      │   │  append JSONL snapshot  │
           │  deterministic fallback │   │  data/history/*.jsonl   │
           └────────────┬────────────┘   └────────────┬────────────┘
                        ▼                              │
           ┌─────────────────────────┐                 │
           │     agent/report.py     │                 │
           │  renders weekly .md     │                 │
           │  + .json report         │                 │
           └─────────────────────────┘                 │
                                                         ▼
                                         ┌─────────────────────────┐
                                         │   agent/synthesis.py    │
                                         │  cross-project trend    │
                                         │  detection (Phase 3)    │
                                         └────────────┬────────────┘
                                                       ▼
                                         outputs/monthly/
                                         portfolio_synthesis.json
                                                       │
                                                       ▼
                                  Executive_Presentation.pptx
                                  (built from that JSON, not by hand)
```

Two CLI entrypoints drive this: `scripts/run_weekly_report.py` (Phase 2, one
project at a time) and `scripts/run_monthly_synthesis.py` (Phase 3, reads
whatever's accumulated in `data/history/`). There is no server process, no
persistent database, and no network listener anywhere in this diagram — see
Section 10 for exactly what that means and doesn't mean.

---

## 4. Tech Stack & Why

| Layer | Choice | Why this, specifically |
|---|---|---|
| Language | Python 3.11 | Best-supported ecosystem for both data wrangling (pandas) and LLM SDKs (anthropic); the assignment's data is tabular, which is pandas' home turf |
| Data ingestion | `pandas` + `openpyxl` | `pandas.ExcelFile` handles multi-sheet workbooks cleanly; `openpyxl` is the engine pandas needs for `.xlsx`. No heavier ETL tool (Airflow, dbt) is justified for a single-file, single-pass transform |
| Config | `PyYAML` | The whole methodology (weights, thresholds, override descriptions, sentiment lexicon) needed to be data, not code, so it's auditable and editable without touching Python. YAML over JSON purely for human-editability (comments, readability) |
| LLM | `anthropic` SDK, Claude Sonnet | Used narrowly — one short completion per project per report, to phrase already-computed facts. Any model would do this job; Claude was chosen because that's the ecosystem this assignment sits in and because tool/refusal behavior is predictable for a "don't invent facts" instruction |
| Persistence | Flat JSONL files (`data/history/*.jsonl`) | No real database needed for append-only, human-diffable time series that's small enough to fit in git. One line per run, one file per project — this *is* the trend database, and it needs zero infrastructure |
| Scheduling (bonus) | GitHub Actions cron, with `APScheduler` as a fallback | GitHub Actions needs no server to run and commits results straight back to the repo, so the history and reports track the codebase automatically. APScheduler is offered for anyone running this on a long-lived VM instead |
| Testing | `pytest` | Standard, and its `parametrize` decorator was a good fit for the many small parsing-edge-case tests (`_parse_day_delta`, `_normalize_rag`) |
| Presentation generation | `pptxgenjs` (Node) | Chosen specifically so the slide deck is generated *from* `portfolio_synthesis.json`, not hand-built in PowerPoint — the numbers on the slides are the same numbers the agent computed, not a human's transcription of them |
| Methodology doc | `docx` (Node) | One-page Word doc was the explicitly requested format for Phase 1 |

**Deliberately not used:** a database (SQLite/Postgres) — no query pattern
here justifies one over flat files; a task queue (Celery) — one file per
project per week is not a throughput problem; a vector store — nothing here
is a retrieval problem, the "search" is just pandas filtering.

---

## 5. Codeflow: End-to-End Walkthrough

### 5.1 Ingestion (`agent/ingest.py`)

Entry point: `load_project(path) -> ProjectData`. The core problem this
solves: the two sample files don't share a schema, and neither is fully
populated. Concretely:

```python
def _leaf_populated(col):
    if col not in df.columns:
        return -1
    depth_leaf = df["_depth"].fillna(0) >= 2
    return df.loc[depth_leaf, col].notna().sum()

variance_col = "Variance"
if _leaf_populated("Variance") <= 0 and _leaf_populated("Variance2") > 0:
    variance_col = "Variance2"
    warns.append("'Variance' column was empty at task level; used "
                  "'Variance2' instead (duplicate-column artifact in "
                  "source file).")
df["_variance_days"] = df[variance_col].apply(_parse_day_delta) if variance_col in df.columns else None
```

This pattern — "check what's actually populated at the level that matters,
fall back if needed, and log the substitution" — repeats for hierarchy depth
(`Level` vs `Ancestors`), task-level color (`RAG` vs `Schedule Health`), and
phase names (`Phase/Milestone` column vs. inferring from depth-1 task
names). Nothing fails silently: every substitution lands in
`ProjectData.warnings` and later shows up in the report's "Data-quality
notes" section.

Day-delta strings like `"-2d"` are parsed with a small regex:

```python
def _parse_day_delta(v) -> Optional[int]:
    v = _clean_scalar(v)
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(round(v))
    m = re.match(r"^(-?\d+)\s*d?$", str(v).strip(), re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None
```

### 5.2 Signal computation (`agent/signals.py`)

Entry point: `compute_signals(ProjectData) -> SignalPayload`. This is
pure measurement — every field on `SignalPayload` is something you could
recompute by hand from the source file. Example — the schedule-variance
trend line that ends up on the executive deck is built only from *completed*
tasks with a finish date on or before "today," specifically to avoid a bug
that showed up during development (see Section 8, Bug #3):

```python
trend_rows = leaf[leaf["Status"] == "Completed"].dropna(subset=["_variance_days"]).copy()
date_col = "_End_Date" if "_End_Date" in trend_rows.columns else None
if date_col and trend_rows[date_col].notna().any():
    trend_rows = trend_rows[trend_rows[date_col] <= TODAY].dropna(subset=[date_col]).sort_values(date_col)
    trend_rows["_cummean"] = trend_rows["_variance_days"].expanding().mean()
```

Blockers, stalled tasks, and critical-path checks are all computed on
`leaf` (depth ≥ 2) rows only — depth 0/1 rows are project/phase rollups that
mirror their children, and including them was an early bug (Section 8,
Bug #4).

### 5.3 RAG decision (`agent/rag_engine.py`)

Entry point: `evaluate(SignalPayload) -> RagVerdict`. Five signals, each
scored 0–100 by its own small function (`_score_schedule`,
`_score_milestone`, `_score_blockers`, `_score_sentiment`,
`_score_critical_path`), combined by the weights in `config/rag_config.yaml`:

```python
composite = (
    sched_score * w["schedule"]
    + mile_score * w["milestone"]
    + block_score * w["blockers"]
    + sent_score * w["sentiment"]
    + crit_score * w["critical_path"]
)
```

Then overrides, which can only downgrade:

```python
rank = {"Green": 2, "Amber": 1, "Red": 0}
if signals.critical_slipped > 0:
    overrides.append({...})
    if rank[status] > rank["Amber"]:
        status = "Amber"
```

A unit test (`test_overrides_can_only_worsen_status`) exists specifically to
lock this asymmetry in place — see Section 8 for why that test was added
after a near-miss.

### 5.4 Narrative generation (`agent/narrative.py`)

Entry point: `generate(SignalPayload, RagVerdict, cfg) -> {"text", "mode"}`.
The LLM call, when it happens, is handed the already-decided verdict and
told explicitly not to touch it:

```python
prompt = f"""
You are given ALREADY-DECIDED, verified facts below. Do not change the
status, do not invent numbers, and do not add facts that are not listed.

PROJECT: {signals.project_name}
STATUS (already decided, do not change): {verdict.status}
COMPOSITE SCORE: {verdict.composite_score}/100

VERIFIED REASONING TRAIL:
{reasoning_trail_as_bullets}

Write the narrative now.
"""
```

If `ANTHROPIC_API_KEY` isn't set, the import fails, or the API call raises
for any reason, `_llm_narrative` returns `None` and the caller falls back to
`_fallback_narrative` — a template that walks the same `SignalPayload` fields
into prose. Both paths produce something a VP could read; only one costs
money and needs network access. Every report says which mode produced it.

### 5.5 Report rendering (`agent/report.py`)

Entry point: `render_markdown(...) -> str`. Straightforward string assembly —
status banner, narrative, a scorecard table built from `verdict.sub_scores`,
the override list if any fired, the full `reasoning_trail` (numbered, so
it's auditable line by line), key facts, and — only if non-empty — the
data-quality notes section.

### 5.6 History (`agent/history_store.py`)

`append_snapshot()` writes one JSON line per run to
`data/history/<project_slug>.jsonl`. `load_history()` reads them back. This
is the entire "database" — no schema migrations, no server, just files that
diff cleanly in git.

### 5.7 Cross-project synthesis (`agent/synthesis.py`)

Entry point: `build_portfolio_synthesis() -> dict`. Reads the *latest*
snapshot for every project in `data/history/`, then runs rule-based
comparisons — not a "summarize these two reports" LLM call. Each
trend/risk only gets surfaced if a concrete threshold is crossed, e.g.:

```python
conc_sorted = sorted(projects, key=lambda p: p["owner_concentration_pct"], reverse=True)
if conc_sorted[0]["owner_concentration_pct"] - conc_sorted[-1]["owner_concentration_pct"] > 20:
    risks.append({"theme": "Key-person concentration risk", "detail": ...})
```

The output JSON (`outputs/monthly/portfolio_synthesis.json`) is what the
`pptxgenjs` script reads to build every number on the executive deck — the
deck cannot show a number that isn't in this file.

---

## 6. Core Functionalities

- **Schema-flexible ingestion** of hierarchical project-plan exports, with
  automatic detection of which of several possible columns actually holds
  the real data, and a logged trail of every substitution made.
- **Five-signal deterministic scoring**: schedule slippage, milestone
  health, blockers, stakeholder sentiment (lexical, capped), critical-path
  risk — each independently computed, weighted, and combined.
- **Hard override rules** that catch the specific failure mode a weighted
  average misses: a strong aggregate score hiding one acute, active problem.
- **Plain-English reasoning**, LLM-assisted with a free, offline,
  deterministic fallback that's always available.
- **Data Confidence scoring** — a second number, alongside RAG, that
  tells the reader how much of the required data was actually present, so
  "Red with complete data" and "Red with major gaps" never look identical.
- **Week-over-week history** via append-only snapshots, enabling trend
  lines with zero database infrastructure.
- **Cross-project trend synthesis** (Phase 3) that only reports a
  trend/risk when a concrete threshold is crossed, feeding directly into an
  auto-generated executive slide deck.
- **Bonus scheduling** via GitHub Actions (or a standalone APScheduler
  script) for hands-off weekly runs.
- **16 passing unit tests** covering parsing edge cases, the full pipeline,
  and — specifically — that override rules can never make a status better.

---

## 7. Key Differentiators

Compared to the obvious "ask an LLM for the status and a paragraph"
approach:

1. **Reproducibility.** Same input file → same status, every time. The LLM
   is not in the decision path.
2. **Cost.** One short completion per project per report cycle, not a call
   per row or per project per query.
3. **Graceful degradation.** No API key, no network, rate-limited — the
   agent still produces a complete, useful report.
4. **An audit trail, not just an answer.** Every status ships with the
   ordered list of facts that produced it — something a client or VP can
   actually interrogate line by line.
5. **Honesty about data gaps.** Budget burn isn't scored because no budget
   data exists in either sample plan — the system says so, rather than
   fabricating a number. This showed up as a real design decision, not a
   hypothetical (see `config/rag_config.yaml`'s comments).
6. **Trend detection with thresholds, not vibes.** Phase 3 doesn't just
   describe two projects side by side — it only calls something a "trend"
   or "risk" when a specific, stated numeric gap justifies it.

---

## 8. Build Journey: Step by Step, What Broke, How It Was Fixed

This section is deliberately literal — these are the actual issues hit while
building against the two real sample files, in the order they came up.

### Step 1 — Explore the data before writing any code
Loaded both `.xlsx` files with `pandas.ExcelFile` to see sheet names and
columns before designing anything. This immediately surfaced the core
problem: **the two files don't share a schema.** `S2P_Project.xlsx` has a
`Level` column and a real `RAG` column; `Project_Plan_B.xlsx` has neither —
it uses `Ancestors` for hierarchy and `Schedule Health` as the closest
proxy for task color. This single discovery shaped the entire ingestion
design (fallback-with-logging, rather than assuming one fixed schema).

### Step 2 — Build ingestion, hit the pandas `ChainedAssignmentError`
**What broke:**
```python
df["_rag"].replace({"Yellow": "Amber"}, inplace=True)
```
raised a `ChainedAssignmentError` under modern pandas (`Copy-on-Write`
semantics) because `df["_rag"]` is a view, not a guaranteed-safe target for
`inplace=True`.
**Fix:** reassign instead of mutating in place:
```python
df["_rag"] = df["_rag"].replace({"Yellow": "Amber"})
```

### Step 3 — Signals ran, but `Project_Plan_B`'s schedule signal came back empty
**What broke:** `tasks_with_variance` was `0` for `Project_Plan_B` even
though the sheet visibly had a `Variance` column. Debugging with
`df.groupby('_depth')['Variance'].apply(lambda s: s.notna().sum())` showed
`Variance` was populated on exactly **one row** — the project root — and
nowhere else.
**Root cause:** the original spreadsheet had duplicate column names
(`Baseline Start` appearing twice, etc.); pandas auto-renamed the second
occurrence to `Baseline Start2` / `Variance2`, and *that* was where the real
per-task data lived.
**Fix:** the `_leaf_populated()` fallback logic described in Section 5.1 —
detect which column is actually populated at leaf level and use that one,
logging the substitution.

### Step 4 — The variance trend chart showed dates in the future
**What broke:** early versions of the cumulative-variance trend (used for
the executive deck's line chart) sorted by `End Date`, which for
not-yet-completed tasks is a *scheduled* future finish date, not a real
data point. The resulting "historical" trend line included points dated
months after "today."
**Fix:** restrict the trend calculation to `Status == "Completed"` rows
only, and additionally filter to dates ≤ today, so the line only reflects
things that have actually happened (Section 5.2).

### Step 5 — Blocker/stalled-task lists included the project's own root row
**What broke:** `stalled_in_progress_examples` listed
`"Zycus - Titan S2P Implementation"` — the project's own top-level rollup
row — as if it were an individually stalled task, because "In Progress" +
"past baseline finish" also matches the parent rollup, which mirrors its
children's aggregate state.
**Fix:** restrict all blocker/stalled/overdue/critical-path checks to
`leaf` (depth ≥ 2) rows only — rollup rows at depth 0/1 are summaries, not
independent tasks, and were excluded from every per-task signal.

### Step 6 — A composite score of 91.2 still needed to be Red
This wasn't a bug so much as a design validation moment: once overrides
were implemented, UniSan's composite score (91.2, comfortably "Green"
territory) got forced to Red because its active phase (Training Phase I)
was itself flagged Red. Initially this felt like it might be a scoring bug
— it wasn't. It's exactly the override doing its job: a strong aggregate
number was hiding one specific, currently-live blocker. This became a
central talking point in the executive deck (Slide 2/3) rather than
something to "fix away."

### Step 7 — Locking in the override asymmetry with a test
After Step 6, it became clear the overrides needed a guarantee: they must
never accidentally *improve* a status. A dedicated test
(`test_overrides_can_only_worsen_status`) was added, constructing a
synthetic "Green" `SignalPayload` and confirming that flipping on a
critical-slip override can only push it to Amber/Red, never back to Green.

### Step 8 — `as_of` date rendering with a stray timestamp
**What broke:** the report's date line initially rendered as
`2026-07-02 00:00:00` instead of `2026-07-02`, because the "Today's Date"
value pulled from the Summary sheet was a `pandas.Timestamp`, and `str()`
on it includes the time component.
**Fix:** explicit `.strftime("%Y-%m-%d")` formatting instead of relying on
`str()`.

### Step 9 — Verifying the deck's charts against source data
Before finalizing the executive deck, every number on it (composite
scores, percentages, owner counts) was cross-checked against
`outputs/monthly/portfolio_synthesis.json` rather than typed in by hand —
this is why the build script for the deck (`pptxgenjs`) reads that JSON
file directly instead of hardcoding numbers.

### Step 10 — Fresh-clone verification
Before calling this done, the entire zipped repo was extracted to a clean
directory, history/output folders wiped, and the full pipeline (`pip
install -r requirements.txt`, both CLI scripts, `pytest`) re-run from
scratch to confirm it works with zero hidden state left over from
development — see Section 9 for that run's output.

---

## 9. Results

**Titan (Outokumpu) — `S2P_Project.xlsx`:**
- Composite score: **44.6/100 → Red**
- 62.6% of tasks with tracked variance are behind baseline; mean variance
  −11.2 days, worst case −63 days on a single task
- 11 critical-path tasks slipped; 3 tasks On Hold, all client-side
  dependencies (credentials/sign-off)
- Only 2 distinct task owners, with the busiest covering 66.7% of all
  tasks — a concrete bus-factor risk
- Notably: the plan's own self-reported `Schedule Health` read **Green** —
  the agent's deeper signal analysis disagreed, and did so with a fully
  auditable reason trail, which is precisely the gap this assignment asked
  to close

**UniSan — `Project_Plan_B.xlsx`:**
- Composite score: **91.2/100**, but **forced to Red** by the
  active-phase-red override
- Only 0.8% of tasks slipped, mean variance +1.2 days — a healthy
  aggregate schedule
- 26 distinct owners, 19.1% concentration — healthy resourcing, no
  key-person risk
- Zero status comments logged by this PM (vs. 16 for Titan's PM) — a
  reporting-discipline gap that shows up as a *specific*, surfaced
  recommendation in the executive deck, not a vague observation

**Test suite:** 16/16 passing, covering parsing edge cases (parametrized),
full-pipeline smoke tests against both real files, and the override-
asymmetry guarantee.

**Fresh-clone run:** confirmed working end-to-end from a clean unzip with
no leftover state — both weekly reports and the monthly synthesis
regenerate identically.

---

## 10. How the Pieces Connect

To be fully explicit about the "frontend/backend" question:

- **There is no backend server.** Nothing listens on a port. There is no
  API, REST or otherwise. "Running the backend" means running a Python
  script from the command line.
- **There is no frontend.** There is no web page, no button to click. The
  "UI" is: a person runs `python scripts/run_weekly_report.py data/*.xlsx`,
  and reads the Markdown file it writes.
- **How the "phases" connect, concretely:** each module in `agent/` takes
  the previous stage's output as a typed Python object (`ProjectData` →
  `SignalPayload` → `RagVerdict` → narrative dict → rendered string), and
  each stage also gets serialized to disk (the `.md`/`.json` weekly report,
  the `.jsonl` history snapshot, the `.json` monthly synthesis). Those disk
  artifacts are the actual "integration points" — anything that wanted to
  build a UI on top of this would read `outputs/*.json` and
  `data/history/*.jsonl`, not import the Python objects directly.
- **The executive deck is the closest thing to a "consumer app"** in this
  system, and even that isn't interactive — it's a one-shot Node.js script
  (`pptxgenjs`) that reads `portfolio_synthesis.json` and writes a `.pptx`
  file. It runs once, at Phase-3 time, not continuously.

If you're asked in an interview "so what does the user actually see," the
honest answer is: a Markdown report and a slide deck, both generated by a
script they run — not a live application.

---

## 11. Future Advancements

Split deliberately into two kinds: incremental improvements to what exists,
and a genuinely new capability (a frontend/API) that was never built.

### 11.1 Incremental (extends the current design, doesn't replace it)

- **Real budget-burn signal.** The config already has a weighted slot
  reserved; this just needs a plan template that carries cost data.
- **Upgrade sentiment from lexical scan to a small classifier**, once
  there's enough labeled comment history to justify it over a transparent
  keyword match.
- **Structured LLM output** for the narrative layer using Claude's tool-use
  / structured-output support, so the narrative comes back as validated
  JSON (e.g. `{opening, schedule_para, blockers_para}`) instead of free
  text — makes downstream formatting more robust.
- **Slack/email delivery** of the weekly Markdown report — a new consumer
  of the already-decoupled `report.render_markdown()` function, not a
  rewrite of anything.

### 11.2 New capability: a proposed frontend/API (not built — a design)

If this needed to become something people log into rather than a script
people run, the natural shape, using only currently-available, mainstream
tooling (no speculative unreleased tech):

- **Backend:** a thin FastAPI service wrapping the existing `agent/`
  package almost unchanged — e.g. `POST /projects/{id}/reports` triggers
  `run_one()`, `GET /projects/{id}/history` reads
  `history_store.load_history()`, `GET /portfolio/synthesis` wraps
  `synthesis.build_portfolio_synthesis()`. The point is that none of the
  judgment logic would need to change — FastAPI would just be a network
  door onto functions that already exist and are already tested.
- **Frontend:** a small React dashboard — project list with live RAG
  pills, a detail view rendering the same `reasoning_trail` the Markdown
  report shows today (so the two surfaces never disagree, because they'd
  read the same JSON), and a trend chart per project pulled straight from
  `data/history/*.jsonl`.
- **Database:** at that point, the flat JSONL files would earn an upgrade
  to a real datastore (Postgres, or SQLite for something lighter) purely
  for concurrent-write safety and query performance — not because the data
  model changes.
- **Auth & multi-tenant PM access:** would matter the moment PMs are
  expected to log into this themselves rather than a shared plan file being
  dropped into `data/`.

This is intentionally scoped to "what would I actually build next," not a
wish list of unrelated technology — every piece above is a natural extension
of a module that already exists and is already tested.
