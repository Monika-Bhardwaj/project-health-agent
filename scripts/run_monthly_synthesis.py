#!/usr/bin/env python3
"""
Run the Phase 3 monthly executive synthesis: aggregates every project's
latest snapshot in data/history/ into outputs/monthly/portfolio_synthesis.json.

Usage:
    python scripts/run_monthly_synthesis.py

Run this after scripts/run_weekly_report.py has produced at least one
snapshot per project. In production, run it once a month (or on-demand
before a client business review) after that week's reports have landed.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.synthesis import build_portfolio_synthesis

if __name__ == "__main__":
    result = build_portfolio_synthesis()
    print(f"Synthesized {len(result['projects'])} project(s).")
    print(f"Trends found: {len(result['trends'])} | Risks: {len(result['risks'])} | "
          f"Recommendations: {len(result['recommendations'])}")
    print("Written to outputs/monthly/portfolio_synthesis.json")
