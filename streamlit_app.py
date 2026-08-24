from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
import sys

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from portfolio.market import Market, price_history
from portfolio.portfolio import Portfolio


st.set_page_config(
    page_title="Portfolio",
    page_icon="📈",
    layout="wide",
)

DEFAULT_TRANSACTIONS = ROOT / "data" / "transactions_demo.csv"


# ---------------------------------------------------------
# Formatting / dataframe helpers
# ---------------------------------------------------------

def money(value: Decimal | float | int | None) -> str:
    if value is None:
        return "—"
    return f"€{value:,.2f}"


def percentage(value: Decimal | float | int | None) -> str:
    """Format a ratio (0.12) as a percentage (+12.00%)."""
    if value is None:
        return "—"
    return f"{float(value) * 100:+.2f}%"


def transactions_frame(portfolio: Portfolio) -> pd.DataFrame:
    """Convert the backend Transaction objects into a UI dataframe."""
    rows = [asdict(tx) for tx in portfolio.transactions]

    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows)
    frame["ticker"] = frame["ticker"].fillna("CASH")

    decimal_columns = [
        "shares",
        "price",
        "fx_to_eur",
        "fees_eur",
        "amount_eur",
    ]
    for column in decimal_columns:
        if column in frame.columns:
            frame[column] = frame[column].map(float)

    return frame


def holdings_frame(holdings: pd.DataFrame) -> pd.DataFrame:
    """Return a Streamlit-friendly copy of the backend holdings report."""
    frame = holdings.copy()

    decimal_columns = [
        "shares",
        "avg_cost_eur",
        "cost_eur",
        "market_price",
        "fx_to_eur",
        "value_eur",
        "pnl_eur",
    ]
    for column in decimal_columns:
        if column in frame.columns:
            frame[column] = frame[column].map(float)

    # Backend stores these as ratios; the UI displays percentages.
    for column in ("pnl_pct", "weight"):
        if column in frame.columns:
            frame[column] = frame[column].map(lambda value: float(value) * 100)

    return frame


def build_summary(portfolio: Portfolio, holdings: pd.DataFrame) -> dict:
    holdings_value = sum(holdings["value_eur"], Decimal("0"))
    cost_basis = sum(holdings["cost_eur"], Decimal("0"))
    market_value = portfolio.cash_balance() + holdings_value
    net_contributions = portfolio.net_contributions()
    profit_loss = market_value - net_contributions
    return_pct = (
        profit_loss / net_contributions
        if net_contributions != 0
        else Decimal("0")
    )

    return {
        "market_value": market_value,
        "cost_basis": cost_basis,
        "profit_loss": profit_loss,
        "return_pct": return_pct,
        "positions": len(holdings),
    }


# ---------------------------------------------------------
# Cached market data
# ---------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def market_snapshot(
    tickers: tuple[str, ...],
    currencies: tuple[str, ...],
) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    market = Market()
    return (
        market.get_prices(list(tickers)),
        market.get_fx_rates(list(currencies)),
    )


@st.cache_data(ttl=300, show_spinner=False)
def cached_price_history(ticker: str, period: str) -> pd.DataFrame:
    return price_history(ticker, period=period)


# ---------------------------------------------------------
# UI
# ---------------------------------------------------------

def render_header() -> None:
    st.title("📈 Portfolio")
    st.caption("Portfolio overview, holdings and transaction history.")


def render_sidebar():
    with st.sidebar:
        st.header("Portfolio")

        source = st.radio(
            "Data source",
            ["Demo portfolio", "Upload CSV"],
        )

        uploaded_file = None
        if source == "Upload CSV":
            uploaded_file = st.file_uploader(
                "Transactions CSV",
                type=["csv"],
            )

        st.divider()

        period = st.selectbox(
            "Chart period",
            ["1mo", "3mo", "6mo", "1y", "2y", "5y"],
            index=3,
        )

        refresh = st.button(
            "Refresh market data",
            use_container_width=True,
        )

    return source, uploaded_file, period, refresh


def render_metrics(summary: dict) -> None:
    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Portfolio Value", money(summary["market_value"]))
    col2.metric("Open Cost Basis", money(summary["cost_basis"]))
    col3.metric(
        "Total Profit / Loss",
        money(summary["profit_loss"]),
        percentage(summary["return_pct"]),
    )
    col4.metric("Positions", summary["positions"])


def render_overview(portfolio: Portfolio, holdings: pd.DataFrame) -> None:
    st.subheader("Overview")

    left, right = st.columns([2, 1], gap="large")
    ui_holdings = holdings_frame(holdings)

    with left:
        st.markdown("#### Allocation")
        if ui_holdings.empty:
            st.info("No portfolio positions.")
        else:
            st.bar_chart(
                ui_holdings[["ticker", "value_eur"]],
                x="ticker",
                y="value_eur",
            )

    with right:
        st.markdown("#### Account")
        st.metric("Cash", money(portfolio.cash_balance()))
        st.metric("Net contributions", money(portfolio.net_contributions()))
        st.metric("Realized P/L", money(portfolio.realized_pnl()))
        st.metric(
            "Income",
            money(portfolio.dividend_income() + portfolio.interest_income()),
        )


