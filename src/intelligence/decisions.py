"""Continuous Learning & Decision Intelligence Framework.

Records every trading decision with full context for post-trade analysis,
continuous improvement, and external AI review.
"""

from __future__ import annotations

import json
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
    """Persistent store for decision records.

    Simple file-based storage with in-memory indexing.
    Production would use a time-series database.
    """

    def __init__(self, data_dir: str | Path = "./decisions"):
        """Initialize decision store.

        Args:
            data_dir: Directory for decision storage.
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, Path] = {}
        self._load_index()

    def save(self, decision: DecisionRecord) -> Path:
        """Save a decision record.

        Args:
            decision: Decision to save.

        Returns:
            Path to saved file.
        """
        date_prefix = datetime.fromtimestamp(decision.timestamp, tz=timezone.utc).strftime("%Y%m%d")
        filename = f"{date_prefix}_{decision.decision_id}.json"
        path = self.data_dir / filename
        path.write_text(decision.to_json(indent=2), encoding="utf-8")
        self._index[decision.decision_id] = path
        return path

    def load(self, decision_id: str) -> DecisionRecord | None:
        """Load a decision by ID.

        Args:
            decision_id: Decision UUID.

        Returns:
            DecisionRecord or None if not found.
        """
        path = self._index.get(decision_id)
        if not path or not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return self._dict_to_record(data)

    def query(
        self,
        symbol: str | None = None,
        strategy: str | None = None,
        since: float | None = None,
        until: float | None = None,
        outcome: str | None = None,
        limit: int = 100,
    ) -> list[DecisionRecord]:
        """Query decisions with filtering.

        Args:
            symbol: Filter by trading symbol.
            strategy: Filter by strategy name.
            since: Minimum timestamp.
            until: Maximum timestamp.
            outcome: Filter by outcome label.
            limit: Maximum results.

        Returns:
            Matching decisions, newest first.
        """
        results: list[DecisionRecord] = []
        for path in sorted(self.data_dir.glob("*.json"), reverse=True):
            if len(results) >= limit:
                break
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if symbol and data.get("market_snapshot", {}).get("symbol") != symbol:
                    continue
                if strategy and data.get("selected_strategy") != strategy:
                    continue
                if since and data.get("timestamp", 0) < since:
                    continue
                if until and data.get("timestamp", float("inf")) > until:
                    continue
                if outcome and data.get("outcome_label") != outcome:
                    continue
                results.append(self._dict_to_record(data))
            except (OSError, json.JSONDecodeError):
                continue
        return results

    def count(self) -> int:
        """Total decisions stored."""
        return len(list(self.data_dir.glob("*.json")))

    def _load_index(self) -> None:
        """Build index of decision IDs to file paths."""
        for path in self.data_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._index[data["decision_id"]] = path
            except (OSError, json.JSONDecodeError, KeyError):
                continue

    @staticmethod
    def _dict_to_record(data: dict[str, Any]) -> DecisionRecord:
        """Reconstruct DecisionRecord from dictionary."""
        record = DecisionRecord(
            decision_id=data.get("decision_id", ""),
            timestamp=data.get("timestamp", 0.0),
            phase=DecisionPhase[data.get("phase", "SIGNAL_GENERATED")],
            reasoning_summary=data.get("reasoning_summary", ""),
            confidence_score=data.get("confidence_score", 0.0),
            selected_strategy=data.get("selected_strategy", ""),
            strategy_parameters=data.get("strategy_parameters", {}),
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
