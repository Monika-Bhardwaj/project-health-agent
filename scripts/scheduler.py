#!/usr/bin/env python3
"""
Standalone weekly scheduler (bonus, alternative to the GitHub Actions
workflow in .github/workflows/weekly_report.yml). Useful if you want to run
the agent on a long-lived server/VM instead of CI.

Usage:
    pip install apscheduler
    python scripts/scheduler.py                  # runs every Monday 06:00 local time
    python scripts/scheduler.py --cron "0 6 * * MON"  # custom cron
    python scripts/scheduler.py --run-now         # also run immediately on start
"""
import argparse
import glob
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_agent():
    files = glob.glob(str(ROOT / "data" / "*.xlsx"))
    if not files:
        print("No .xlsx files found in data/ — nothing to run.")
        return
    subprocess.run([sys.executable, str(ROOT / "scripts" / "run_weekly_report.py"), *files], check=False)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "run_monthly_synthesis.py")], check=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cron", default="0 6 * * MON", help="cron expression (default: Monday 06:00)")
    ap.add_argument("--run-now", action="store_true")
    args = ap.parse_args()

    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        print("APScheduler is not installed. Run: pip install apscheduler")
        print("(Alternatively, use the GitHub Actions workflow in .github/workflows/weekly_report.yml,")
        print(" or add scripts/run_weekly_report.py to any system cron / Task Scheduler.)")
        sys.exit(1)

    if args.run_now:
        run_agent()

    scheduler = BlockingScheduler()
    scheduler.add_job(run_agent, CronTrigger.from_crontab(args.cron))
    print(f"Scheduler started. Next run per cron '{args.cron}'. Ctrl+C to stop.")
    scheduler.start()


if __name__ == "__main__":
    main()
