import logging
import math
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from src.data.cache import get_cache
from src.data.models import (
    CompanyFacts,
    CompanyFactsResponse,
    CompanyNews,
    CompanyNewsResponse,
    FinancialMetrics,
    FinancialMetricsResponse,
    InsiderTrade,
    InsiderTradeResponse,
    LineItem,
    LineItemResponse,
    Price,
    PriceResponse,
)

logger = logging.getLogger(__name__)

_cache = get_cache()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val) -> float | None:
    try:
        f = float(val)
        return None if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return None


def _ticker(symbol: str) -> yf.Ticker:
    return yf.Ticker(symbol)


def _get_stmt_value(stmt: pd.DataFrame, *row_names: str, col_idx: int = 0) -> float | None:
    """Extract a value from a yfinance financial statement DataFrame."""
    if stmt is None or stmt.empty:
        return None
    for name in row_names:
        if name in stmt.index:
            try:
                val = stmt.iloc[:, col_idx].get(name)
                return _safe_float(val)
            except Exception:
                continue
    return None


def _period_label(date: datetime, period: str) -> str:
    if period == "ttm":
        return "ttm"
    if period == "annual":
        return date.strftime("%Y-%m-%d")
    if period == "quarterly":
        q = (date.month - 1) // 3 + 1
        return f"{date.year}-Q{q}"
    return date.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------

def get_prices(ticker: str, start_date: str, end_date: str, api_key: str = None) -> list[Price]:
    cache_key = f"{ticker}_{start_date}_{end_date}"
    if cached := _cache.get_prices(cache_key):
        return [Price(**p) for p in cached]

    try:
        df = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=True)
    except Exception as e:
        logger.warning("yfinance download failed for %s: %s", ticker, e)
        return []

    if df.empty:
        return []

    # yfinance may return MultiIndex columns when downloading a single ticker
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    prices = []
    for ts, row in df.iterrows():
        prices.append(Price(
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            volume=int(row["Volume"]),
            time=ts.strftime("%Y-%m-%dT00:00:00"),
        ))

    _cache.set_prices(cache_key, [p.model_dump() for p in prices])
    return prices


