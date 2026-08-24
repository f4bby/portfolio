from datetime import date
from decimal import Decimal

from portfolio import Portfolio, Transaction
from portfolio.reports import (
    holdings_report,
    order_unrealized_pnl_report,
    print_holdings_report,
    print_order_unrealized_pnl_report,
)


class FakeMarket:
    def __init__(
        self,
        prices: dict[str, Decimal],
        fx_rates: dict[str, Decimal],
    ):
        self.prices = prices
        self.fx_rates = fx_rates

    def get_prices(
        self,
        tickers: list[str],
    ) -> dict[str, Decimal]:
        return {
            ticker: self.prices[ticker]
            for ticker in tickers
        }

    def get_fx_rates(
        self,
        currencies: list[str],
    ) -> dict[str, Decimal]:
        return {
            currency: self.fx_rates[currency]
            for currency in currencies
        }


def transaction(
    transaction_id: int,
    transaction_type: str,
    *,
    shares: str = "0",
    price: str = "0",
    fees_eur: str = "0",
    amount_eur: str = "0",
) -> Transaction:
    return Transaction(
        transaction_id=transaction_id,
        date=date(2026, 8, transaction_id),
        transaction_type=transaction_type,
        asset_type=(
            "CASH"
            if transaction_type == "DEPOSIT"
            else "ETF"
        ),
        ticker=(
            None
            if transaction_type == "DEPOSIT"
            else "TEST"
        ),
        isin=None,
        shares=Decimal(shares),
        price=Decimal(price),
        currency="EUR",
        fx_to_eur=Decimal("1"),
        fees_eur=Decimal(fees_eur),
        amount_eur=Decimal(amount_eur),
        comments=None,
    )


def test_holdings_report_takes_a_portfolio_instance():
    portfolio = Portfolio(
        [
            transaction(
                1,
                "DEPOSIT",
                amount_eur="1000",
            ),
            transaction(
                2,
                "BUY",
                shares="2",
                price="100",
                fees_eur="10",
            ),
        ]
    )

    market = FakeMarket(
        prices={"TEST": Decimal("120")},
        fx_rates={"EUR": Decimal("1")},
    )

    report = holdings_report(portfolio, market=market)

    assert report.loc[0, "cost_eur"] == Decimal("210")
    assert report.loc[0, "value_eur"] == Decimal("240")
    assert report.loc[0, "pnl_eur"] == Decimal("30")
    assert report.loc[0, "weight"] == Decimal("240") / Decimal("1030")


def test_order_report_values_each_open_fifo_lot():
    portfolio = Portfolio(
        [
            transaction(
                1,
                "BUY",
                shares="2",
                price="100",
                fees_eur="2",
            ),
            transaction(
                2,
                "BUY",
                shares="3",
                price="120",
                fees_eur="3",
            ),
            transaction(
                3,
                "SELL",
                shares="1",
                price="125",
            ),
        ]
    )

    market = FakeMarket(
        prices={"TEST": Decimal("130")},
        fx_rates={"EUR": Decimal("1")},
    )

    report = order_unrealized_pnl_report(
        portfolio,
        market=market,
    )

    assert report["open_shares"].tolist() == [
        Decimal("1"),
        Decimal("3"),
    ]
    assert report["cost_eur"].tolist() == [
        Decimal("101"),
        Decimal("363"),
    ]
    assert report["pnl_eur"].tolist() == [
        Decimal("29"),
        Decimal("27"),
    ]


def test_print_reports_take_a_portfolio_instance(capsys):
    portfolio = Portfolio()
    market = FakeMarket(prices={}, fx_rates={})

    print_holdings_report(portfolio, market=market)
    print_order_unrealized_pnl_report(portfolio, market=market)

    output = capsys.readouterr().out

    assert "PORTFOLIO" in output
    assert "No open positions." in output
    assert "UNREALIZED P&L BY FIFO ORDER" in output
    assert "No open orders." in output
