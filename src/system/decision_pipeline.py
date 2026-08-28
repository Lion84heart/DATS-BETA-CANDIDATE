"""Decision recording pipeline for live trading.

Integrates decision intelligence (CAP-009) with the trading loop
to record every trading decision with full context, features,
and outcomes for external AI review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from intelligence.decisions import (
    DecisionExecutionResult,
    DecisionPackage,
    DecisionPhase,
    DecisionRecord,
    DecisionStore,
    FeatureVector,
    MarketSnapshot,
    PortfolioState,
    RiskAssessment,
)
from intelligence.evaluation import PostTradeEvaluator
from observability.metrics import MetricsCollector


@dataclass
class PipelineContext:
    """Context passed through the decision pipeline."""

    symbol: str
    price: float
    timestamp: float
    features: dict[str, Any] = field(default_factory=dict)
    strategy_name: str = ""
    risk_approved: bool = False
    position_size: float = 0.0
    execution_result: DecisionExecutionResult | None = None
    portfolio_state: PortfolioState | None = None


class DecisionPipeline:
    """Records complete trading decisions for review and analysis.

    Captures decision context, market state, features, reasoning,
    strategy selection, risk evaluation, portfolio state, execution
    outcome, and post-trade evaluation. Exports structured
    DecisionReviewPackages for external AI analysis.

    All decisions are recorded with REVIEW_REQUIRED status and
    must be manually reviewed before any action is taken based
    on the analysis. Advisory only — never modifies production.
    """

    def __init__(
        self,
        store: DecisionStore,
        metrics: MetricsCollector | None = None,
    ):
        self.store = store
        self.metrics = metrics or MetricsCollector()
        self.evaluator = PostTradeEvaluator()
        self._review_status: dict[str, str] = {}

    def record_decision(
        self,
        context: PipelineContext,
        reasoning: str = "",
        confidence: float = 0.0,
    ) -> DecisionRecord:
        """Record a complete trading decision.

        Args:
            context: Pipeline context with all decision data.
            reasoning: Human-readable or AI-generated reasoning.
            confidence: Confidence score [0, 1].

        Returns:
            The recorded DecisionRecord.
        """
        self.metrics.increment("decisions.recorded", 1.0)

        record = DecisionRecord(
            decision_id=f"{context.symbol}-{int(context.timestamp * 1000)}",
            timestamp=context.timestamp,
            phase=DecisionPhase.SIGNAL_GENERATED,
            market_snapshot=MarketSnapshot(
                symbol=context.symbol,
                price=context.price,
                bid=context.price * 0.999,
                ask=context.price * 1.001,
                timestamp=context.timestamp,
            ),
            feature_vector=FeatureVector(
                features={k: float(v) for k, v in context.features.items()},
                feature_names=list(context.features.keys()),
            ),
            reasoning_summary=reasoning,
            confidence_score=confidence,
            selected_strategy=context.strategy_name,
            risk_assessment=RiskAssessment(
                passed_checks=["pipeline_default"],
                failed_checks=[],
            ),
            portfolio_state=context.portfolio_state
            or PortfolioState(
                total_value=0.0,
                cash=0.0,
                unrealized_pnl=0.0,
                open_positions={},
            ),
            execution_result=context.execution_result,
        )

        self.store.save(record)
        self._review_status[record.decision_id] = "REVIEW_REQUIRED"

        return record

    def update_execution(
        self,
        decision_id: str,
        execution_result: DecisionExecutionResult,
    ) -> DecisionRecord | None:
        """Update a decision with execution outcome.

        Args:
            decision_id: Decision to update.
            execution_result: Execution outcome.

        Returns:
            Updated record or None if not found.
        """
        record = self.store.load(decision_id)
        if record is None:
            self.metrics.increment("decisions.update_not_found", 1.0)
            return None

        record.execution_result = execution_result
        record.phase = DecisionPhase.ORDER_FILLED
        self.store.save(record)
        self.metrics.increment("decisions.executed", 1.0)

        return record

    def evaluate_outcome(
        self,
        decision_id: str,
        exit_price: float | None = None,
    ) -> DecisionRecord | None:
        """Evaluate post-trade outcome of a decision.

        Args:
            decision_id: Decision to evaluate.
            exit_price: Exit price for PnL calculation.

        Returns:
            Updated record or None if not found.
        """
        record = self.store.load(decision_id)
        if record is None:
            return None

        if record.execution_result and exit_price is not None:
            # Calculate realized PnL
            entry = record.execution_result.avg_price
            qty = record.execution_result.filled_qty
            if entry and qty:
                # qty > 0 means long, qty < 0 means short
                pnl = (exit_price - entry) * qty
                record.realized_pnl = pnl

                # Evaluate and label
                outcome = self.evaluator.label_outcome(pnl)
                record.outcome_label = outcome.value
                record.phase = DecisionPhase.POST_TRADE

        self.store.save(record)
        self.metrics.increment("decisions.evaluated", 1.0)
        return record

    def mark_reviewed(
        self,
        decision_id: str,
        reviewer: str = "system",
        notes: str = "",
    ) -> None:
        """Mark a decision as reviewed.

        Args:
            decision_id: Decision to mark.
            reviewer: Who reviewed the decision.
            notes: Review notes.
        """
        self._review_status[decision_id] = f"REVIEWED_BY:{reviewer}"
        if notes:
            self._review_status[decision_id] += f"|NOTES:{notes}"
        self.metrics.increment("decisions.reviewed", 1.0)

    def get_review_status(self, decision_id: str) -> str:
        """Get review status of a decision."""
        return self._review_status.get(decision_id, "UNKNOWN")

    def export_review_package(self, decision_id: str) -> DecisionPackage | None:
        """Export a decision as a review package for external AI analysis.

        Advisory only. The exported package must be reviewed by a
        human analyst before any production changes are made.

        Args:
            decision_id: Decision to export.

        Returns:
            DecisionPackage or None if not found.
        """
        record = self.store.load(decision_id)
        if record is None:
            return None

        package = DecisionPackage(description=f"Review package for {decision_id}")
        package.add(record)
        self.metrics.increment("decisions.packages_exported", 1.0)
        return package

    def export_all_pending_reviews(self) -> list[DecisionPackage]:
        """Export all decisions requiring review.

        Returns:
            List of DecisionPackage for review.
        """
        packages: list[DecisionPackage] = []
        for decision_id, status in self._review_status.items():
            if status == "REVIEW_REQUIRED":
                record = self.store.load(decision_id)
                if record:
                    packages.append(DecisionPackage(record))
        self.metrics.increment("decisions.pending_reviews_exported", float(len(packages)))
        return packages

    def get_summary(self) -> dict[str, Any]:
        """Summary of decision pipeline state."""
        return {
            "total_decisions_recorded": len(self._review_status),
            "pending_reviews": sum(
                1 for s in self._review_status.values() if s == "REVIEW_REQUIRED"
            ),
            "reviewed": sum(
                1 for s in self._review_status.values() if s.startswith("REVIEWED_BY")
            ),
        }