def prices_to_df(prices: list[Price]) -> pd.DataFrame:
    df = pd.DataFrame([p.model_dump() for p in prices])
    df["Date"] = pd.to_datetime(df["time"])
    df.set_index("Date", inplace=True)
    for col in ["open", "close", "high", "low", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.sort_index(inplace=True)
    return df


def get_price_data(ticker: str, start_date: str, end_date: str, api_key: str = None) -> pd.DataFrame:
    return prices_to_df(get_prices(ticker, start_date, end_date))


# ---------------------------------------------------------------------------
# Financial Metrics
# ---------------------------------------------------------------------------

def get_financial_metrics(
    ticker: str,
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
    api_key: str = None,
) -> list[FinancialMetrics]:
    cache_key = f"{ticker}_{period}_{end_date}_{limit}"
    if cached := _cache.get_financial_metrics(cache_key):
        return [FinancialMetrics(**m) for m in cached]

    try:
        t = _ticker(ticker)
        info = t.info or {}
        fin = t.financials          # annual income statement
        bs = t.balance_sheet        # annual balance sheet
        cf = t.cashflow             # annual cash flow
        qfin = t.quarterly_financials
        qbs = t.quarterly_balance_sheet
        qcf = t.quarterly_cashflow
    except Exception as e:
        logger.warning("yfinance fetch failed for %s: %s", ticker, e)
        return []

    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    results: list[FinancialMetrics] = []

    if period == "ttm":
        # Use info-level ratios (already TTM) + LTM income/CF from quarterly stmts
        rev = _get_stmt_value(qfin, "Total Revenue", col_idx=0)
        ni = _get_stmt_value(qfin, "Net Income", "Net Income Common Stockholders", col_idx=0)
        op_inc = _get_stmt_value(qfin, "Operating Income", col_idx=0)
        ebit = _get_stmt_value(qfin, "EBIT", col_idx=0)
        ebitda = _get_stmt_value(qfin, "EBITDA", "Normalized EBITDA", col_idx=0)
        gross_p = _get_stmt_value(qfin, "Gross Profit", col_idx=0)
        da = _get_stmt_value(qcf, "Reconciled Depreciation", "Depreciation And Amortization", col_idx=0)
        fcf = _get_stmt_value(qcf, "Free Cash Flow", col_idx=0)
        capex = _get_stmt_value(qcf, "Capital Expenditure", col_idx=0)
        total_debt = _get_stmt_value(qbs, "Total Debt", col_idx=0)
        eq = _get_stmt_value(qbs, "Stockholders Equity", "Common Stock Equity", col_idx=0)
        tot_assets = _get_stmt_value(qbs, "Total Assets", col_idx=0)
        cur_assets = _get_stmt_value(qbs, "Current Assets", col_idx=0)
        cur_liab = _get_stmt_value(qbs, "Current Liabilities", col_idx=0)
        shares = _safe_float(info.get("sharesOutstanding"))
        mkt_cap = _safe_float(info.get("marketCap"))
        ev = _safe_float(info.get("enterpriseValue"))
        eps = _safe_float(info.get("trailingEps"))
        bvps = _safe_float(info.get("bookValue"))

        gross_margin = _safe_float(info.get("grossMargins"))
        op_margin = _safe_float(info.get("operatingMargins"))
        net_margin = _safe_float(info.get("profitMargins"))
        roe = _safe_float(info.get("returnOnEquity"))
        roa = _safe_float(info.get("returnOnAssets"))
        current_ratio = _safe_float(info.get("currentRatio"))
        quick_ratio = _safe_float(info.get("quickRatio"))
        d2e = _safe_float(info.get("debtToEquity"))
        if d2e is not None:
            d2e = d2e / 100  # yfinance reports as percentage points
        rev_growth = _safe_float(info.get("revenueGrowth"))
        earn_growth = _safe_float(info.get("earningsGrowth"))
        pe = _safe_float(info.get("trailingPE"))
        pb = _safe_float(info.get("priceToBook"))
        ps = _safe_float(info.get("priceToSalesTrailing12Months"))
        ev_ebitda = _safe_float(info.get("enterpriseToEbitda"))
        ev_rev = _safe_float(info.get("enterpriseToRevenue"))
        peg = _safe_float(info.get("pegRatio"))
        payout = _safe_float(info.get("payoutRatio"))

        interest_exp = _get_stmt_value(qfin, "Interest Expense", col_idx=0)
        interest_cov = None
        if ebit is not None and interest_exp is not None and interest_exp != 0:
            interest_cov = ebit / abs(interest_exp)

        d2a = None
        if total_debt is not None and tot_assets is not None and tot_assets != 0:
            d2a = total_debt / tot_assets

        roic = None
        if ni is not None and total_debt is not None and eq is not None:
            invested_cap = (total_debt or 0) + (eq or 0)
            if invested_cap != 0:
                roic = ni / invested_cap

        asset_turn = None
        if rev is not None and tot_assets is not None and tot_assets != 0:
            asset_turn = rev / tot_assets

        inv_turn = None
        recv_turn = None
        dso = None
        op_cycle = None
        wc_turn = None
        if cur_assets is not None and cur_liab is not None:
            wc = cur_assets - cur_liab
            if wc != 0 and rev is not None:
                wc_turn = rev / wc

        cash_ratio = None
        cash = _safe_float(info.get("totalCash"))
        if cash is not None and cur_liab is not None and cur_liab != 0:
            cash_ratio = cash / cur_liab

        op_cf = _get_stmt_value(qcf, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities", col_idx=0)
        op_cf_ratio = None
        if op_cf is not None and cur_liab is not None and cur_liab != 0:
            op_cf_ratio = op_cf / cur_liab

        fcf_ps = None
        if fcf is not None and shares is not None and shares != 0:
            fcf_ps = fcf / shares

        fcf_yield = None
        if fcf is not None and mkt_cap is not None and mkt_cap != 0:
            fcf_yield = fcf / mkt_cap

        m = FinancialMetrics(
            ticker=ticker,
            report_period=end_date,
            period="ttm",
            currency="USD",
            market_cap=mkt_cap,
            enterprise_value=ev,
            price_to_earnings_ratio=pe,
            price_to_book_ratio=pb,
            price_to_sales_ratio=ps,
            enterprise_value_to_ebitda_ratio=ev_ebitda,
            enterprise_value_to_revenue_ratio=ev_rev,
            free_cash_flow_yield=fcf_yield,
            peg_ratio=peg,
            gross_margin=gross_margin,
            operating_margin=op_margin,
            net_margin=net_margin,
            return_on_equity=roe,
            return_on_assets=roa,
            return_on_invested_capital=roic,
            asset_turnover=asset_turn,
            inventory_turnover=inv_turn,
            receivables_turnover=recv_turn,
            days_sales_outstanding=dso,
            operating_cycle=op_cycle,
            working_capital_turnover=wc_turn,
            current_ratio=current_ratio,
            quick_ratio=quick_ratio,
            cash_ratio=cash_ratio,
            operating_cash_flow_ratio=op_cf_ratio,
            debt_to_equity=d2e,
            debt_to_assets=d2a,
            interest_coverage=interest_cov,
            revenue_growth=rev_growth,
            earnings_growth=earn_growth,
            book_value_growth=None,
            earnings_per_share_growth=None,
            free_cash_flow_growth=None,
            operating_income_growth=None,
            ebitda_growth=None,
            payout_ratio=payout,
            earnings_per_share=eps,
            book_value_per_share=bvps,
            free_cash_flow_per_share=fcf_ps,
        )
        results = [m]

    else:
        # Annual or quarterly: iterate statement columns (each col = one period)
        stmt = fin if period == "annual" else qfin
        bss = bs if period == "annual" else qbs
        cfs = cf if period == "annual" else qcf

        if stmt is None or stmt.empty:
            return []

        cols = [c for c in stmt.columns if pd.Timestamp(c) <= pd.Timestamp(end_date)]
        cols = sorted(cols, reverse=True)[:limit]

        mkt_cap = _safe_float((t.info or {}).get("marketCap"))

        for i, col in enumerate(cols):
            col_dt = pd.Timestamp(col).to_pydatetime()
            rev = _get_stmt_value(stmt, "Total Revenue", col_idx=i)
            ni = _get_stmt_value(stmt, "Net Income", "Net Income Common Stockholders", col_idx=i)
            op_inc = _get_stmt_value(stmt, "Operating Income", col_idx=i)
            ebit = _get_stmt_value(stmt, "EBIT", col_idx=i)
            gross_p = _get_stmt_value(stmt, "Gross Profit", col_idx=i)
            interest_exp = _get_stmt_value(stmt, "Interest Expense", col_idx=i)
            eps = _get_stmt_value(stmt, "Diluted EPS", "Basic EPS", col_idx=i)

            total_assets = _get_stmt_value(bss, "Total Assets", col_idx=i)
            total_debt = _get_stmt_value(bss, "Total Debt", col_idx=i)
            eq = _get_stmt_value(bss, "Stockholders Equity", "Common Stock Equity", col_idx=i)
            cur_assets = _get_stmt_value(bss, "Current Assets", col_idx=i)
            cur_liab = _get_stmt_value(bss, "Current Liabilities", col_idx=i)
            cash = _get_stmt_value(bss, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments", col_idx=i)
            bvps = None
            shares = _safe_float((t.info or {}).get("sharesOutstanding"))
            if eq is not None and shares is not None and shares != 0:
                bvps = eq / shares

            fcf = _get_stmt_value(cfs, "Free Cash Flow", col_idx=i)
            capex = _get_stmt_value(cfs, "Capital Expenditure", col_idx=i)
            da = _get_stmt_value(cfs, "Reconciled Depreciation", "Depreciation And Amortization", col_idx=i)
            op_cf = _get_stmt_value(cfs, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities", col_idx=i)

            gross_margin = (gross_p / rev) if gross_p is not None and rev else None
            op_margin = (op_inc / rev) if op_inc is not None and rev else None
            net_margin = (ni / rev) if ni is not None and rev else None
            roe = (ni / eq) if ni is not None and eq else None
            roa = (ni / total_assets) if ni is not None and total_assets else None
            d2e_val = (total_debt / eq) if total_debt is not None and eq and eq != 0 else None
            d2a = (total_debt / total_assets) if total_debt is not None and total_assets and total_assets != 0 else None
            int_cov = None
            if ebit is not None and interest_exp is not None and interest_exp != 0:
                int_cov = ebit / abs(interest_exp)
            roic = None
            if ni is not None and total_debt is not None and eq is not None:
                ic = (total_debt or 0) + (eq or 0)
                roic = ni / ic if ic != 0 else None
            asset_turn = (rev / total_assets) if rev is not None and total_assets else None
            current_ratio = (cur_assets / cur_liab) if cur_assets is not None and cur_liab and cur_liab != 0 else None
            cash_ratio = (cash / cur_liab) if cash is not None and cur_liab and cur_liab != 0 else None
            op_cf_ratio = (op_cf / cur_liab) if op_cf is not None and cur_liab and cur_liab != 0 else None
            wc_turn = None
            if cur_assets is not None and cur_liab is not None:
                wc = cur_assets - cur_liab
                if wc != 0 and rev is not None:
                    wc_turn = rev / wc
            fcf_yield = (fcf / mkt_cap) if fcf is not None and mkt_cap else None
            fcf_ps = (fcf / shares) if fcf is not None and shares and shares != 0 else None

            rev_growth = None
            earn_growth = None
            if i + 1 < len(cols):
                prev_rev = _get_stmt_value(stmt, "Total Revenue", col_idx=i + 1)
                prev_ni = _get_stmt_value(stmt, "Net Income", "Net Income Common Stockholders", col_idx=i + 1)
                if rev is not None and prev_rev and prev_rev != 0:
                    rev_growth = (rev - prev_rev) / abs(prev_rev)
                if ni is not None and prev_ni and prev_ni != 0:
                    earn_growth = (ni - prev_ni) / abs(prev_ni)

            m = FinancialMetrics(
                ticker=ticker,
                report_period=col_dt.strftime("%Y-%m-%d"),
                period=period,
                currency="USD",
                market_cap=mkt_cap if i == 0 else None,
                enterprise_value=None,
                price_to_earnings_ratio=None,
                price_to_book_ratio=None,
                price_to_sales_ratio=None,
                enterprise_value_to_ebitda_ratio=None,
                enterprise_value_to_revenue_ratio=None,
                free_cash_flow_yield=fcf_yield,
                peg_ratio=None,
                gross_margin=gross_margin,
                operating_margin=op_margin,
                net_margin=net_margin,
                return_on_equity=roe,
                return_on_assets=roa,
                return_on_invested_capital=roic,
                asset_turnover=asset_turn,
                inventory_turnover=None,
                receivables_turnover=None,
                days_sales_outstanding=None,
                operating_cycle=None,
                working_capital_turnover=wc_turn,
                current_ratio=current_ratio,
                quick_ratio=None,
                cash_ratio=cash_ratio,
                operating_cash_flow_ratio=op_cf_ratio,
                debt_to_equity=d2e_val,
                debt_to_assets=d2a,
                interest_coverage=int_cov,
                revenue_growth=rev_growth,
                earnings_growth=earn_growth,
                book_value_growth=None,
                earnings_per_share_growth=None,
                free_cash_flow_growth=None,
                operating_income_growth=None,
                ebitda_growth=None,
                payout_ratio=None,
                earnings_per_share=eps,
                book_value_per_share=bvps,
                free_cash_flow_per_share=fcf_ps,
            )
            results.append(m)

    if not results:
        return []

    _cache.set_financial_metrics(cache_key, [m.model_dump() for m in results])
    return results


# ---------------------------------------------------------------------------
# Line Items  (maps common field names → yfinance statement rows)
# ---------------------------------------------------------------------------

_LINE_ITEM_MAP = {
    "revenue": ("financials", "Total Revenue"),
    "net_income": ("financials", "Net Income", "Net Income Common Stockholders"),
    "operating_income": ("financials", "Operating Income"),
    "gross_profit": ("financials", "Gross Profit"),
    "ebit": ("financials", "EBIT"),
    "interest_expense": ("financials", "Interest Expense"),
    "earnings_per_share": ("financials", "Diluted EPS", "Basic EPS"),
    "free_cash_flow": ("cashflow", "Free Cash Flow"),
    "capital_expenditure": ("cashflow", "Capital Expenditure"),
    "depreciation_and_amortization": ("cashflow", "Reconciled Depreciation", "Depreciation And Amortization"),
    "total_debt": ("balance_sheet", "Total Debt"),
    "total_assets": ("balance_sheet", "Total Assets"),
    "total_liabilities": ("balance_sheet", "Total Liabilities Net Minority Interest"),
    "current_assets": ("balance_sheet", "Current Assets"),
    "current_liabilities": ("balance_sheet", "Current Liabilities"),
    "book_value_per_share": None,  # computed
    "outstanding_shares": None,    # computed
    "dividends_and_other_cash_distributions": ("cashflow", "Cash Dividends Paid", "Common Stock Dividend Paid"),
    "operating_margin": None,
    "debt_to_equity": None,
}


def search_line_items(
    ticker: str,
    line_items: list[str],
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
    api_key: str = None,
) -> list[LineItem]:
    try:
        t = _ticker(ticker)
        fin = t.financials if period == "annual" else t.quarterly_financials
        bs = t.balance_sheet if period == "annual" else t.quarterly_balance_sheet
        cf = t.cashflow if period == "annual" else t.quarterly_cashflow
        info = t.info or {}
    except Exception as e:
        logger.warning("yfinance fetch failed for %s: %s", ticker, e)
        return []

    stmts = {"financials": fin, "balance_sheet": bs, "cashflow": cf}

    if period == "ttm":
        # Return a single TTM row by summing the last 4 quarters
        def _ttm(stmt: pd.DataFrame, *row_names: str) -> float | None:
            if stmt is None or stmt.empty:
                return None
            for name in row_names:
                if name in stmt.index:
                    vals = stmt.loc[name].dropna().head(4)
                    if not vals.empty:
                        return _safe_float(vals.sum())
            return None

        shares = _safe_float(info.get("sharesOutstanding"))
        ni_ttm = _ttm(t.quarterly_financials, "Net Income", "Net Income Common Stockholders")

        row_data: dict = {"ticker": ticker, "report_period": end_date, "period": "ttm", "currency": "USD"}
        for item in line_items:
            mapping = _LINE_ITEM_MAP.get(item)
            if mapping is None:
                # computed fields
                if item == "book_value_per_share":
                    eq = _get_stmt_value(t.quarterly_balance_sheet, "Stockholders Equity", "Common Stock Equity")
                    row_data[item] = (eq / shares) if eq is not None and shares else None
                elif item == "outstanding_shares":
                    row_data[item] = shares
                elif item == "operating_margin":
                    rev = _ttm(t.quarterly_financials, "Total Revenue")
                    op = _ttm(t.quarterly_financials, "Operating Income")
                    row_data[item] = (op / rev) if op is not None and rev else None
                elif item == "debt_to_equity":
                    td = _get_stmt_value(t.quarterly_balance_sheet, "Total Debt")
                    eq = _get_stmt_value(t.quarterly_balance_sheet, "Stockholders Equity", "Common Stock Equity")
                    row_data[item] = (td / eq) if td is not None and eq and eq != 0 else None
                else:
                    row_data[item] = None
                continue

            stmt_key = mapping[0]
            row_names = mapping[1:]
            stmt = t.quarterly_financials if stmt_key == "financials" else (
                t.quarterly_balance_sheet if stmt_key == "balance_sheet" else t.quarterly_cashflow
            )
            row_data[item] = _ttm(stmt, *row_names)

        return [LineItem(**row_data)]

    # Annual / quarterly: one row per period column
    if fin is None or fin.empty:
        return []

    cols = [c for c in fin.columns if pd.Timestamp(c) <= pd.Timestamp(end_date)]
    cols = sorted(cols, reverse=True)[:limit]

    results = []
    shares = _safe_float((t.info or {}).get("sharesOutstanding"))

    for i, col in enumerate(cols):
        col_dt = pd.Timestamp(col).to_pydatetime()
        row_data = {"ticker": ticker, "report_period": col_dt.strftime("%Y-%m-%d"), "period": period, "currency": "USD"}
        for item in line_items:
            mapping = _LINE_ITEM_MAP.get(item)
            if mapping is None:
                if item == "book_value_per_share":
                    eq = _get_stmt_value(bs, "Stockholders Equity", "Common Stock Equity", col_idx=i)
                    row_data[item] = (eq / shares) if eq is not None and shares else None
                elif item == "outstanding_shares":
                    row_data[item] = shares
                elif item == "operating_margin":
                    rev = _get_stmt_value(fin, "Total Revenue", col_idx=i)
                    op = _get_stmt_value(fin, "Operating Income", col_idx=i)
                    row_data[item] = (op / rev) if op is not None and rev else None
                elif item == "debt_to_equity":
                    td = _get_stmt_value(bs, "Total Debt", col_idx=i)
                    eq = _get_stmt_value(bs, "Stockholders Equity", "Common Stock Equity", col_idx=i)
                    row_data[item] = (td / eq) if td is not None and eq and eq != 0 else None
                else:
                    row_data[item] = None
                continue

            stmt_key = mapping[0]
            row_names = mapping[1:]
            stmt = stmts[stmt_key]
            row_data[item] = _get_stmt_value(stmt, *row_names, col_idx=i)

        results.append(LineItem(**row_data))

    return results


# ---------------------------------------------------------------------------
# Insider Trades
# ---------------------------------------------------------------------------

def get_insider_trades(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 1000,
    api_key: str = None,
) -> list[InsiderTrade]:
    cache_key = f"{ticker}_{start_date or 'none'}_{end_date}_{limit}"
    if cached := _cache.get_insider_trades(cache_key):
        return [InsiderTrade(**t) for t in cached]

    try:
        t = _ticker(ticker)
        df = t.insider_transactions
    except Exception as e:
        logger.warning("yfinance insider_transactions failed for %s: %s", ticker, e)
        return []

    if df is None or df.empty:
        return []

    trades: list[InsiderTrade] = []
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    start_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None

    for _, row in df.iterrows():
        # yfinance columns: Insider, Position, Date, Transaction, #Shares, Value, #Shares Total, SEC Form 4
        raw_date = row.get("Start Date") or row.get("Date") or row.get("startDate")
        if raw_date is None:
            continue
        if hasattr(raw_date, "to_pydatetime"):
            trade_dt = raw_date.to_pydatetime()
        else:
            try:
                trade_dt = datetime.strptime(str(raw_date)[:10], "%Y-%m-%d")
            except Exception:
                continue

        if trade_dt > end_dt:
            continue
        if start_dt and trade_dt < start_dt:
            continue

        shares_raw = row.get("Shares") or row.get("#Shares")
        price_raw = row.get("Value") or row.get("Price")
        shares_total = row.get("Insider Shares") or row.get("#Shares Total")

        transaction = str(row.get("Transaction", row.get("transaction", ""))).lower()
        shares_val = _safe_float(shares_raw)
        # yfinance uses negative for sales
        if shares_val is not None and ("sale" in transaction or "sell" in transaction):
            shares_val = -abs(shares_val)

        trades.append(InsiderTrade(
            ticker=ticker,
            issuer=ticker,
            name=str(row.get("Insider", row.get("name", ""))),
            title=str(row.get("Position", row.get("title", ""))),
            is_board_director=None,
            transaction_date=trade_dt.strftime("%Y-%m-%dT00:00:00"),
            transaction_shares=shares_val,
            transaction_price_per_share=None,
            transaction_value=_safe_float(price_raw),
            shares_owned_before_transaction=None,
            shares_owned_after_transaction=_safe_float(shares_total),
            security_title=None,
            filing_date=trade_dt.strftime("%Y-%m-%dT00:00:00"),
        ))
        if len(trades) >= limit:
            break

    if not trades:
        return []

    _cache.set_insider_trades(cache_key, [tr.model_dump() for tr in trades])
    return trades


# ---------------------------------------------------------------------------
# Company News  (yfinance news via .news property)
# ---------------------------------------------------------------------------

def get_company_news(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 1000,
    api_key: str = None,
) -> list[CompanyNews]:
    cache_key = f"{ticker}_{start_date or 'none'}_{end_date}_{limit}"
    if cached := _cache.get_company_news(cache_key):
        return [CompanyNews(**n) for n in cached]

    try:
        t = _ticker(ticker)
        raw_news = t.news or []
    except Exception as e:
        logger.warning("yfinance news failed for %s: %s", ticker, e)
        return []

    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    start_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None

    news_list: list[CompanyNews] = []
    for item in raw_news:
        content = item.get("content", item)
        pub_date_raw = content.get("pubDate") or content.get("providerPublishTime") or item.get("providerPublishTime")
        if pub_date_raw is None:
            continue
        if isinstance(pub_date_raw, (int, float)):
            pub_dt = datetime.fromtimestamp(pub_date_raw)
        else:
            try:
                pub_dt = datetime.strptime(str(pub_date_raw)[:10], "%Y-%m-%d")
            except Exception:
                continue

        if pub_dt > end_dt:
            continue
        if start_dt and pub_dt < start_dt:
            continue

        title = content.get("title") or item.get("title") or ""
        url = (content.get("canonicalUrl", {}) or {}).get("url") or content.get("url") or item.get("link") or ""
        source = (content.get("provider", {}) or {}).get("displayName") or content.get("source") or "Yahoo Finance"

        news_list.append(CompanyNews(
            ticker=ticker,
            title=title,
            author=None,
            source=source,
            date=pub_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            url=url,
            sentiment=None,
        ))
        if len(news_list) >= limit:
            break

    if not news_list:
        return []

    _cache.set_company_news(cache_key, [n.model_dump() for n in news_list])
    return news_list


# ---------------------------------------------------------------------------
# Market Cap & Company Facts
# ---------------------------------------------------------------------------

def get_market_cap(
    ticker: str,
    end_date: str,
    api_key: str = None,
) -> float | None:
    try:
        info = _ticker(ticker).info or {}
        return _safe_float(info.get("marketCap"))
    except Exception as e:
        logger.warning("yfinance market cap failed for %s: %s", ticker, e)
        return None


def get_company_facts(ticker: str) -> CompanyFacts | None:
    try:
        info = _ticker(ticker).info or {}
    except Exception as e:
        logger.warning("yfinance company facts failed for %s: %s", ticker, e)
        return None

    return CompanyFacts(
        ticker=ticker,
        name=info.get("longName") or info.get("shortName") or ticker,
        cik=None,
        industry=info.get("industry"),
        sector=info.get("sector"),
        exchange=info.get("exchange"),
        location=f"{info.get('city', '')}, {info.get('state', '')}, {info.get('country', '')}".strip(", "),
        market_cap=_safe_float(info.get("marketCap")),
        number_of_employees=info.get("fullTimeEmployees"),
        website_url=info.get("website"),
        sic_code=None,
        sic_industry=None,
        sic_sector=None,
    )
