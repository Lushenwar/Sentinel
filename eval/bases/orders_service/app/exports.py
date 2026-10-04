import csv
import os
from datetime import datetime, timezone

from app import settings


def export_orders_csv(orders: list[dict]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    path = os.path.join(settings.get("exports", "dir"), f"orders_{stamp}.csv")
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "status", "total", "created_at"])
        for o in orders:
            writer.writerow([o["id"], o["status"], o["total"], o["created_at"]])
    return path
