"""Continuous Learning & Decision Intelligence Framework.

Records every trading decision with full context for post-trade analysis,
continuous improvement, and external AI review.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path
from typing import Any


class DecisionPhase(Enum):
    """Phase of a trading decision lifecycle."""

    SIGNAL_GENERATED = auto()
    RISK_ASSESSED = auto()
    ORDER_SUBMITTED = auto()
    ORDER_FILLED = auto()
    POST_TRADE = auto()


@dataclass
class MarketSnapshot:
    """Market conditions at decision time."""

    symbol: str
    timestamp: float
    price: float
    bid: float
    ask: float
    volume_24h: float | None = None
    volatility_annual: float | None = None
    market_regime: str | None = None  # trending, mean_reverting, etc.


@dataclass
class FeatureVector:
    """ML features used for decision."""

    features: dict[str, float] = field(default_factory=dict)
    feature_names: list[str] = field(default_factory=list)
    model_version: str | None = None

    def to_array(self) -> list[float]:
        """Convert features to ordered array."""
        if self.feature_names:
            return [self.features.get(k, 0.0) for k in self.feature_names]
        return list(self.features.values())


@dataclass
class RiskAssessment:
    """Risk metrics at decision time."""

    var_95: float | None = None
    cvar_95: float | None = None
    max_drawdown: float | None = None
    position_size_pct: float | None = None
    leverage: float | None = None
    kill_switch_armed: bool = False
    passed_checks: list[str] = field(default_factory=list)
    failed_checks: list[str] = field(default_factory=list)


@dataclass
class PortfolioState:
    """Portfolio snapshot at decision time."""

    total_value: float
    cash: float
    unrealized_pnl: float
    open_positions: dict[str, dict[str, Any]] = field(default_factory=dict)
    sector_exposure: dict[str, float] = field(default_factory=dict)


@dataclass
class DecisionExecutionResult:
    """Order execution outcome."""

    order_id: str
    filled_qty: float
    avg_price: float
    slippage_bps: float
    commission: float
    execution_time_ms: float
    status: str


@dataclass
class DecisionRecord:
    """Complete record of a single trading decision.

    Captures the full context from signal generation through
    execution for later analysis and learning.
    """

    # Identity
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    phase: DecisionPhase = DecisionPhase.SIGNAL_GENERATED

    # Market context
    market_snapshot: MarketSnapshot | None = None

    # AI reasoning
    feature_vector: FeatureVector | None = None
    reasoning_summary: str = ""
    confidence_score: float = 0.0  # 0.0 to 1.0

    # Recommendation — BUY, SELL, or HOLD. Advisory only: nothing in this
    # module ever submits an order. A human must act through the separate,
    # existing manual order-entry flow to execute anything.
    signal: str | None = None
    risk_level: str | None = None  # LOW, MEDIUM, HIGH

    # Strategy
    selected_strategy: str = ""
    strategy_parameters: dict[str, Any] = field(default_factory=dict)

    # Risk
    risk_assessment: RiskAssessment | None = None

    # Portfolio
    portfolio_state: PortfolioState | None = None

    # Execution
    execution_result: DecisionExecutionResult | None = None

    # Outcome (filled in post-trade)
    exit_price: float | None = None
    exit_timestamp: float | None = None
    realized_pnl: float | None = None
    holding_period_seconds: float | None = None
    outcome_label: str | None = None  # win, loss, breakeven

    # Metadata
    tags: dict[str, str] = field(default_factory=dict)
    version: str = "1.0"

    @property
    def duration_ms(self) -> float | None:
        """Time from decision to execution in milliseconds."""
        if self.execution_result:
            return self.execution_result.execution_time_ms
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        result = asdict(self)
        result["phase"] = self.phase.name
        return result

    def to_json(self, indent: int | None = None) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def set_outcome(
        self,
        exit_price: float,
        exit_timestamp: float,
        realized_pnl: float,
        label: str,
    ) -> None:
        """Set post-trade outcome."""
        self.exit_price = exit_price
        self.exit_timestamp = exit_timestamp
        self.realized_pnl = realized_pnl
        self.outcome_label = label
        self.holding_period_seconds = exit_timestamp - self.timestamp
        self.phase = DecisionPhase.POST_TRADE


@dataclass
class DecisionPackage:
    """A collection of decisions packaged for external AI review.

    Used for engineering review, strategy improvement, and
    continuous learning analysis.
    """

    package_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)
    description: str = ""
    decisions: list[DecisionRecord] = field(default_factory=list)
    summary_statistics: dict[str, Any] = field(default_factory=dict)

    def add(self, decision: DecisionRecord) -> None:
        """Add a decision to the package."""
        self.decisions.append(decision)

    def generate_report(self) -> dict[str, Any]:
        """Generate structured review report."""
        total = len(self.decisions)
        if total == 0:
            return {"package_id": self.package_id, "total_decisions": 0}

        outcomes = [d.outcome_label for d in self.decisions if d.outcome_label]
        wins = outcomes.count("win")
        losses = outcomes.count("loss")

        return {
            "package_id": self.package_id,
            "created_at": _iso(self.created_at),
            "description": self.description,
            "total_decisions": total,
            "outcomes": {
                "wins": wins,
                "losses": losses,
                "breakeven": outcomes.count("breakeven"),
                "pending": total - len(outcomes),
            },
            "win_rate": wins / (wins + losses) if (wins + losses) > 0 else None,
            "avg_confidence": sum(d.confidence_score for d in self.decisions) / total,
            "strategies_used": list(set(d.selected_strategy for d in self.decisions)),
            "total_pnl": sum(
                (d.realized_pnl or 0) for d in self.decisions
            ),
            "avg_slippage_bps": sum(
                (d.execution_result.slippage_bps if d.execution_result else 0)
                for d in self.decisions
            ) / total,
        }

    def export(self, path: str | Path) -> None:
        """Export package to JSON file."""
        data = {
            "package_id": self.package_id,
            "created_at": self.created_at,
            "description": self.description,
            "report": self.generate_report(),
            "decisions": [d.to_dict() for d in self.decisions],
        }
        Path(path).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


class DecisionStore:
    """Persistent store for decision records — backed by SQLite.

    A single-file relational database (Python's stdlib ``sqlite3``, no new
    dependency or service to run) rather than one JSON file per decision.
    The database file lives under ``data_dir`` (default ``./data``, which
    resolves to the ``./data:/app/data`` volume already mounted in
    docker-compose), so decisions genuinely persist across container
    restarts instead of being lost.
    """

    def __init__(self, data_dir: str | Path = "./data"):
        """Initialize decision store.

        Args:
            data_dir: Directory holding the ``decisions.db`` SQLite file.
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "decisions.db"
        # check_same_thread=False: a single shared connection is accessed
        # from request handlers and feed-tick callbacks, all on the same
        # asyncio event loop thread, but not necessarily the same asyncio
        # Task — sqlite3 only cares about OS thread identity here.
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decisions (
                decision_id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                symbol TEXT,
                strategy TEXT,
                signal TEXT,
                outcome TEXT,
                data TEXT NOT NULL
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_timestamp ON decisions(timestamp)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_symbol ON decisions(symbol)")

        # Every individual Strategy Engine result that fed into a fused
        # decision (Sprint 4) — one row per (decision, strategy).
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_id TEXT NOT NULL,
                symbol TEXT,
                timestamp REAL,
                strategy TEXT NOT NULL,
                signal TEXT NOT NULL,
                confidence REAL NOT NULL,
                reasoning TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_strategy_results_decision ON strategy_results(decision_id)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_strategy_results_symbol ON strategy_results(symbol, timestamp)"
        )

        # Completed backtest runs (Sprint 5) — one row per run, with the
        # full report (metrics, confusion stats, trades, decision log)
        # stored as JSON so it can be re-exported later without re-running.
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS backtest_runs (
                run_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                started_at REAL NOT NULL,
                completed_at REAL NOT NULL,
                num_bars INTEGER NOT NULL,
                total_return_pct REAL,
                sharpe_ratio REAL,
                number_of_trades INTEGER,
                data TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_backtest_runs_started ON backtest_runs(started_at)"
        )
        self._conn.commit()

    def save_backtest_run(self, report_dict: dict[str, Any]) -> None:
        """Persist a completed backtest run (as produced by report_to_dict).

        Args:
            report_dict: The full backtest report, already JSON-shaped.
        """
        metrics = report_dict.get("portfolio_metrics", {})
        self._conn.execute(
            """
            INSERT INTO backtest_runs
                (run_id, symbol, started_at, completed_at, num_bars,
                 total_return_pct, sharpe_ratio, number_of_trades, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET data=excluded.data
            """,
            (
                report_dict["run_id"], report_dict["symbol"], report_dict["started_at"],
                report_dict["completed_at"], report_dict["num_bars"],
                metrics.get("total_return_pct"), metrics.get("sharpe_ratio"),
                metrics.get("number_of_trades"), json.dumps(report_dict, default=str),
            ),
        )
        self._conn.commit()

    def get_backtest_run(self, run_id: str) -> dict[str, Any] | None:
        """Load one full backtest report by run_id."""
        row = self._conn.execute(
            "SELECT data FROM backtest_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def list_backtest_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        """List backtest runs newest-first, with summary columns only."""
        rows = self._conn.execute(
            """
            SELECT run_id, symbol, started_at, completed_at, num_bars,
                   total_return_pct, sharpe_ratio, number_of_trades
            FROM backtest_runs ORDER BY started_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "run_id": r[0], "symbol": r[1], "started_at": r[2], "completed_at": r[3],
                "num_bars": r[4], "total_return_pct": r[5], "sharpe_ratio": r[6], "number_of_trades": r[7],
            }
            for r in rows
        ]

    def save_strategy_results(
        self,
        decision_id: str,
        symbol: str,
        timestamp: float,
        results: list[dict[str, Any]],
    ) -> None:
        """Persist every individual strategy result behind a fused decision.

        Args:
            decision_id: The fused DecisionRecord these results fed into.
            symbol: Trading symbol analyzed.
            timestamp: Analysis timestamp.
            results: One dict per strategy with keys 'strategy', 'signal',
                'confidence', 'reasoning'.
        """
        self._conn.executemany(
            """
            INSERT INTO strategy_results (decision_id, symbol, timestamp, strategy, signal, confidence, reasoning)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (decision_id, symbol, timestamp, r["strategy"], r["signal"], r["confidence"], r["reasoning"])
                for r in results
            ],
        )
        self._conn.commit()

    def get_strategy_results(self, decision_id: str) -> list[dict[str, Any]]:
        """Get every individual strategy result behind one fused decision.

        Args:
            decision_id: The fused decision to look up.

        Returns:
            One dict per strategy (strategy, signal, confidence, reasoning),
            in the order they were recorded.
        """
        rows = self._conn.execute(
            """
            SELECT strategy, signal, confidence, reasoning
            FROM strategy_results WHERE decision_id = ? ORDER BY id
            """,
            (decision_id,),
        ).fetchall()
        return [
            {"strategy": r[0], "signal": r[1], "confidence": r[2], "reasoning": r[3]}
            for r in rows
        ]

    def save(self, decision: DecisionRecord) -> None:
        """Save (insert or update) a decision record.

        Args:
            decision: Decision to save.
        """
        symbol = decision.market_snapshot.symbol if decision.market_snapshot else None
        self._conn.execute(
            """
            INSERT INTO decisions (decision_id, timestamp, symbol, strategy, signal, outcome, data)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(decision_id) DO UPDATE SET
                timestamp=excluded.timestamp, symbol=excluded.symbol,
                strategy=excluded.strategy, signal=excluded.signal,
                outcome=excluded.outcome, data=excluded.data
            """,
            (
                decision.decision_id, decision.timestamp, symbol,
                decision.selected_strategy, decision.signal, decision.outcome_label,
                decision.to_json(),
            ),
        )
        self._conn.commit()

    def load(self, decision_id: str) -> DecisionRecord | None:
        """Load a decision by ID.

        Args:
            decision_id: Decision UUID.

        Returns:
            DecisionRecord or None if not found.
        """
        row = self._conn.execute(
            "SELECT data FROM decisions WHERE decision_id = ?", (decision_id,)
        ).fetchone()
        if row is None:
            return None
        return self._dict_to_record(json.loads(row[0]))

    def query(
        self,
        symbol: str | None = None,
        strategy: str | None = None,
        since: float | None = None,
        until: float | None = None,
        outcome: str | None = None,
        signal: str | None = None,
        limit: int = 100,
    ) -> list[DecisionRecord]:
        """Query decisions with filtering.

        Args:
            symbol: Filter by trading symbol.
            strategy: Filter by strategy name.
            since: Minimum timestamp.
            until: Maximum timestamp.
            outcome: Filter by outcome label.
            signal: Filter by recommendation (BUY/SELL/HOLD).
            limit: Maximum results.

        Returns:
            Matching decisions, newest first.
        """
        clauses: list[str] = []
        params: list[Any] = []
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        if strategy:
            clauses.append("strategy = ?")
            params.append(strategy)
        if since is not None:
            clauses.append("timestamp >= ?")
            params.append(since)
        if until is not None:
            clauses.append("timestamp <= ?")
            params.append(until)
        if outcome:
            clauses.append("outcome = ?")
            params.append(outcome)
        if signal:
            clauses.append("signal = ?")
            params.append(signal)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT data FROM decisions {where} ORDER BY timestamp DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [self._dict_to_record(json.loads(row[0])) for row in rows]

    def count(self) -> int:
        """Total decisions stored."""
        return self._conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]

    @staticmethod
    def _dict_to_record(data: dict[str, Any]) -> DecisionRecord:
        """Reconstruct DecisionRecord from dictionary."""
        record = DecisionRecord(
            decision_id=data.get("decision_id", ""),
            timestamp=data.get("timestamp", 0.0),
            phase=DecisionPhase[data.get("phase", "SIGNAL_GENERATED")],
            reasoning_summary=data.get("reasoning_summary", ""),
            confidence_score=data.get("confidence_score", 0.0),
            signal=data.get("signal"),
            risk_level=data.get("risk_level"),
            selected_strategy=data.get("selected_strategy", ""),
            strategy_parameters=data.get("strategy_parameters", {}),
            exit_price=data.get("exit_price"),
            exit_timestamp=data.get("exit_timestamp"),
            realized_pnl=data.get("realized_pnl"),
            holding_period_seconds=data.get("holding_period_seconds"),
            outcome_label=data.get("outcome_label"),
            tags=data.get("tags", {}),
            version=data.get("version", "1.0"),
        )
        # Deserialize nested structures if present
        if data.get("market_snapshot"):
            ms = data["market_snapshot"]
            record.market_snapshot = MarketSnapshot(
                symbol=ms["symbol"],
                timestamp=ms["timestamp"],
                price=ms["price"],
                bid=ms["bid"],
                ask=ms["ask"],
                volume_24h=ms.get("volume_24h"),
                volatility_annual=ms.get("volatility_annual"),
                market_regime=ms.get("market_regime"),
            )
        if data.get("feature_vector"):
            fv = data["feature_vector"]
            record.feature_vector = FeatureVector(
                features=fv.get("features", {}),
                feature_names=fv.get("feature_names", []),
                model_version=fv.get("model_version"),
            )
        if data.get("risk_assessment"):
            ra = data["risk_assessment"]
            record.risk_assessment = RiskAssessment(
                var_95=ra.get("var_95"),
                cvar_95=ra.get("cvar_95"),
                max_drawdown=ra.get("max_drawdown"),
                position_size_pct=ra.get("position_size_pct"),
                leverage=ra.get("leverage"),
                kill_switch_armed=ra.get("kill_switch_armed", False),
                passed_checks=ra.get("passed_checks", []),
                failed_checks=ra.get("failed_checks", []),
            )
        if data.get("portfolio_state"):
            ps = data["portfolio_state"]
            record.portfolio_state = PortfolioState(
                total_value=ps.get("total_value", 0.0),
                cash=ps.get("cash", 0.0),
                unrealized_pnl=ps.get("unrealized_pnl", 0.0),
                open_positions=ps.get("open_positions", {}),
                sector_exposure=ps.get("sector_exposure", {}),
            )
        if data.get("execution_result"):
            er = data["execution_result"]
            record.execution_result = DecisionExecutionResult(
                order_id=er["order_id"],
                filled_qty=er["filled_qty"],
                avg_price=er["avg_price"],
                slippage_bps=er["slippage_bps"],
                commission=er["commission"],
                execution_time_ms=er["execution_time_ms"],
                status=er["status"],
            )
        return record


def _iso(ts: float) -> str:
    """Format timestamp as ISO string."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
