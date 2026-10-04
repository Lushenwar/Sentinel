import httpx

from app import settings
from app.cache import TTLCache

_stock_cache = TTLCache(
    ttl_s=settings.get("cache", "ttl_s"), max_entries=settings.get("cache", "max_entries")
)


def get_stock(sku: str) -> int:
    cached = _stock_cache.get(sku)
    if cached is not None:
        return cached
    resp = httpx.get(
        f"{settings.get('inventory', 'base_url')}/v2/stock/{sku}",
        timeout=settings.get("inventory", "timeout_s"),
    )
    resp.raise_for_status()
    qty = resp.json()["available"]
    _stock_cache.set(sku, qty)
    return qty


def get_stock_many(skus: list[str]) -> dict[str, int]:
    return {sku: get_stock(sku) for sku in skus}
