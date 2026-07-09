"""
Basic tests for the deterministic parts of the agent (ingest, signals,
rag_engine). Run with: python -m pytest tests/ -v

These intentionally do NOT test narrative.py's LLM path (no network calls in
tests) — narrative.py's fallback path is deterministic and covered here via
rag_engine outputs feeding into report.render_markdown.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from agent.ingest import load_project, _parse_day_delta, _normalize_rag
from agent.signals import compute_signals
from agent.rag_engine import evaluate
from agent.narrative import generate
from agent.report import render_markdown

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.mark.parametrize("raw,expected", [
    ("-2d", -2), ("15d", 15), ("0", 0), (0, 0), (-5.0, -5), (None, None), ("#UNPARSEABLE", None),
])
def test_parse_day_delta(raw, expected):
    assert _parse_day_delta(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("Green", "Green"), ("red", "Red"), ("YELLOW", "Yellow"), ("purple", None), (None, None),
])
def test_normalize_rag(raw, expected):
    assert _normalize_rag(raw) == expected


@pytest.mark.skipif(not (DATA_DIR / "S2P_Project.xlsx").exists(), reason="sample data not present")
def test_ingest_s2p_smoke():
    p = load_project(DATA_DIR / "S2P_Project.xlsx")
    assert p.project_name.startswith("Zycus")
    assert len(p.tasks) > 100
    assert "_rag" in p.tasks.columns


@pytest.mark.skipif(not (DATA_DIR / "Project_Plan_B.xlsx").exists(), reason="sample data not present")
def test_ingest_handles_missing_rag_column():
    p = load_project(DATA_DIR / "Project_Plan_B.xlsx")
    assert any("Schedule Health" in w for w in p.warnings)


@pytest.mark.skipif(not (DATA_DIR / "S2P_Project.xlsx").exists(), reason="sample data not present")
def test_full_pipeline_produces_valid_status():
    p = load_project(DATA_DIR / "S2P_Project.xlsx")
    s = compute_signals(p)
    v = evaluate(s)
    assert v.status in ("Red", "Amber", "Green")
    assert 0 <= v.composite_score <= 100
    assert len(v.reasoning_trail) > 0

    n = generate(s, v, {"enabled_by_default": False})
    assert n["mode"] == "deterministic_fallback"
    md = render_markdown(s, v, n, p.warnings)
    assert v.status in md
    assert "Signal scorecard" in md


def test_overrides_can_only_worsen_status():
    """An override that fires should never move status from Red/Amber to Green."""
    from agent.signals import SignalPayload
    base_kwargs = dict(
        project_name="Test", project_manager="PM", as_of="2026-01-01",
        data_confidence_pct=100, data_confidence_notes=[],
        pct_complete=0.9, total_tasks=10, tasks_with_variance=10,
        pct_tasks_slipped=0, mean_variance_days=0, worst_variance_days=0, worst_variance_task="x",
        variance_trend=[], current_phase="Go Live", phase_rag_counts={}, phases_red=[],
        overdue_not_started=0, overdue_not_started_examples=[],
        on_hold_count=0, on_hold_examples=[], at_risk_count=0,
        stalled_in_progress=0, stalled_in_progress_examples=[],
        negative_float_critical_count=0, critical_total=5, critical_slipped=0,
        critical_slipped_examples=[], sentiment_score=0.5, sentiment_negative_hits=[],
        sentiment_positive_hits=5, sentiment_sample_size=5, unique_owners=5,
        owner_concentration_pct=20, raw_task_level_rag_counts={"Green": 10},
    )
    good = SignalPayload(**base_kwargs)
    v = evaluate(good)
    assert v.status == "Green"

    bad_kwargs = dict(base_kwargs)
    bad_kwargs.update(critical_slipped=3)
    bad = SignalPayload(**bad_kwargs)
    v2 = evaluate(bad)
    assert v2.status in ("Amber", "Red")  # never Green once the override fires
