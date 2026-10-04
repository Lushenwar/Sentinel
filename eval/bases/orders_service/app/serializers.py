from datetime import datetime
from decimal import Decimal


def money(cents: int) -> str:
    return str((Decimal(cents) / 100).quantize(Decimal("0.01")))


def order_to_dict(row: dict) -> dict:
    return {
        "id": row["id"],
        "status": row["status"],
        "total": money(row["total_cents"]),
        "currency": row["currency"],
        "created_at": row["created_at"].isoformat(),
        "customer": {
            "id": row["customer_id"],
            "email": row["customer_email"],
        },
        "items": [line_to_dict(line) for line in row["lines"]],
    }


def line_to_dict(line: dict) -> dict:
    return {"sku": line["sku"], "qty": line["qty"], "unit_price": money(line["unit_price_cents"])}


def parse_since(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
