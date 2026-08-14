"""Backtesting package: interfaces and shared types for refactoring.

This module exposes the stable public surface for the backtesting subsystem
without triggering the heavy runtime stack during tests that only import a
portfolio or analytics primitive.
"""

from typing import Any

from .types import (
    ActionLiteral,
    AgentDecision,
    AgentDecisions,
    AgentOutput,
    AgentSignals,
    PerformanceMetrics,
    PortfolioSnapshot,
    PortfolioValuePoint,
    PositionState,
    PriceDataFrame,
    TickerRealizedGains,
)

from .portfolio import Portfolio
from .trader import TradeExecutor
from .metrics import PerformanceMetricsCalculator
from .valuation import calculate_portfolio_value, compute_exposures
from .analytics import AnalyticsSummary, BacktestAnalytics

__all__ = [
    # Types
    "ActionLiteral",
    "AgentDecision",
    "AgentDecisions",
    "AgentOutput",
    "AgentSignals",
    "PerformanceMetrics",
    "PortfolioSnapshot",
    "PortfolioValuePoint",
    "PositionState",
    "PriceDataFrame",
    "TickerRealizedGains",
    # Interfaces
    "Portfolio",
    "TradeExecutor",
    "PerformanceMetricsCalculator",
    "AgentController",
    "BacktestEngine",
    "calculate_portfolio_value",
    "compute_exposures",
    "OutputBuilder",
    "AnalyticsSummary",
    "BacktestAnalytics",
]


def __getattr__(name: str) -> Any:
    """Resolve public backtesting names lazily.

    This avoids importing the agent/LLM runtime whenever a simple backtesting
    primitive is imported for unit-level validation.
    """
    if name == "AgentController":
        from .controller import AgentController

        return AgentController
    if name == "BacktestEngine":
        from .engine import BacktestEngine

        return BacktestEngine
    if name == "OutputBuilder":
        from .output import OutputBuilder

        return OutputBuilder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


