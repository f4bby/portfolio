from decimal import Decimal
from typing import Protocol

import pandas as pd

from portfolio.portfolio import Portfolio


class MarketData(Protocol):
    """Market-data interface required by the reports."""

    def get_prices(
        self,
        tickers: list[str],
    ) -> dict[str, Decimal]: ...

    def get_fx_rates(
        self,
        currencies: list[str],
    ) -> dict[str, Decimal]: ...


def _market_data(
    market: MarketData | None,
) -> MarketData:
    if market is not None:
        return market

    from portfolio.market import Market

    return Market()


def holdings_report(
    portfolio: Portfolio,
    market: MarketData | None = None,
) -> pd.DataFrame:
    """Build a current-holdings report for ``portfolio``."""
    market = _market_data(market)

    prices = market.get_prices(
        portfolio.tickers(),
    )

    fx_rates = market.get_fx_rates(
        portfolio.currencies(),
    )

    return portfolio.valued_positions(
        prices,
        fx_rates,
    )


def order_unrealized_pnl_report(
    portfolio: Portfolio,
    market: MarketData | None = None,
) -> pd.DataFrame:
    """Build an unrealized P&L report for every open FIFO BUY lot."""
    market = _market_data(market)
    open_lots = portfolio.open_lots()

    columns = [
        "transaction_id",
        "date",
        "ticker",
        "currency",
        "original_shares",
        "open_shares",
        "buy_price",
        "buy_fx",
        "avg_cost_eur",
        "market_price",
        "current_fx",
        "cost_eur",
        "value_eur",
        "pnl_eur",
        "pnl_pct",
    ]

    if open_lots.empty:
        return pd.DataFrame(columns=columns)

    tickers = open_lots["ticker"].drop_duplicates().tolist()
    currencies = sorted(
        open_lots["currency"].dropna().unique().tolist()
    )

    prices = market.get_prices(tickers)
    fx_rates = market.get_fx_rates(currencies)

    rows = []

    for _, lot in open_lots.iterrows():
        ticker = lot["ticker"]
        currency = lot["currency"]

        if ticker not in prices:
            raise KeyError(
                f"Missing market price for open position {ticker}"
            )

        if currency not in fx_rates:
            raise KeyError(
                f"Missing FX rate for {currency}"
            )

        market_price = Decimal(str(prices[ticker]))
        current_fx = Decimal(str(fx_rates[currency]))
        open_shares = lot["open_shares"]
        open_cost_eur = lot["open_cost_eur"]

        value_eur = (
            open_shares
            * market_price
            * current_fx
        )

        pnl_eur = (
            value_eur
            - open_cost_eur
        )

        pnl_pct = (
            pnl_eur / open_cost_eur
            if open_cost_eur != 0
            else Decimal("0")
        )

        avg_cost_eur = (
            open_cost_eur / open_shares
            if open_shares != 0
            else Decimal("0")
        )

        rows.append(
            {
                "transaction_id": lot["transaction_id"],
                "date": lot["date"],
                "ticker": ticker,
                "currency": currency,
                "original_shares": lot["original_shares"],
                "open_shares": open_shares,
                "buy_price": lot["buy_price"],
                "buy_fx": lot["buy_fx_to_eur"],
                "avg_cost_eur": avg_cost_eur,
                "market_price": market_price,
                "current_fx": current_fx,
                "cost_eur": open_cost_eur,
                "value_eur": value_eur,
                "pnl_eur": pnl_eur,
                "pnl_pct": pnl_pct,
            }
        )

    return pd.DataFrame(rows, columns=columns)


