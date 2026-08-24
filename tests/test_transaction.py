from datetime import date
from decimal import Decimal

from portfolio import Portfolio, Transaction


def test_deposit_increases_cash():
    transaction = Transaction(
        transaction_id=1,
        date=date(2026, 8, 1),
        transaction_type="DEPOSIT",
        asset_type="CASH",
        ticker=None,
        isin=None,
        shares=Decimal("0"),
        price=Decimal("0"),
        currency="EUR",
        fx_to_eur=Decimal("1"),
        fees_eur=Decimal("0"),
        amount_eur=Decimal("10000"),
        comments="Initial capital",
    )

    portfolio = Portfolio([transaction])

    assert portfolio.cash_balance() == Decimal("10000")


def test_interest_increases_cash():
    transaction = Transaction(
        transaction_type="INTEREST",
        amount_eur=Decimal("3.30"),
        # Fill the remaining required Transaction fields
        # using the same values/helper used by your existing tests.
    )

    portfolio = Portfolio([transaction])

    assert portfolio.cash_balance() == Decimal("3.30")