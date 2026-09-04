"""Decision review API router."""

from __future__ import annotations


from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api.auth import UserRole, get_current_user, get_user_from_token, has_permission, record_audit
from api.dependencies import get_component
from intelligence.decisions import DecisionStore
from system.decision_pipeline import DecisionPipeline

router = APIRouter(prefix="/decisions", tags=["decisions"])


class ReviewRequest(BaseModel):
    """Request to mark a decision as reviewed."""

    reviewer: str = "analyst"
    notes: str = ""


@router.get("/")
async def list_decisions(
    request: Request,
    symbol: str | None = None,
    signal: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List decisions with optional filtering. Viewer+."""
    get_current_user(request)  # Any authenticated user
    try:
        store: DecisionStore = get_component(request, "decision_store")
        records = store.query(symbol=symbol, signal=signal, limit=limit)
        return {
            "count": len(records),
            "offset": offset,
            "limit": limit,
            "records": [
                {
                    "decision_id": r.decision_id,
                    "timestamp": r.timestamp,
                    "phase": r.phase.value if hasattr(r.phase, "value") else str(r.phase),
                    "symbol": r.market_snapshot.symbol if r.market_snapshot else None,
                    "price": r.market_snapshot.price if r.market_snapshot else None,
                    "strategy": r.selected_strategy,
                    "confidence": r.confidence_score,
                    "signal": r.signal,
                    "risk_level": r.risk_level,
                    "outcome": r.outcome_label,
                    "realized_pnl": r.realized_pnl,
                    "reasoning_summary": r.reasoning_summary,
                    "risk_failed_checks": r.risk_assessment.failed_checks if r.risk_assessment else [],
                    "risk_passed_checks": r.risk_assessment.passed_checks if r.risk_assessment else [],
                }
                for r in records[offset:offset + limit]
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary/pipeline")
async def get_pipeline_summary(request: Request) -> dict:
    """Get decision pipeline summary. Viewer+."""
    get_current_user(request)  # Any authenticated user
    try:
        pipeline: DecisionPipeline | None = getattr(request.app.state, "pipeline", None)
        if pipeline is None:
            # Try to create from registry
            try:
                store = get_component(request, "decision_store")
                pipeline = DecisionPipeline(store=store)
            except Exception:
                return {"total_decisions_recorded": 0, "pending_reviews": 0, "reviewed": 0}
        return pipeline.get_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/csv")
async def export_decisions_csv(request: Request) -> dict:
    """Export decisions as CSV. Analyst+."""
    current_user = get_current_user(request)
    if not has_permission(current_user, UserRole.ANALYST):
        raise HTTPException(status_code=403, detail="Analyst access required")
    try:
        store: DecisionStore = get_component(request, "decision_store")
        records = store.query(limit=10000)
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "decision_id", "timestamp", "symbol", "price", "strategy",
            "confidence", "signal", "pnl", "status", "reviewed"
        ])
        for r in records:
            signal = "HOLD"
            if r.execution_result and r.execution_result.filled_qty > 0:
                signal = "BUY" if r.execution_result.filled_qty > 0 else "SELL"
            elif r.confidence_score > 0.5:
                signal = "BUY"
            elif r.confidence_score < 0.5 and r.confidence_score > 0:
                signal = "SELL"
            writer.writerow([
                r.decision_id,
                r.timestamp,
                r.market_snapshot.symbol if r.market_snapshot else "",
                r.market_snapshot.price if r.market_snapshot else "",
                r.selected_strategy or "",
                r.confidence_score,
                signal,
                r.realized_pnl or 0,
                r.phase.value if hasattr(r.phase, "value") else str(r.phase),
                "Yes" if r.outcome_label else "No",
            ])
        return {
            "format": "csv",
            "count": len(records),
            "csv_data": output.getvalue(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{decision_id}")
async def get_decision(decision_id: str, request: Request) -> dict:
    """Get a specific decision by ID. Viewer+."""
    get_current_user(request)  # Any authenticated user
    try:
        store: DecisionStore = get_component(request, "decision_store")
        record = store.load(decision_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Decision not found")
        return {
            "decision_id": record.decision_id,
            "timestamp": record.timestamp,
            "phase": record.phase.value if hasattr(record.phase, "value") else str(record.phase),
            "market_snapshot": record.market_snapshot.__dict__ if record.market_snapshot else None,
            "feature_vector": record.feature_vector.__dict__ if record.feature_vector else None,
            "reasoning_summary": record.reasoning_summary,
            "confidence_score": record.confidence_score,
            "signal": record.signal,
            "risk_level": record.risk_level,
            "selected_strategy": record.selected_strategy,
            "risk_assessment": record.risk_assessment.__dict__ if record.risk_assessment else None,
            "portfolio_state": record.portfolio_state.__dict__ if record.portfolio_state else None,
            "execution_result": record.execution_result.__dict__ if record.execution_result else None,
            "realized_pnl": record.realized_pnl,
            "outcome_label": record.outcome_label,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{decision_id}/strategies")
async def get_decision_strategies(decision_id: str, request: Request) -> dict:
    """Get every individual Strategy Engine result behind a fused decision.

    Viewer+. Each entry is one strategy's independent BUY/SELL/HOLD
    signal, confidence, and reasoning — the raw votes DecisionFusion
    combined into the final decision.
    """
    get_current_user(request)  # Any authenticated user
    try:
        store: DecisionStore = get_component(request, "decision_store")
        results = store.get_strategy_results(decision_id)
        return {"decision_id": decision_id, "count": len(results), "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{decision_id}/review")
async def review_decision(
    decision_id: str,
    review: ReviewRequest,
    request: Request,
) -> dict:
    """Mark a decision as reviewed. Analyst+."""
    current_user = get_current_user(request)
    if not has_permission(current_user, UserRole.ANALYST):
        raise HTTPException(status_code=403, detail="Analyst access required")
    try:
        pipeline: DecisionPipeline = request.app.state.pipeline
        if pipeline is None:
            raise HTTPException(status_code=503, detail="Decision pipeline not available")
        pipeline.mark_reviewed(decision_id, reviewer=review.reviewer, notes=review.notes)

        # Audit log
        auth_header = request.headers.get("authorization", "")
        user = None
        if auth_header.startswith("Bearer "):
            user = get_user_from_token(auth_header[7:])
        record_audit(user, "DECISION_REVIEW", "decisions", f"decision_id={decision_id}, reviewer={review.reviewer}")

        return {
            "decision_id": decision_id,
            "status": "reviewed",
            "reviewer": review.reviewer,
            "notes": review.notes,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{decision_id}/export")
async def export_decision(decision_id: str, request: Request) -> dict:
    """Export a decision as a review package. Analyst+."""
    current_user = get_current_user(request)
    if not has_permission(current_user, UserRole.ANALYST):
        raise HTTPException(status_code=403, detail="Analyst access required")
    try:
        pipeline: DecisionPipeline = request.app.state.pipeline
        if pipeline is None:
            raise HTTPException(status_code=503, detail="Decision pipeline not available")
        package = pipeline.export_review_package(decision_id)
        if package is None:
            raise HTTPException(status_code=404, detail="Decision not found")
        return {
            "decision_id": decision_id,
            "package": package.to_dict(),
            "review_status": pipeline.get_review_status(decision_id),
            "advisory_only": True,
            "requires_human_approval": True,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
