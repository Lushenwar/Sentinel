from app import settings


def page_bounds(page: int, page_size: int) -> tuple[int, int]:
    """page is 1-based; returns a half-open [start, end) slice."""
    start = (page - 1) * page_size
    return start, start + page_size


def clamp_page_size(requested: int | None) -> int:
    if requested is None:
        return settings.get("api", "page_size")
    return max(1, min(requested, settings.get("api", "max_page_size")))


def paginate(items: list, page: int, page_size: int) -> dict:
    start, end = page_bounds(page, page_size)
    return {"items": items[start:end], "page": page, "has_more": end < len(items)}