def render_holdings(holdings: pd.DataFrame) -> None:
    st.subheader("Holdings")

    frame = holdings_frame(holdings)
    if frame.empty:
        st.info("No open positions.")
        return

    columns = [
        "ticker",
        "currency",
        "shares",
        "avg_cost_eur",
        "market_price",
        "value_eur",
        "pnl_eur",
        "pnl_pct",
        "weight",
    ]

    st.dataframe(
        frame[columns],
        hide_index=True,
        use_container_width=True,
        column_config={
            "ticker": "Ticker",
            "currency": "Currency",
            "shares": st.column_config.NumberColumn("Shares", format="%.4f"),
            "avg_cost_eur": st.column_config.NumberColumn(
                "Avg Cost (EUR)", format="€%.2f"
            ),
            "market_price": st.column_config.NumberColumn(
                "Price (local)", format="%.2f"
            ),
            "value_eur": st.column_config.NumberColumn(
                "Value (EUR)", format="€%.2f"
            ),
            "pnl_eur": st.column_config.NumberColumn(
                "P/L (EUR)", format="€%.2f"
            ),
            "pnl_pct": st.column_config.NumberColumn(
                "Return", format="%.2f%%"
            ),
            "weight": st.column_config.ProgressColumn(
                "Weight",
                min_value=0.0,
                max_value=100.0,
                format="%.1f%%",
            ),
        },
    )


def render_asset_explorer(
    portfolio: Portfolio,
    holdings: pd.DataFrame,
    period: str,
) -> None:
    st.subheader("Asset Explorer")

    if holdings.empty:
        st.info("No assets in portfolio.")
        return

    ticker = st.selectbox("Asset", holdings["ticker"].tolist())
    position = holdings.loc[holdings["ticker"] == ticker].iloc[0]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Price",
        f"{position['market_price']:,.2f} {position['currency']}",
    )
    col2.metric("Shares", f"{position['shares']:,.4f}")
    col3.metric("Value", money(position["value_eur"]))
    col4.metric("Return", percentage(position["pnl_pct"]))

    st.markdown(f"#### {ticker} price history")
    try:
        history = cached_price_history(ticker, period)
    except Exception as exc:
        st.warning(f"Could not load price history: {exc}")
    else:
        if history.empty:
            st.info("No price history available.")
        else:
            st.line_chart(history, x="date", y="close")

    st.markdown(f"#### {ticker} transactions")
    transactions = transactions_frame(portfolio)
    transactions = transactions.loc[transactions["ticker"] == ticker]
    st.dataframe(transactions, hide_index=True, use_container_width=True)


def render_transactions(portfolio: Portfolio) -> None:
    st.subheader("Transactions")

    transactions = transactions_frame(portfolio)
    if transactions.empty:
        st.info("No transactions.")
        return

    tickers = sorted(transactions["ticker"].dropna().unique().tolist())
    selected_tickers = st.multiselect(
        "Ticker",
        tickers,
        default=tickers,
    )

    filtered = transactions.loc[transactions["ticker"].isin(selected_tickers)]
    st.dataframe(filtered, hide_index=True, use_container_width=True)


# ---------------------------------------------------------
# Backend loading
# ---------------------------------------------------------

@st.cache_resource
def load_demo_portfolio() -> Portfolio:
    return Portfolio.from_csv(DEFAULT_TRANSACTIONS)


def load_uploaded_portfolio(file) -> Portfolio:
    # pandas.read_csv (used by Portfolio.from_csv) accepts Streamlit UploadedFile.
    file.seek(0)
    return Portfolio.from_csv(file)


def value_portfolio(portfolio: Portfolio) -> pd.DataFrame:
    tickers = tuple(portfolio.tickers())
    currencies = tuple(portfolio.currencies())

    prices, fx_rates = market_snapshot(tickers, currencies)
    return portfolio.valued_positions(prices, fx_rates)


# ---------------------------------------------------------
# App
# ---------------------------------------------------------

def main() -> None:
    render_header()
    source, uploaded_file, period, refresh = render_sidebar()

    if refresh:
        st.cache_resource.clear()
        st.cache_data.clear()
        st.rerun()

    try:
        if source == "Demo portfolio":
            portfolio = load_demo_portfolio()
        elif uploaded_file is None:
            st.info("Upload a transactions CSV to continue.")
            return
        else:
            portfolio = load_uploaded_portfolio(uploaded_file)
    except Exception as exc:
        st.error(f"Could not load transactions: {exc}")
        return

    try:
        with st.spinner("Loading market data..."):
            holdings = value_portfolio(portfolio)
    except Exception as exc:
        st.error(f"Could not value portfolio with current market data: {exc}")
        st.info("Your transactions loaded successfully. Try Refresh market data.")
        render_transactions(portfolio)
        return

    summary = build_summary(portfolio, holdings)
    render_metrics(summary)

    st.divider()
    overview, holdings_tab, explorer, transactions = st.tabs(
        ["Overview", "Holdings", "Asset Explorer", "Transactions"]
    )

    with overview:
        render_overview(portfolio, holdings)

    with holdings_tab:
        render_holdings(holdings)

    with explorer:
        render_asset_explorer(portfolio, holdings, period)

    with transactions:
        render_transactions(portfolio)


if __name__ == "__main__":
    main()
