from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass
class Transaction:
    transaction_id: int
    date: date
    transaction_type: str
    asset_type: str
    ticker: str | None
    isin: str | None
    shares: Decimal
    price: Decimal
    currency: str
    fx_to_eur: Decimal
    fees_eur: Decimal
    amount_eur: Decimal
    comments: str | None

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "Transaction":
        return cls(
            transaction_id=int(row["transaction_id"]),
            date=date.fromisoformat(str(row["date"])),
            transaction_type=str(row["transaction_type"]),
            asset_type=str(row["asset_type"]),
            ticker=row["ticker"],
            isin=row["isin"],
            shares=Decimal(str(row["shares"])),
            price=Decimal(str(row["price"])),
            currency=str(row["currency"]),
            fx_to_eur=Decimal(str(row["fx_to_eur"])),
            fees_eur=Decimal(str(row["fees_eur"])),
            amount_eur=Decimal(str(row["amount_eur"])),
            comments=row["comments"],
        )