from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from .metrics import PerformanceMetricsCalculator
from .types import PortfolioValuePoint


@dataclass(frozen=True)
class AnalyticsSummary:
    """Small immutable result object for a strategy backtest.

    This mirrors the shape currently returned by the backtesting ecosystem and
    makes it easy for API/CLI layers to expose a stable summary payload.
    """

    total_return_pct: float
    sharpe_ratio: float | None
    sortino_ratio: float | None
    max_drawdown: float | None
    max_drawdown_date: str | None
    equity_curve_points: int


class BacktestAnalytics:
    """Pure analytics facade that reads an equity curve and returns a stable summary."""

    def __init__(self, *, annual_trading_days: int = 252, annual_rf_rate: float = 0.0434) -> None:
        self._calculator = PerformanceMetricsCalculator(
            annual_trading_days=annual_trading_days,
            annual_rf_rate=annual_rf_rate,
        )

    def summarize(self, values: Sequence[PortfolioValuePoint], initial_capital: float | None = None) -> AnalyticsSummary:
        """Build analytics from a series of portfolio value points."""
        if not values:
            return AnalyticsSummary(
                total_return_pct=0.0,
                sharpe_ratio=None,
                sortino_ratio=None,
                max_drawdown=None,
                max_drawdown_date=None,
                equity_curve_points=0,
            )

        first = values[0]
        last = values[-1]
        initial = initial_capital if initial_capital is not None else float(first["Portfolio Value"])

        total_return_pct = 0.0
        if initial and initial != 0:
            total_return_pct = ((float(last["Portfolio Value"]) / initial) - 1.0) * 100.0

        metrics = self._calculator.compute_metrics(values)
        return AnalyticsSummary(
            total_return_pct=float(total_return_pct),
            sharpe_ratio=metrics.get("sharpe_ratio"),
            sortino_ratio=metrics.get("sortino_ratio"),
            max_drawdown=metrics.get("max_drawdown"),
            max_drawdown_date=metrics.get("max_drawdown_date"),
            equity_curve_points=len(values),
        )

    def to_dict(self, summary: AnalyticsSummary) -> dict[str, Any]:
        return {
            "total_return_pct": summary.total_return_pct,
            "sharpe_ratio": summary.sharpe_ratio,
            "sortino_ratio": summary.sortino_ratio,
            "max_drawdown": summary.max_drawdown,
            "max_drawdown_date": summary.max_drawdown_date,
            "equity_curve_points": summary.equity_curve_points,
        }
