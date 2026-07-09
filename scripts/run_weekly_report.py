#!/usr/bin/env python3
"""
Run the Project Health Reporting Agent for one or more project-plan files.

Usage:
    python scripts/run_weekly_report.py data/S2P_Project.xlsx
    python scripts/run_weekly_report.py data/*.xlsx
    python scripts/run_weekly_report.py data/S2P_Project.xlsx --no-llm

Each run:
  1. Ingests the raw .xlsx (handles messy/incomplete data automatically)
  2. Computes deterministic signals
  3. Evaluates the RAG status via the rules engine
  4. Generates plain-English reasoning (LLM if ANTHROPIC_API_KEY is set, else
     a deterministic fallback narrative — both draw on the same verified facts)
  5. Writes a Markdown report to outputs/weekly/
  6. Appends a JSON snapshot to data/history/ for trend tracking
"""
import argparse
import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.ingest import load_project
from agent.signals import compute_signals, to_dict as signals_to_dict
from agent.rag_engine import evaluate, to_dict as verdict_to_dict
from agent.narrative import generate
from agent.report import write_report
from agent.history_store import append_snapshot
import yaml


def run_one(path: str, cfg: dict, use_llm: bool) -> None:
    pdata = load_project(path)
    signals = compute_signals(pdata)
    verdict = evaluate(signals)

    llm_cfg = dict(cfg.get("llm", {}))
    llm_cfg["enabled_by_default"] = use_llm and llm_cfg.get("enabled_by_default", True)
    narrative = generate(signals, verdict, llm_cfg)

    report_path = write_report(signals, verdict, narrative, pdata.warnings)
    snapshot_path = append_snapshot(signals.project_name, signals.as_of, signals_to_dict(signals), verdict_to_dict(verdict))

    print(f"[{signals.project_name}] STATUS={verdict.status} score={verdict.composite_score} "
          f"narrative_mode={narrative['mode']}")
    print(f"  report   -> {report_path}")
    print(f"  history  -> {snapshot_path}")

    # Also emit a machine-readable JSON alongside the Markdown, for any
    # downstream system (e.g. a dashboard, or the monthly synthesis step)
    json_path = report_path.with_suffix(".json")
    json_path.write_text(json.dumps({
        "signals": signals_to_dict(signals),
        "verdict": verdict_to_dict(verdict),
        "narrative": narrative,
        "data_quality_warnings": pdata.warnings,
    }, default=str, indent=2))
    print(f"  json     -> {json_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="Path(s) or glob(s) to project-plan .xlsx files")
    ap.add_argument("--config", default="config/rag_config.yaml")
    ap.add_argument("--no-llm", action="store_true", help="Force the deterministic fallback narrative (no API calls)")
    args = ap.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    paths = []
    for pattern in args.files:
        matched = glob.glob(pattern)
        paths.extend(matched if matched else [pattern])

    if not paths:
        print("No input files matched.", file=sys.stderr)
        sys.exit(1)

    for p in paths:
        run_one(p, cfg, use_llm=not args.no_llm)


if __name__ == "__main__":
    main()
