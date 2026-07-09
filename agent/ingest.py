"""
agent/ingest.py
================
Reads a raw project-plan .xlsx export (Smartsheet / MS-Project style) and
turns it into a clean, normalized ProjectData object.

Design principle: ingestion NEVER raises on messy input. Every real-world
export we were handed (S2P_Project.xlsx, Project_Plan_B.xlsx) has a
different set of populated columns, different casing, string-typed numeric
fields ("-2d"), and placeholder values like "#UNPARSEABLE". This module's
whole job is to absorb that mess once, in one place, so every downstream
module (signals, rag_engine, narrative) can assume clean types.
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

PLACEHOLDER_VALUES = {"#UNPARSEABLE", "#N/A", "N/A", "", "NaT", "nan"}


def _clean_scalar(v):
    if pd.isna(v):
        return None
    if isinstance(v, str) and v.strip() in PLACEHOLDER_VALUES:
        return None
    return v


def _parse_day_delta(v) -> Optional[int]:
    """Parse values like '-2d', '15d', '0', 0, or None into an int day count."""
    v = _clean_scalar(v)
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(round(v))
    m = re.match(r"^(-?\d+)\s*d?$", str(v).strip(), re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def _parse_bool_flag(v) -> bool:
    v = _clean_scalar(v)
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    return str(v).strip().upper() in {"TRUE", "YES", "Y", "1"}


def _normalize_rag(v) -> Optional[str]:
    v = _clean_scalar(v)
    if v is None:
        return None
    v = str(v).strip().title()
    return v if v in {"Red", "Amber", "Yellow", "Green"} else None


@dataclass
class ProjectData:
    source_file: str
    project_name: str
    project_manager: str
    sheet_name: str
    tasks: pd.DataFrame                 # normalized task-level table
    summary_raw: dict                   # key/value pairs from the "Summary" sheet, as given
    comments: list                      # list of dicts: {row_ref, text, author, timestamp}
    field_presence: dict                # which expected fields existed / were populated
    warnings: list = field(default_factory=list)  # ingestion-time data-quality notes


def _find_main_sheet(xl: pd.ExcelFile) -> str:
    candidates = [s for s in xl.sheet_names if s.lower() not in ("comments", "summary")]
    return candidates[0] if candidates else xl.sheet_names[0]


def _load_comments(xl: pd.ExcelFile) -> list:
    if "Comments" not in xl.sheet_names:
        return []
    raw = xl.parse("Comments", header=None)
    out = []
    for _, row in raw.iterrows():
        vals = [_clean_scalar(x) for x in row.tolist()]
        vals = [x for x in vals if x is not None]
        if len(vals) >= 2 and isinstance(vals[0], str) and vals[0].lower().startswith("row"):
            out.append({
                "row_ref": vals[0],
                "text": vals[1] if len(vals) > 1 else "",
                "author": vals[2] if len(vals) > 2 else None,
                "timestamp": str(vals[3]) if len(vals) > 3 else None,
            })
    return out


def _load_summary(xl: pd.ExcelFile) -> dict:
    if "Summary" not in xl.sheet_names:
        return {}
    raw = xl.parse("Summary")
    out = {}
    if raw.shape[1] >= 2:
        for _, row in raw.iterrows():
            k = _clean_scalar(row.iloc[0])
            v = _clean_scalar(row.iloc[1])
            if k:
                out[str(k).strip()] = v
    return out


def load_project(path: str | Path) -> ProjectData:
    path = Path(path)
    xl = pd.ExcelFile(path)
    sheet = _find_main_sheet(xl)
    df = xl.parse(sheet)
    df.columns = [str(c).strip() for c in df.columns]

    # --- hierarchy depth: prefer 'Level', fall back to 'Ancestors' ---
    warns = []
    if "Level" in df.columns and df["Level"].notna().any():
        df["_depth"] = pd.to_numeric(df["Level"], errors="coerce")
    elif "Ancestors" in df.columns:
        df["_depth"] = pd.to_numeric(df["Ancestors"], errors="coerce")
        warns.append("No 'Level' column found; used 'Ancestors' as the WBS hierarchy depth instead.")
    else:
        df["_depth"] = 0
        warns.append("No hierarchy column found ('Level' or 'Ancestors'); all tasks treated as flat (depth 0).")

    # --- RAG: prefer explicit 'RAG' column, else fall back to 'Schedule Health' ---
    if "RAG" in df.columns and df["RAG"].notna().any():
        df["_rag"] = df["RAG"].apply(_normalize_rag)
        rag_source = "RAG"
    elif "Schedule Health" in df.columns:
        df["_rag"] = df["Schedule Health"].apply(_normalize_rag)
        rag_source = "Schedule Health"
        warns.append("No task-level 'RAG' column found; used 'Schedule Health' as a proxy for task color.")
    else:
        df["_rag"] = None
        rag_source = None
        warns.append("No RAG or Schedule Health column found; task-level color signal is unavailable.")
    df["_rag"] = df["_rag"].replace({"Yellow": "Amber"})

    # --- variance / duration / float as numeric days ---
    # Some exports (e.g. Project_Plan_B) leave the primary 'Variance'/'Baseline
    # Start'/'Baseline Finish' columns almost entirely blank at the task level
    # and instead populate a secondary '...2' column (an artifact of duplicate
    # column names in the source spreadsheet). We use whichever is actually
    # populated at leaf-task level, and record the substitution as a warning.
    def _leaf_populated(col):
        if col not in df.columns:
            return -1
        depth_leaf = df["_depth"].fillna(0) >= 2
        return df.loc[depth_leaf, col].notna().sum()

    variance_col = "Variance"
    if _leaf_populated("Variance") <= 0 and _leaf_populated("Variance2") > 0:
        variance_col = "Variance2"
        warns.append("'Variance' column was empty at task level; used 'Variance2' instead (duplicate-column artifact in source file).")
    df["_variance_days"] = df[variance_col].apply(_parse_day_delta) if variance_col in df.columns else None

    df["_duration_days"] = df["Duration"].apply(_parse_day_delta) if "Duration" in df.columns else None
    df["_total_float"] = pd.to_numeric(df.get("Total Float"), errors="coerce")

    # --- dates ---
    for col in ("Start Date", "End Date"):
        if col in df.columns:
            df[f"_{col.replace(' ', '_')}"] = pd.to_datetime(df[col], errors="coerce")

    for base_col, alt_col, out_name in (
        ("Baseline Start", "Baseline Start2", "_Baseline_Start"),
        ("Baseline Finish", "Baseline Finish2", "_Baseline_Finish"),
    ):
        chosen = base_col
        if _leaf_populated(base_col) <= 0 and _leaf_populated(alt_col) > 0:
            chosen = alt_col
            warns.append(f"'{base_col}' column was empty at task level; used '{alt_col}' instead (duplicate-column artifact in source file).")
        if chosen in df.columns:
            df[out_name] = pd.to_datetime(df[chosen], errors="coerce")

    # --- flags ---
    df["_on_hold"] = df["On Hold?"].apply(_parse_bool_flag) if "On Hold?" in df.columns else False
    df["_at_risk"] = df["At Risk?"].apply(_parse_bool_flag) if "At Risk?" in df.columns else False
    df["_critical"] = df["Critical ?"].apply(_parse_bool_flag) if "Critical ?" in df.columns else False
    df["_not_applicable"] = df["Not Applicable?"].apply(_parse_bool_flag) if "Not Applicable?" in df.columns else False

    # --- free text: merge 'Status Comment' + 'Comments' columns per row ---
    text_cols = [c for c in ("Status Comment", "Comments") if c in df.columns]
    if text_cols:
        df["_task_text"] = df[text_cols].apply(
            lambda r: " ".join(str(_clean_scalar(x)) for x in r if _clean_scalar(x)), axis=1
        )
    else:
        df["_task_text"] = ""

    df["Task Name"] = df["Task Name"].apply(_clean_scalar) if "Task Name" in df.columns else None
    df["Status"] = df["Status"].apply(_clean_scalar) if "Status" in df.columns else None

    # --- phase attribution: forward-fill from Phase/Milestone column at depth==1,
    #     falling back to the depth==1 Task Name when Phase/Milestone is blank ---
    if "Phase/Milestone" in df.columns and df["Phase/Milestone"].notna().any():
        phase_series = df["Phase/Milestone"].where(df["_depth"] <= 1)
    else:
        warns.append("Phase/Milestone column is empty; inferring phases from depth-1 task names instead.")
        phase_series = df["Task Name"].where(df["_depth"] == 1)
    df["_phase"] = phase_series.ffill()

    field_presence = {
        col: bool(df[col].notna().any()) if col in df.columns else False
        for col in ["Task Name", "Status", "Start Date", "End Date", "RAG", "Phase/Milestone",
                    "Owner", "Assigned To", "Status Comment", "Comments", "Total Float",
                    "Critical ?", "On Hold?", "At Risk?"]
    }
    field_presence["_rag_source"] = rag_source

    summary_raw = _load_summary(xl)
    comments = _load_comments(xl)

    project_name = None
    if len(df) and df["_depth"].iloc[0] == 0 and pd.notna(df.get("Task Name", pd.Series()).iloc[0] if "Task Name" in df.columns else None):
        project_name = df["Task Name"].iloc[0]
    if not project_name:
        project_name = summary_raw.get("Project Name") or path.stem

    project_manager = summary_raw.get("Project Manager")
    if not project_manager and "Project Manager" in df.columns:
        pm_vals = df["Project Manager"].dropna().unique()
        project_manager = pm_vals[0] if len(pm_vals) else "Unknown"

    return ProjectData(
        source_file=str(path.name),
        project_name=str(project_name),
        project_manager=str(project_manager) if project_manager else "Unknown",
        sheet_name=sheet,
        tasks=df,
        summary_raw=summary_raw,
        comments=comments,
        field_presence=field_presence,
        warnings=warns,
    )
