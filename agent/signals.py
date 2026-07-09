"""
agent/signals.py
================
Turns a normalized ProjectData into a SignalPayload: a set of auditable,
numeric/boolean facts about the project's health. No RAG judgment happens
here — this module only measures. rag_engine.py does the judging.

Every number in the returned payload is traceable back to a pandas
operation you can re-run by hand; nothing here is an LLM call.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

import pandas as pd
import yaml

from agent.ingest import ProjectData

TODAY = pd.Timestamp(datetime(2026, 7, 2))  # falls back to real "today" if not present in data


@dataclass
class SignalPayload:
    project_name: str
    project_manager: str
    as_of: str
    data_confidence_pct: float
    data_confidence_notes: list

    # schedule
    pct_complete: Optional[float]
    total_tasks: int
    tasks_with_variance: int
    pct_tasks_slipped: float
    mean_variance_days: Optional[float]
    worst_variance_days: Optional[float]
    worst_variance_task: Optional[str]
    variance_trend: list          # [(date_str, cumulative_mean_variance)] chronological

    # milestones / phases
    current_phase: Optional[str]
    phase_rag_counts: dict
    phases_red: list
    overdue_not_started: int
    overdue_not_started_examples: list

    # blockers
    on_hold_count: int
    on_hold_examples: list
    at_risk_count: int
    stalled_in_progress: int
    stalled_in_progress_examples: list
    negative_float_critical_count: int

    # critical path
    critical_total: int
    critical_slipped: int
    critical_slipped_examples: list

    # sentiment (lexical proxy — explicitly low-confidence)
    sentiment_score: float          # -1 (very negative) .. +1 (very positive)
    sentiment_negative_hits: list
    sentiment_positive_hits: int
    sentiment_sample_size: int

    # resourcing
    unique_owners: int
    owner_concentration_pct: float  # share of tasks held by the single busiest owner

    raw_task_level_rag_counts: dict


def _load_cfg(cfg_path="config/rag_config.yaml") -> dict:
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def _lexical_sentiment(texts: list[str], lexicon: dict) -> tuple[float, list, int, int]:
    neg_words = lexicon["negative"]
    pos_words = lexicon["positive"]
    neg_hits, pos_hits, sample = [], 0, 0
    for t in texts:
        if not t or not str(t).strip():
            continue
        sample += 1
        low = str(t).lower()
        hit_neg = [w for w in neg_words if w in low]
        hit_pos = [w for w in pos_words if w in low]
        if hit_neg:
            neg_hits.append({"text": t.strip()[:160], "matched": hit_neg})
        pos_hits += len(hit_pos)
    total_signal = len(neg_hits) + pos_hits
    if total_signal == 0:
        return 0.0, [], 0, sample
    score = (pos_hits - len(neg_hits)) / total_signal
    return round(score, 2), neg_hits[:8], pos_hits, sample


def compute_signals(pdata: ProjectData, cfg_path="config/rag_config.yaml") -> SignalPayload:
    cfg = _load_cfg(cfg_path)
    df = pdata.tasks
    leaf = df[df["_depth"].fillna(0) >= 2] if df["_depth"].notna().any() else df
    if leaf.empty:
        leaf = df

    # --- data confidence ---
    required = cfg["data_confidence"]["required_fields"]
    missing = [f for f in required if not pdata.field_presence.get(f, False)]
    penalty = cfg["data_confidence"]["penalty_per_missing_field_pct"]
    confidence = max(0.0, 100.0 - penalty * len(missing))
    conf_notes = list(pdata.warnings)
    if missing:
        conf_notes.append(f"Missing/empty required fields project-wide: {', '.join(missing)}")

    # --- schedule ---
    pct_complete = None
    if "% Complete" in df.columns:
        root = df[df["_depth"].fillna(99) == 0]
        if not root.empty and pd.notna(root["% Complete"].iloc[0]):
            pct_complete = float(root["% Complete"].iloc[0])
        elif df["% Complete"].notna().any():
            pct_complete = float(pd.to_numeric(df["% Complete"], errors="coerce").mean())

    var_series = leaf["_variance_days"].dropna()
    tasks_with_variance = int(var_series.shape[0])
    pct_slipped = float((var_series < 0).mean() * 100) if tasks_with_variance else 0.0
    mean_var = float(var_series.mean()) if tasks_with_variance else None
    worst_var, worst_task = None, None
    if tasks_with_variance:
        idx = var_series.idxmin()
        worst_var = float(var_series.loc[idx])
        worst_task = str(leaf.loc[idx, "Task Name"]) if pd.notna(leaf.loc[idx, "Task Name"]) else None

    # chronological cumulative-variance trend, using actual completed-task finish
    # dates only (Status == 'Completed'), so the trend line reflects real history
    # up to today rather than future-scheduled finish dates of open tasks.
    trend_rows = leaf[leaf["Status"] == "Completed"].dropna(subset=["_variance_days"]).copy()
    date_col = "_End_Date" if "_End_Date" in trend_rows.columns else None
    variance_trend = []
    if date_col and trend_rows[date_col].notna().any():
        trend_rows = trend_rows[trend_rows[date_col] <= TODAY].dropna(subset=[date_col]).sort_values(date_col)
        trend_rows["_cummean"] = trend_rows["_variance_days"].expanding().mean()
        step = max(1, len(trend_rows) // 8)
        for i in range(0, len(trend_rows), step):
            row = trend_rows.iloc[i]
            variance_trend.append((row[date_col].strftime("%Y-%m-%d"), round(float(row["_cummean"]), 1)))
        if len(trend_rows):
            last = trend_rows.iloc[-1]
            variance_trend.append((last[date_col].strftime("%Y-%m-%d"), round(float(last["_cummean"]), 1)))

    # --- milestones / phases ---
    phase_rag_counts = {}
    phases_red = []
    current_phase = pdata.summary_raw.get("Project Stage")
    if "_phase" in df.columns:
        phase_level_rows = df[df["_depth"].fillna(99) == 1]
        for _, r in phase_level_rows.iterrows():
            rag = r["_rag"]
            name = r["Task Name"]
            if pd.isna(name):
                continue
            phase_rag_counts[name] = rag if pd.notna(rag) else "Unknown"
            if rag == "Red":
                phases_red.append(name)
        if not current_phase:
            in_prog = phase_level_rows[phase_level_rows["Status"] == "In Progress"]
            if not in_prog.empty:
                current_phase = in_prog.iloc[0]["Task Name"]

    # NOTE: blockers/stalled/overdue/critical checks all run on `leaf` (depth>=2)
    # tasks only. Depth 0/1 rows are project- and phase-level rollups that mirror
    # their children's stats, so including them would double-count and would also
    # surface the project's own root row as if it were an individual blocked task.
    overdue_ns = leaf[
        (leaf["Status"] == "Not Started")
        & leaf.get("_Baseline_Finish", pd.Series(dtype="datetime64[ns]")).notna()
        & (leaf.get("_Baseline_Finish") < TODAY)
    ] if "_Baseline_Finish" in leaf.columns else leaf.iloc[0:0]
    overdue_examples = overdue_ns["Task Name"].dropna().head(5).tolist()

    # --- blockers ---
    on_hold_rows = leaf[leaf["_on_hold"] == True]
    at_risk_rows = leaf[leaf["_at_risk"] == True]
    stalled = leaf[
        (leaf["Status"] == "In Progress")
        & leaf.get("_Baseline_Finish", pd.Series(dtype="datetime64[ns]")).notna()
        & (leaf.get("_Baseline_Finish") < TODAY)
    ] if "_Baseline_Finish" in leaf.columns else leaf.iloc[0:0]
    neg_float_crit = leaf[(leaf["_critical"] == True) & (leaf["_total_float"] < 0)] if "_total_float" in leaf.columns else leaf.iloc[0:0]

    # --- critical path ---
    crit = leaf[leaf["_critical"] == True]
    crit_slipped = crit[crit["_variance_days"].fillna(0) < 0] if "_variance_days" in crit.columns else crit.iloc[0:0]

    # --- sentiment ---
    texts = list(df["_task_text"].dropna())
    texts += [c["text"] for c in pdata.comments if c.get("text")]
    sentiment_score, neg_hits, pos_hits, sample = _lexical_sentiment(texts, cfg["sentiment_lexicon"])

    # --- resourcing ---
    owner_col = "Owner" if "Owner" in df.columns and df["Owner"].notna().any() else (
        "Assigned To" if "Assigned To" in df.columns else None
    )
    unique_owners, concentration = 0, 0.0
    if owner_col:
        owners = df[owner_col].dropna()
        # 'Assigned To' can hold comma-separated lists; explode for a fair count
        exploded = owners.astype(str).str.split(",").explode().str.strip()
        exploded = exploded[exploded != ""]
        if len(exploded):
            counts = exploded.value_counts()
            unique_owners = int(counts.shape[0])
            concentration = float(counts.iloc[0] / counts.sum() * 100)

    as_of_raw = pdata.summary_raw.get("Today's Date")
    as_of = pd.Timestamp(as_of_raw).strftime("%Y-%m-%d") if as_of_raw is not None else TODAY.strftime("%Y-%m-%d")

    return SignalPayload(
        project_name=pdata.project_name,
        project_manager=pdata.project_manager,
        as_of=as_of,
        data_confidence_pct=confidence,
        data_confidence_notes=conf_notes,
        pct_complete=pct_complete,
        total_tasks=int(len(leaf)),
        tasks_with_variance=tasks_with_variance,
        pct_tasks_slipped=round(pct_slipped, 1),
        mean_variance_days=round(mean_var, 1) if mean_var is not None else None,
        worst_variance_days=worst_var,
        worst_variance_task=worst_task,
        variance_trend=variance_trend,
        current_phase=current_phase,
        phase_rag_counts=phase_rag_counts,
        phases_red=phases_red,
        overdue_not_started=int(len(overdue_ns)),
        overdue_not_started_examples=overdue_examples,
        on_hold_count=int(len(on_hold_rows)),
        on_hold_examples=on_hold_rows["Task Name"].dropna().head(5).tolist(),
        at_risk_count=int(len(at_risk_rows)),
        stalled_in_progress=int(len(stalled)),
        stalled_in_progress_examples=stalled["Task Name"].dropna().head(5).tolist(),
        negative_float_critical_count=int(len(neg_float_crit)),
        critical_total=int(len(crit)),
        critical_slipped=int(len(crit_slipped)),
        critical_slipped_examples=crit_slipped["Task Name"].dropna().head(5).tolist(),
        sentiment_score=sentiment_score,
        sentiment_negative_hits=neg_hits,
        sentiment_positive_hits=pos_hits,
        sentiment_sample_size=sample,
        unique_owners=unique_owners,
        owner_concentration_pct=round(concentration, 1),
        raw_task_level_rag_counts={k: int(v) for k, v in df["_rag"].value_counts(dropna=False).to_dict().items()},
    )


def to_dict(payload: SignalPayload) -> dict:
    return asdict(payload)
