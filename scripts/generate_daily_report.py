#!/usr/bin/env python3
"""
DATS — Live Paper Trading Daily Report Generator
Version: 1.0
Date: 2026-09-05

Reads data/live_trading.db and prints a report for one UTC calendar
day (default: today), or an arbitrary window with --days-back N (a
rolling N-day report, e.g. for a weekly summary).

No new dashboard, no new API surface — a CLI report generator only,
consistent with the mission's "stop building new dashboards."

Run inside the app container:

    docker exec dats-beta python scripts/generate_daily_report.py
    docker exec dats-beta python scripts/generate_daily_report.py --days-back 7
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from live_trading.daily_report import generate_daily_report, generate_report  # noqa: E402
from live_trading.trade_log import LiveTradeStore  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a live paper-trading report.")
    parser.add_argument("--days-back", type=int, default=0, help="Report over the trailing N days instead of one calendar day.")
    parser.add_argument("--data-dir", default="./data", help="Directory containing live_trading.db.")
    args = parser.parse_args()

    store = LiveTradeStore(data_dir=args.data_dir)

    if args.days_back > 0:
        end_ts = time.time()
        start_ts = end_ts - args.days_back * 86400
        report = generate_report(store, start_ts, end_ts)
        print(f"=== Live Paper Trading Report — trailing {args.days_back} day(s) ===")
    else:
        report = generate_daily_report(store, datetime.now(timezone.utc))
        print("=== Live Paper Trading Daily Report (UTC today) ===")

    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
