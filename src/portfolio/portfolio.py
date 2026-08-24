from decimal import Decimal
from pathlib import Path

import pandas as pd

from portfolio.transaction import Transaction


class Portfolio:
    def __init__(
        self,
        transactions: list[Transaction] | None = None,
    ):
        self.transactions: list[Transaction] = transactions or []

    @staticmethod
    def _decimal(value) -> Decimal:
        if isinstance(value, Decimal):
            return value

        return Decimal(str(value))

    @classmethod
    def from_csv(
        cls,
        filepath: str | Path,
    ) -> "Portfolio":
        df = pd.read_csv(filepath)

        # Convert NaN values from empty CSV cells to None.
        df = df.astype(object).where(pd.notna(df), None)

        transactions = [
            Transaction.from_dict(row)
            for row in df.to_dict(orient="records")
        ]

        return cls(transactions)

    def cash_balance(self) -> Decimal:
        """Return the current cash balance in EUR."""
        cash = Decimal("0")

        for tx in self.transactions:
            if tx.transaction_type == "DEPOSIT":
                cash += tx.amount_eur

            elif tx.transaction_type == "WITHDRAWAL":
                cash -= tx.amount_eur

            elif tx.transaction_type == "BUY":
                trade_value_eur = (
                    tx.shares
                    * tx.price
                    * tx.fx_to_eur
                )

                cash -= trade_value_eur
                cash -= tx.fees_eur

            elif tx.transaction_type == "SELL":
                trade_value_eur = (
                    tx.shares
                    * tx.price
                    * tx.fx_to_eur
                )

                cash += trade_value_eur
                cash -= tx.fees_eur

            elif tx.transaction_type == "DIVIDEND":
                cash += tx.amount_eur

            elif tx.transaction_type == "INTEREST":
                cash += tx.amount_eur

        return cash

    def net_contributions(self) -> Decimal:
        """Return deposits minus withdrawals."""
        deposits = sum(
            (
                tx.amount_eur
                for tx in self.transactions
                if tx.transaction_type == "DEPOSIT"
            ),
            Decimal("0"),
        )

        withdrawals = sum(
            (
                tx.amount_eur
                for tx in self.transactions
                if tx.transaction_type == "WITHDRAWAL"
            ),
            Decimal("0"),
        )

        return deposits - withdrawals

    def dividend_income(self) -> Decimal:
        """Return total dividends received in EUR."""
        return sum(
            (
                tx.amount_eur
                for tx in self.transactions
                if tx.transaction_type == "DIVIDEND"
            ),
            Decimal("0"),
        )

    def interest_income(self) -> Decimal:
        """Return total interest received in EUR."""
        return sum(
            (
                tx.amount_eur
                for tx in self.transactions
                if tx.transaction_type == "INTEREST"
            ),
            Decimal("0"),
        )

    def _fifo_trade_state(
        self,
    ) -> tuple[dict[str, list[dict]], Decimal]:
        """
        Replay BUY and SELL transactions using FIFO.

        Each BUY creates a lot. SELL transactions consume the oldest
        open lots first.

        BUY fees are included in cost basis.
        SELL fees reduce sale proceeds.

        Transaction order is assumed to be chronological.
        """
        lots: dict[str, list[dict]] = {}
        realized_pnl = Decimal("0")

        for tx in self.transactions:
            if tx.transaction_type not in ("BUY", "SELL"):
                continue

            if tx.ticker is None:
                continue

            ticker = tx.ticker

            if ticker not in lots:
                lots[ticker] = []

            if tx.transaction_type == "BUY":
                trade_cost_eur = (
                    tx.shares
                    * tx.price
                    * tx.fx_to_eur
                )

                total_cost_eur = (
                    trade_cost_eur
                    + tx.fees_eur
                )

                lots[ticker].append(
                    {
                        "transaction_id": tx.transaction_id,
                        "date": tx.date,
                        "ticker": ticker,
                        "currency": tx.currency,
                        "buy_price": tx.price,
                        "buy_fx_to_eur": tx.fx_to_eur,
                        "original_shares": tx.shares,
                        "open_shares": tx.shares,
                        "open_cost_eur": total_cost_eur,
                    }
                )

                continue

            # SELL
            shares_to_sell = tx.shares

            available_shares = sum(
                (
                    lot["open_shares"]
                    for lot in lots[ticker]
                ),
                Decimal("0"),
            )

            if available_shares == 0:
                raise ValueError(
                    f"Cannot sell {ticker}; no shares owned."
                )

            if shares_to_sell > available_shares:
                raise ValueError(
                    f"Cannot sell {tx.shares} shares of {ticker}; "
                    f"only {available_shares} owned."
                )

            cost_removed = Decimal("0")

            for lot in lots[ticker]:
                if shares_to_sell == 0:
                    break

                lot_shares = lot["open_shares"]

                if lot_shares == 0:
                    continue

                shares_from_lot = min(
                    shares_to_sell,
                    lot_shares,
                )

                # If the entire lot is consumed, remove the exact
                # remaining cost. This avoids Decimal residuals.
                if shares_from_lot == lot_shares:
                    lot_cost_removed = lot["open_cost_eur"]

                else:
                    lot_cost_removed = (
                        lot["open_cost_eur"]
                        * shares_from_lot
                        / lot_shares
                    )

                lot["open_shares"] -= shares_from_lot
                lot["open_cost_eur"] -= lot_cost_removed

                if lot["open_shares"] == 0:
                    lot["open_cost_eur"] = Decimal("0")

                cost_removed += lot_cost_removed
                shares_to_sell -= shares_from_lot

            sale_value_eur = (
                tx.shares
                * tx.price
                * tx.fx_to_eur
            )

            sale_proceeds_eur = (
                sale_value_eur
                - tx.fees_eur
            )

            realized_pnl += (
                sale_proceeds_eur
                - cost_removed
            )

        return lots, realized_pnl

    def _trade_state(
        self,
    ) -> tuple[dict[str, dict], Decimal]:
        """
        Return aggregated open positions and realized P&L using FIFO.
        """
        lots, realized_pnl = self._fifo_trade_state()

        positions: dict[str, dict] = {}

        for ticker, ticker_lots in lots.items():
            open_lots = [
                lot
                for lot in ticker_lots
                if lot["open_shares"] > 0
            ]

            if not open_lots:
                continue

            shares = sum(
                (
                    lot["open_shares"]
                    for lot in open_lots
                ),
                Decimal("0"),
            )

            cost_eur = sum(
                (
                    lot["open_cost_eur"]
                    for lot in open_lots
                ),
                Decimal("0"),
            )

            positions[ticker] = {
                "shares": shares,
                "cost_eur": cost_eur,
                "currency": open_lots[0]["currency"],
            }

        return positions, realized_pnl

    def positions(self) -> pd.DataFrame:
        """Return current open positions using FIFO cost basis."""
        positions, _ = self._trade_state()

        data = []

        for ticker, position in positions.items():
            data.append(
                {
                    "ticker": ticker,
                    "currency": position["currency"],
                    "shares": position["shares"],
                    "cost_eur": position["cost_eur"],
                }
            )

        return pd.DataFrame(
            data,
            columns=[
                "ticker",
                "currency",
                "shares",
                "cost_eur",
            ],
        )

    def open_lots(self) -> pd.DataFrame:
        """Return the currently open FIFO BUY lots."""
        lots, _ = self._fifo_trade_state()

        rows = [
            lot.copy()
            for ticker_lots in lots.values()
            for lot in ticker_lots
            if lot["open_shares"] > 0
        ]

        return pd.DataFrame(
            rows,
            columns=[
                "transaction_id",
                "date",
                "ticker",
                "currency",
                "buy_price",
                "buy_fx_to_eur",
                "original_shares",
                "open_shares",
                "open_cost_eur",
            ],
        )

    def realized_pnl(self) -> Decimal:
        """Return cumulative FIFO realized P&L in EUR."""
        _, realized_pnl = self._trade_state()

        return realized_pnl

    def tickers(self) -> list[str]:
        """Return tickers for currently open positions."""
        positions = self.positions()

        if positions.empty:
            return []

        return positions["ticker"].tolist()

    def currencies(self) -> list[str]:
        """Return currencies used by currently open positions."""
        positions = self.positions()

        if positions.empty:
            return []

        return sorted(
            {
                currency
                for currency in positions["currency"]
                if currency is not None
            }
        )

    def valued_positions(
        self,
        prices: dict[str, Decimal],
        fx_rates: dict[str, Decimal],
    ) -> pd.DataFrame:
        """Return open positions valued with the supplied market data."""
        positions = self.positions()

        rows = []

        for _, position in positions.iterrows():
            ticker = position["ticker"]
            currency = position["currency"]
            shares = position["shares"]
            cost_eur = position["cost_eur"]

            if ticker not in prices:
                raise KeyError(
                    f"Missing market price for {ticker}"
                )

            if currency not in fx_rates:
                raise KeyError(
                    f"Missing FX rate for {currency}"
                )

            market_price = self._decimal(
                prices[ticker]
            )

            fx_to_eur = self._decimal(
                fx_rates[currency]
            )

            value_eur = (
                shares
                * market_price
                * fx_to_eur
            )

            pnl_eur = (
                value_eur
                - cost_eur
            )

            average_cost_eur = (
                cost_eur / shares
                if shares != 0
                else Decimal("0")
            )

            pnl_pct = (
                pnl_eur / cost_eur
                if cost_eur != 0
                else Decimal("0")
            )

            rows.append(
                {
                    "ticker": ticker,
                    "currency": currency,
                    "shares": shares,
                    "avg_cost_eur": average_cost_eur,
                    "cost_eur": cost_eur,
                    "market_price": market_price,
                    "fx_to_eur": fx_to_eur,
                    "value_eur": value_eur,
                    "pnl_eur": pnl_eur,
                    "pnl_pct": pnl_pct,
                }
            )

        holdings = pd.DataFrame(
            rows,
            columns=[
                "ticker",
                "currency",
                "shares",
                "avg_cost_eur",
                "cost_eur",
                "market_price",
                "fx_to_eur",
                "value_eur",
                "pnl_eur",
                "pnl_pct",
            ],
        )

        cash = self.cash_balance()

        holdings_value = sum(
            holdings["value_eur"],
            Decimal("0"),
        )

        total_value = (
            cash
            + holdings_value
        )

        if not holdings.empty:
            holdings["weight"] = holdings["value_eur"].apply(
                lambda value: (
                    value / total_value
                    if total_value != 0
                    else Decimal("0")
                )
            )

        else:
            holdings["weight"] = pd.Series(
                dtype=object,
            )

        return holdings

    def holdings_value(
        self,
        prices: dict[str, Decimal],
        fx_rates: dict[str, Decimal],
    ) -> Decimal:
        """
        Return the current market value of all open positions in EUR.
        """
        holdings = self.valued_positions(
            prices,
            fx_rates,
        )

        return sum(
            holdings["value_eur"],
            Decimal("0"),
        )

    def unrealized_pnl(
        self,
        prices: dict[str, Decimal],
        fx_rates: dict[str, Decimal],
    ) -> Decimal:
        """
        Return FIFO unrealized P&L on currently open positions in EUR.
        """
        holdings = self.valued_positions(
            prices,
            fx_rates,
        )

        return sum(
            holdings["pnl_eur"],
            Decimal("0"),
        )

    def total_value(
        self,
        prices: dict[str, Decimal],
        fx_rates: dict[str, Decimal],
    ) -> Decimal:
        """
        Return cash plus current holdings value in EUR.
        """
        return (
            self.cash_balance()
            + self.holdings_value(
                prices,
                fx_rates,
            )
        )

    def total_pnl(
        self,
        prices: dict[str, Decimal],
        fx_rates: dict[str, Decimal],
    ) -> Decimal:
        """
        Return total investment P&L in EUR.

        Deposits and withdrawals are external cash flows and are
        excluded from investment performance.
        """
        return (
            self.total_value(
                prices,
                fx_rates,
            )
            - self.net_contributions()
        )
