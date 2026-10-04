"""Background worker: drains the fulfilment queue."""

import json
import time

import redis

_r = redis.Redis(host="10.0.4.20", port=6379)
QUEUE = "fulfilment"
PROCESSING = "fulfilment:processing"


def handle(job: dict):
    from app.clients import inventory

    inventory.get_stock(job["sku"])


def run_forever():
    while True:
        raw = _r.brpoplpush(QUEUE, PROCESSING, timeout=5)
        if raw is None:
            continue
        job = json.loads(raw)
        handle(job)
        _r.lrem(PROCESSING, 1, raw)
        time.sleep(0.01)
