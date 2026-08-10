from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd

from src.data.models import (
    CompanyFacts,
    CompanyNews,
    FinancialMetrics,
    InsiderTrade,
    Price,
)
from src.tools.api import (
    get_company_facts,
    get_company_news,
    get_financial_metrics,
    get_insider_trades,
    get_price_data,
    get_prices,
)


@runtime_checkable
class MarketDataProvider(Protocol):
    """Interface for quote and fundamental providers used by the backtester.

    Implementations can wrap yfinance, Financial Datasets, mock providers,
    or a future service facade. The engine depends on the protocol rather than
    the concrete functions in `src.tools.api`.
    """

    def get_prices(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        api_key: str | None = None,
    ) -> list[Price]: ...

    def get_price_data(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        api_key: str | None = None,
    ) -> pd.DataFrame: ...

    def get_financial_metrics(
        self,
        ticker: str,
        end_date: str,
        period: str = "ttm",
        limit: int = 10,
        api_key: str | None = None,
    ) -> list[FinancialMetrics]: ...

    def get_insider_trades(
        self,
        ticker: str,
        end_date: str,
        start_date: str | None = None,
        limit: int = 1000,
        api_key: str | None = None,
    ) -> list[InsiderTrade]: ...

    def get_company_news(
        self,
        ticker: str,
        end_date: str,
        start_date: str | None = None,
        limit: int = 1000,
        api_key: str | None = None,
    ) -> list[CompanyNews]: ...

    def get_company_facts(self, ticker: str) -> CompanyFacts | None: ...


class APIMarketDataProvider:
    """Concrete adapter that provides the current API-backed implementation."""

    def get_prices(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        api_key: str | None = None,
    ) -> list[Price]:
        return get_prices(ticker, start_date, end_date, api_key=api_key)

    def get_price_data(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        api_key: str | None = None,
    ) -> pd.DataFrame:
        return get_price_data(ticker, start_date, end_date, api_key=api_key)

    def get_financial_metrics(
        self,
        ticker: str,
        end_date: str,
        period: str = "ttm",
        limit: int = 10,
        api_key: str | None = None,
    ) -> list[FinancialMetrics]:
        return get_financial_metrics(ticker, end_date, period=period, limit=limit, api_key=api_key)

    def get_insider_trades(
        self,
        ticker: str,
        end_date: str,
        start_date: str | None = None,
        limit: int = 1000,
        api_key: str | None = None,
    ) -> list[InsiderTrade]:
        return get_insider_trades(ticker, end_date, start_date=start_date, limit=limit, api_key=api_key)

    def get_company_news(
        self,
        ticker: str,
        end_date: str,
        start_date: str | None = None,
        limit: int = 1000,
        api_key: str | None = None,
    ) -> list[CompanyNews]:
        return get_company_news(ticker, end_date, start_date=start_date, limit=limit, api_key=api_key)

    def get_company_facts(self, ticker: str) -> CompanyFacts | None:
        return get_company_facts(ticker)
