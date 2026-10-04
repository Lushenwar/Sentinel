import httpx

from app import settings


def charge(order_id: str, amount_cents: int, card_token: str) -> dict:
    resp = httpx.post(
        f"{settings.get('payments', 'base_url')}/v1/charges",
        json={"order_id": order_id, "amount_cents": amount_cents, "card_token": card_token},
        timeout=settings.get("payments", "timeout_s"),
    )
    resp.raise_for_status()
    return resp.json()


def refund(charge_id: str) -> dict:
    resp = httpx.post(
        f"{settings.get('payments', 'base_url')}/v1/charges/{charge_id}/refund",
        timeout=settings.get("payments", "timeout_s"),
    )
    resp.raise_for_status()
    return resp.json()
