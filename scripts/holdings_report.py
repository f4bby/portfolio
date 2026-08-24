from portfolio import Portfolio
from portfolio import reports


portfolio = Portfolio.from_csv("data/transactions_demo.csv")

reports.print_holdings_report(portfolio)
reports.print_order_unrealized_pnl_report(portfolio)