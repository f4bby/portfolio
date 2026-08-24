from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

import pandas as pd
import requests
import yfinance as yf




ECB_BASE_URL = "https://data-api.ecb.europa.eu/service/data/EXR"


class Market:
    def __init__(self, on_date: date | None = None):
        self.on_date = on_date

    def get_price(self, ticker: str) -> Decimal:
        """
        Return the latest available closing price for ticker.

        If on_date is set, return the most recent closing price
        available on or before that date.
        """

        stock = yf.Ticker(ticker)

        if self.on_date is None:
            history = stock.history(
                period="5d",
                auto_adjust=False,
            )

        else:
            # Look back far enough to handle weekends / holidays.
            start_date = self.on_date - timedelta(days=7)

            # yfinance's `end` date is exclusive, so add one day
            # to include self.on_date.
            end_date = self.on_date + timedelta(days=1)

            history = stock.history(
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                auto_adjust=False,
            )

        if history.empty:
            raise ValueError(
                f"No price available for {ticker}"
            )

        close = history["Close"].dropna()

        if close.empty:
            raise ValueError(
                f"No closing price available for {ticker}"
            )

        return Decimal(str(close.iloc[-1]))

    def get_fx_to_eur(
        self,
        currency: str,
        on_date: date | str | None = None,
    ) -> Decimal:
        """
        Return the value of 1 unit of currency in EUR.

        Examples:
            EUR -> 1
            USD -> ~0.86
            GBP -> ~1.17

        The lookup date can be supplied directly to this method or through
        Market(on_date=...). The direct argument takes precedence.

        For historical dates, return the latest ECB reference rate
        available on or before that date.
        """
        currency = currency.upper()

        if currency == "EUR":
            return Decimal("1")

        lookup_date = on_date if on_date is not None else self.on_date

        if isinstance(lookup_date, str):
            lookup_date = date.fromisoformat(lookup_date)

        # ECB exchange-rate key:
        # D.<currency>.EUR.SP00.A
        #
        # Example:
        # D.USD.EUR.SP00.A
        #
        # ECB quotes this as:
        # foreign currency units per 1 EUR.
        key = f"D.{currency}.EUR.SP00.A"
        url = f"{ECB_BASE_URL}/{key}"

        params = {
            "format": "csvdata",
            "lastNObservations": 1,
        }

        if lookup_date is not None:
            params["endPeriod"] = lookup_date.isoformat()

        response = requests.get(
            url,
            params=params,
            timeout=10,
        )

        response.raise_for_status()

        df = pd.read_csv(StringIO(response.text))

        if df.empty:
            raise ValueError(
                f"No ECB FX rate found for {currency}"
            )

        if "OBS_VALUE" not in df.columns:
            raise ValueError(
                f"Unexpected ECB response for {currency}"
            )

        ecb_rate = Decimal(str(df.iloc[-1]["OBS_VALUE"]))

        if ecb_rate == 0:
            raise ValueError(
                f"Invalid ECB FX rate for {currency}"
            )

        # ECB:
        # 1 EUR = X foreign currency
        #
        # Portfolio needs:
        # 1 foreign currency = X EUR
        return Decimal("1") / ecb_rate

    def get_fx_rate(
        self,
        currency: str,
        on_date: date | str | None = None,
    ) -> Decimal:
        """Convenience alias for get_fx_to_eur()."""
        return self.get_fx_to_eur(currency, on_date=on_date)

    def get_prices(
        self,
        tickers: list[str],
    ) -> dict[str, Decimal]:
        return {
            ticker: self.get_price(ticker)
            for ticker in tickers
        }

    def get_fx_rates(
        self,
        currencies: list[str],
        on_date: date | str | None = None,
    ) -> dict[str, Decimal]:
        return {
            currency: self.get_fx_to_eur(
                currency,
                on_date=on_date,
            )
            for currency in currencies
        }




def price_history(
    ticker: str,
    period: str = "1y",
    interval: str = "1d",
) -> pd.DataFrame:
    """
    Fetch historical market prices for a ticker.

    Parameters
    ----------
    ticker:
        Yahoo Finance ticker symbol, e.g. "AAPL", "MSFT", "VWCE.DE".

    period:
        History period supported by yfinance, e.g.
        "1mo", "3mo", "6mo", "1y", "2y", "5y", "max".

    interval:
        Data interval supported by yfinance, e.g.
        "1d", "1h", "1wk", "1mo".

    Returns
    -------
    pd.DataFrame
        DataFrame containing:

        date
        open
        high
        low
        close
        volume

        Returns an empty DataFrame when no market data is available.
    """

    ticker = ticker.strip().upper()

    if not ticker:
        raise ValueError("Ticker cannot be empty.")

    try:
        data = yf.Ticker(ticker).history(
            period=period,
            interval=interval,
            auto_adjust=True,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to fetch price history for {ticker}."
        ) from exc

    if data.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        )

    data = data.reset_index()

    # yfinance uses either "Date" or "Datetime"
    # depending on the requested interval.
    if "Date" in data.columns:
        data = data.rename(columns={"Date": "date"})
    elif "Datetime" in data.columns:
        data = data.rename(columns={"Datetime": "date"})

    data = data.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )

    columns = [
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    data = data[
        [column for column in columns if column in data.columns]
    ].copy()

    return data