def print_holdings_report(
    portfolio: Portfolio,
    market: MarketData | None = None,
) -> None:
    """Print the current-holdings report for ``portfolio``."""
    holdings = holdings_report(
        portfolio,
        market=market,
    )

    cash = portfolio.cash_balance()
    net_contributions = portfolio.net_contributions()
    dividends = portfolio.dividend_income()
    interest = portfolio.interest_income()
    realized_pnl = portfolio.realized_pnl()

    holdings_value = sum(
        holdings["value_eur"],
        Decimal("0"),
    )

    cost_basis = sum(
        holdings["cost_eur"],
        Decimal("0"),
    )

    unrealized_pnl = sum(
        holdings["pnl_eur"],
        Decimal("0"),
    )

    total_value = (
        cash
        + holdings_value
    )

    total_pnl = (
        total_value
        - net_contributions
    )

    total_pnl_pct = (
        total_pnl / net_contributions
        if net_contributions != 0
        else Decimal("0")
    )

    cash_pct = (
        cash / total_value
        if total_value != 0
        else Decimal("0")
    )

    print("PORTFOLIO")
    print()

    print(
        f"Net contributions:  €{net_contributions:,.2f}"
    )
    print(
        f"Total value:        €{total_value:,.2f}"
    )
    print(
        f"Holdings value:     €{holdings_value:,.2f}"
    )
    print(
        f"Open cost basis:    €{cost_basis:,.2f}"
    )
    print(
        f"Cash:               €{cash:,.2f}"
    )
    print(
        f"Cash %:              {cash_pct:.2%}"
    )

    print()

    print(
        f"Unrealized P&L:     €{unrealized_pnl:,.2f}"
    )
    print(
        f"Realized P&L:       €{realized_pnl:,.2f}"
    )
    print(
        f"Dividends:          €{dividends:,.2f}"
    )
    print(
        f"Interest:           €{interest:,.2f}"
    )
    print(
        f"Total P&L:          €{total_pnl:,.2f}"
    )
    print(
        f"Total P&L %:         {total_pnl_pct:.2%}"
    )

    print()
    print("HOLDINGS")
    print()

    if holdings.empty:
        print("No open positions.")
        return

    print(
        f"{'Ticker':<10}"
        f"{'Shares':>10}"
        f"{'Avg Cost €':>14}"
        f"{'Price':>12}"
        f"{'Value €':>14}"
        f"{'P&L €':>14}"
        f"{'P&L %':>12}"
        f"{'Weight':>12}"
    )

    for _, row in holdings.iterrows():
        print(
            f"{row['ticker']:<10}"
            f"{row['shares']:>10.2f}"
            f"{row['avg_cost_eur']:>14,.2f}"
            f"{row['market_price']:>12.2f}"
            f"{row['value_eur']:>14,.2f}"
            f"{row['pnl_eur']:>14,.2f}"
            f"{row['pnl_pct']:>11.2%}"
            f"{row['weight']:>11.2%}"
        )
    print()


def print_order_unrealized_pnl_report(
    portfolio: Portfolio,
    market: MarketData | None = None,
) -> None:
    """Print unrealized P&L for every open FIFO BUY lot."""
    report = order_unrealized_pnl_report(
        portfolio,
        market=market,
    )

    print("UNREALIZED P&L BY FIFO ORDER")
    print()

    if report.empty:
        print("No open orders.")
        return

    print(
        f"{'Date':<12}"
        f"{'Ticker':<10}"
        f"{'Shares':>12}"
        f"{'Buy':>12}"
        f"{'Current':>12}"
        f"{'Cost €':>14}"
        f"{'Value €':>14}"
        f"{'P&L €':>14}"
        f"{'P&L %':>10}"
    )

    for _, row in report.iterrows():
        print(
            f"{str(row['date']):<12}"
            f"{row['ticker']:<10}"
            f"{row['open_shares']:>12.4f}"
            f"{row['buy_price']:>12.2f}"
            f"{row['market_price']:>12.2f}"
            f"{row['cost_eur']:>14,.2f}"
            f"{row['value_eur']:>14,.2f}"
            f"{row['pnl_eur']:>14,.2f}"
            f"{row['pnl_pct']:>9.2%}"
        )
    print()
