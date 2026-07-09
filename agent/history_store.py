"""
agent/history_store.py
=======================
Every time the agent runs, it appends one JSON snapshot per project to
data/history/<project_slug>.jsonl. This is what makes week-over-week and
month-over-month trending possible without a database: the file is the
database, it's human-readable, and it's diffable in git.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

HISTORY_DIR = Path("data/history")


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def append_snapshot(project_name: str, run_date: str, signals_dict: dict, verdict_dict: dict) -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = HISTORY_DIR / f"{_slug(project_name)}.jsonl"
    record = {
        "run_date": run_date,
        "logged_at": datetime.utcnow().isoformat() + "Z",
        "signals": signals_dict,
        "verdict": verdict_dict,
    }
    with open(path, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")
    return path


def load_history(project_name: str) -> list[dict]:
    path = HISTORY_DIR / f"{_slug(project_name)}.jsonl"
    if not path.exists():
        return []
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def all_project_slugs() -> list[str]:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    return [p.stem for p in HISTORY_DIR.glob("*.jsonl")]
