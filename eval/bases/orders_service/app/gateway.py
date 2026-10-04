"""Edge handler: runs a request handler under the upstream deadline."""

import concurrent.futures

from app import settings

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=32)


def run_with_deadline(handler, *args, **kwargs) -> dict:
    future = _executor.submit(handler, *args, **kwargs)
    try:
        return future.result(timeout=settings.get("gateway", "upstream_timeout_s"))
    except concurrent.futures.TimeoutError:
        return {"status": 504, "body": {"error": "upstream timeout"}}
