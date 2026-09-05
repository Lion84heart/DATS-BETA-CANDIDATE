"""Persistence for the live paper-trading pipeline.

A separate SQLite file (``data/live_trading.db``, inside the same
mounted ``./data`` volume every other durable piece of this app's
state already uses) so this is fully additive — it never touches the
existing ``data/decisions.db`` schema or the code that manages it.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TradeRecord:
    """Everything the mission asked to record for one trade."""

    trade_id: str
    symbol: str
    opened_at: float
    entry_price: float
    quantity: float
    stop_loss_price: float | None
    take_profit_price: float | None
    entry_confidence: float
    entry_reasoning: str
    entry_votes: list[dict[str, Any]] = field(default_factory=list)
    closed_at: float | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    exit_confidence: float | None = None
    exit_reasoning: str | None = None
    exit_votes: list[dict[str, Any]] = field(default_factory=list)
    pnl: float | None = None
    pnl_pct: float | None = None
    fees: float = 0.0
    holding_seconds: float | None = None
    status: str = "OPEN"  # "OPEN" | "CLOSED"


class LiveTradeStore:
    """SQLite-backed store for live paper trades and equity snapshots."""

    def __init__(self, data_dir: str | Path = "./data") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "live_trading.db"
        # check_same_thread=False: accessed from feed-tick callbacks and any
        # report-generation script, all on the same asyncio event loop
        # thread but not necessarily the same asyncio task.
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS live_trades (
                trade_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                opened_at REAL NOT NULL,
                entry_price REAL NOT NULL,
                quantity REAL NOT NULL,
                stop_loss_price REAL,
                take_profit_price REAL,
                entry_confidence REAL,
                entry_reasoning TEXT,
                entry_votes TEXT,
                closed_at REAL,
                exit_price REAL,
                exit_reason TEXT,
                exit_confidence REAL,
                exit_reasoning TEXT,
                exit_votes TEXT,
                pnl REAL,
                pnl_pct REAL,
                fees REAL DEFAULT 0.0,
                holding_seconds REAL,
                status TEXT NOT NULL DEFAULT 'OPEN'
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS equity_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                equity REAL NOT NULL,
                cash REAL NOT NULL,
                open_position_count INTEGER NOT NULL
            )
            """
        )
        self._conn.commit()

    def open_trade(
        self, symbol: str, entry_price: float, quantity: float,
        stop_loss_price: float | None, take_profit_price: float | None,
        entry_confidence: float, entry_reasoning: str, entry_votes: list[dict[str, Any]],
    ) -> str:
        trade_id = str(uuid.uuid4())
        self._conn.execute(
            """INSERT INTO live_trades
               (trade_id, symbol, opened_at, entry_price, quantity, stop_loss_price,
                take_profit_price, entry_confidence, entry_reasoning, entry_votes, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')""",
            (
                trade_id, symbol, time.time(), entry_price, quantity, stop_loss_price,
                take_profit_price, entry_confidence, entry_reasoning, json.dumps(entry_votes),
            ),
        )
        self._conn.commit()
        return trade_id

    def close_trade(
        self, trade_id: str, exit_price: float, fees: float, exit_reason: str,
        exit_confidence: float | None, exit_reasoning: str | None, exit_votes: list[dict[str, Any]],
    ) -> None:
        row = self._conn.execute(
            "SELECT entry_price, quantity, opened_at FROM live_trades WHERE trade_id = ?", (trade_id,),
        ).fetchone()
        if row is None:
            return
        entry_price, quantity, opened_at = row
        closed_at = time.time()
        pnl = (exit_price - entry_price) * quantity - fees
        pnl_pct = (exit_price - entry_price) / entry_price * 100.0 if entry_price else 0.0
        holding_seconds = closed_at - opened_at

        self._conn.execute(
            """UPDATE live_trades SET closed_at=?, exit_price=?, exit_reason=?, exit_confidence=?,
               exit_reasoning=?, exit_votes=?, pnl=?, pnl_pct=?, fees=?, holding_seconds=?, status='CLOSED'
               WHERE trade_id=?""",
            (
                closed_at, exit_price, exit_reason, exit_confidence, exit_reasoning,
                json.dumps(exit_votes), pnl, pnl_pct, fees, holding_seconds, trade_id,
            ),
        )
        self._conn.commit()

    def record_equity_snapshot(self, equity: float, cash: float, open_position_count: int) -> None:
        self._conn.execute(
            "INSERT INTO equity_snapshots (timestamp, equity, cash, open_position_count) VALUES (?, ?, ?, ?)",
            (time.time(), equity, cash, open_position_count),
        )
        self._conn.commit()

    def get_open_trades(self, symbol: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM live_trades WHERE status='OPEN'"
        params: tuple = ()
        if symbol is not None:
            query += " AND symbol=?"
            params = (symbol,)
        return self._rows_as_dicts(query, params)

    def get_trades_between(self, start_ts: float, end_ts: float) -> list[dict[str, Any]]:
        return self._rows_as_dicts(
            "SELECT * FROM live_trades WHERE opened_at >= ? AND opened_at < ? ORDER BY opened_at",
            (start_ts, end_ts),
        )

    def get_all_trades(self) -> list[dict[str, Any]]:
        return self._rows_as_dicts("SELECT * FROM live_trades ORDER BY opened_at", ())

    def get_equity_curve_between(self, start_ts: float, end_ts: float) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT timestamp, equity, cash, open_position_count FROM equity_snapshots "
            "WHERE timestamp >= ? AND timestamp < ? ORDER BY timestamp",
            (start_ts, end_ts),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def _rows_as_dicts(self, query: str, params: tuple) -> list[dict[str, Any]]:
        cur = self._conn.execute(query, params)
        cols = [d[0] for d in cur.description]
        rows = []
        for row in cur.fetchall():
            record = dict(zip(cols, row))
            for key in ("entry_votes", "exit_votes"):
                if record.get(key):
                    try:
                        record[key] = json.loads(record[key])
                    except (json.JSONDecodeError, TypeError):
                        pass
            rows.append(record)
        return rows
