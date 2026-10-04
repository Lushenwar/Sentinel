from app import db, serializers
from app.clients import inventory, payments
from app.pagination import clamp_page_size, paginate

_ORDER_SQL = "SELECT * FROM orders_view WHERE id = %s"
_LIST_SQL = "SELECT * FROM orders_view WHERE customer_id = %s ORDER BY created_at DESC, id DESC"


def get_order(order_id: str) -> dict:
    row = db.fetch_one(_ORDER_SQL, (order_id,))
    if row is None:
        return {"status": 404, "body": {"error": "order not found"}}
    return {"status": 200, "body": serializers.order_to_dict(row)}


def list_orders(customer_id: str, page: int = 1, page_size: int | None = None) -> dict:
    rows = db.fetch_all(_LIST_SQL, (customer_id,))
    body = paginate([serializers.order_to_dict(r) for r in rows], page, clamp_page_size(page_size))
    return {"status": 200, "body": body}


def create_order(customer_id: str, lines: list[dict], card_token: str) -> dict:
    stock = inventory.get_stock_many([line["sku"] for line in lines])
    short = [line["sku"] for line in lines if stock[line["sku"]] < line["qty"]]
    if short:
        return {"status": 409, "body": {"error": "insufficient stock", "skus": short}}
    total = sum(line["qty"] * line["unit_price_cents"] for line in lines)
    order_id = db.fetch_one("SELECT create_order(%s, %s)", (customer_id, total))[0]
    payments.charge(order_id, total, card_token)
    return {"status": 201, "body": {"id": order_id, "total": serializers.money(total)}}
