from app import db
from app.handlers.orders import create_order

_CART_SQL = "SELECT payload FROM carts WHERE id = %s"


def load_cart(cart_id: str) -> dict:
    row = db.fetch_one(_CART_SQL, (cart_id,))
    return row[0] if row else {"items": []}


def cart_to_lines(cart: dict) -> list[dict]:
    return [
        {"sku": item["sku"], "qty": item["qty"], "unit_price_cents": item["unit_price_cents"]}
        for item in cart["items"]
    ]


def checkout(customer_id: str, cart_id: str, card_token: str) -> dict:
    return create_order(customer_id, cart_to_lines(load_cart(cart_id)), card_token)
