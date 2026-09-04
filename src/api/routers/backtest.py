"""Backtesting & Evaluation API router.

Runs the existing Strategy Engine + Decision Fusion + PaperBroker fill
logic against replayed historical OHLCV data (see backtesting/). Fully
isolated from live trading: every run uses a fresh, in-memory PaperBroker
instance that is discarded when the run completes — it never touches the
registry's shared live broker, the live feed, or /orders.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from api.auth import UserRole, get_current_user, has_permission
from api.dependencies import get_component
from backtesting.data import generate_synthetic_ohlcv, parse_csv_ohlcv
from backtesting.engine import BacktestEngine, BacktestRunConfig
from backtesting.report import dict_to_csv, report_to_dict
from intelligence.decisions import DecisionStore

router = APIRouter(prefix="/backtest", tags=["backtest"])

_MAX_BARS = 5000


class BacktestRunRequest(BaseModel):
    """Request to run a backtest."""

    symbol: str = "AAPL"
    data_source: str = Field("synthetic", pattern="^(synthetic|csv)$")
    num_bars: int = Field(500, ge=50, le=_MAX_BARS)
    seed: int | None = None
    csv_data: str | None = None
    initial_capital: float = Field(100000.0, gt=0)
    position_size_pct: float = Field(0.95, gt=0, le=1.0)
    confusion_horizon_bars: int = Field(5, ge=1, le=100)
    confusion_threshold_pct: float = Field(0.1, ge=0.0)


@router.post("/run")
async def run_backtest(req: BacktestRunRequest, request: Request) -> dict:
    """Run a backtest and persist the report. Operator+."""
    current_user = get_current_user(request)
    if not has_permission(current_user, UserRole.OPERATOR):
        raise HTTPException(status_code=403, detail="Operator access required")

    symbol = req.symbol.upper()

    try:
        if req.data_source == "csv":
            if not req.csv_data:
                raise HTTPException(status_code=400, detail="csv_data is required when data_source='csv'")
            bars = parse_csv_ohlcv(req.csv_data)
            if len(bars) > _MAX_BARS:
                raise HTTPException(status_code=400, detail=f"CSV has {len(bars)} bars; the limit is {_MAX_BARS}")
        else:
            bars = generate_synthetic_ohlcv(symbol, req.num_bars, seed=req.seed)

        if len(bars) < 50:
            raise HTTPException(status_code=400, detail=f"Need at least 50 bars to backtest; got {len(bars)}")

        config = BacktestRunConfig(
            symbol=symbol,
            initial_capital=req.initial_capital,
            position_size_pct=req.position_size_pct,
            confusion_horizon_bars=req.confusion_horizon_bars,
            confusion_threshold_pct=req.confusion_threshold_pct,
        )
        engine = BacktestEngine()
        report = await engine.run(bars, config)
        report_dict = report_to_dict(report)

        store: DecisionStore = get_component(request, "decision_store")
        store.save_backtest_run(report_dict)

        return report_dict
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs")
async def list_runs(request: Request, limit: int = 50) -> dict:
    """List past backtest runs, newest first. Viewer+."""
    get_current_user(request)
    try:
        store: DecisionStore = get_component(request, "decision_store")
        runs = store.list_backtest_runs(limit=limit)
        return {"count": len(runs), "runs": runs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request) -> dict:
    """Get the full report for one backtest run. Viewer+."""
    get_current_user(request)
    try:
        store: DecisionStore = get_component(request, "decision_store")
        report_dict = store.get_backtest_run(run_id)
        if report_dict is None:
            raise HTTPException(status_code=404, detail="Backtest run not found")
        return report_dict
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/export.json")
async def export_run_json(run_id: str, request: Request) -> dict:
    """Export one run's full report as JSON. Viewer+."""
    return await get_run(run_id, request)


@router.get("/runs/{run_id}/export.csv", response_class=PlainTextResponse)
async def export_run_csv(run_id: str, request: Request) -> str:
    """Export one run's report as a multi-section CSV. Viewer+."""
    get_current_user(request)
    try:
        store: DecisionStore = get_component(request, "decision_store")
        report_dict = store.get_backtest_run(run_id)
        if report_dict is None:
            raise HTTPException(status_code=404, detail="Backtest run not found")
        return dict_to_csv(report_dict)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
