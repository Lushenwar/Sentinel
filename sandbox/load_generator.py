"""
Usage: python -m sandbox.load_generator [--tps 5] [--duration 30]
Drives traffic to the sandbox app; auto-fires an alert to core when error rate spikes.
"""
import asyncio, httpx, time, argparse
from datetime import datetime, timezone

APP = "http://localhost:8001"
CORE = "http://localhost:8000/alert"
ALERT_THRESHOLD_PCT = 20
ALERT_MIN_ERRORS = 5

async def run(tps: int, duration: int):
    counts = {"ok": 0, "err": 0}
    alerted = False
    deadline = time.monotonic() + duration
    interval = 1.0 / tps

    async with httpx.AsyncClient(timeout=2.0) as client:
        while time.monotonic() < deadline:
            t0 = time.monotonic()
            try:
                r = await client.get(f"{APP}/api/data")
                counts["err" if r.status_code >= 500 else "ok"] += 1
            except Exception:
                counts["err"] += 1

            total = counts["ok"] + counts["err"]
            err_pct = counts["err"] / total * 100 if total else 0
            print(f"\r[load] ok={counts['ok']} err={counts['err']} rate={err_pct:.1f}%", end="", flush=True)

            if not alerted and counts["err"] >= ALERT_MIN_ERRORS and err_pct > ALERT_THRESHOLD_PCT:
                alerted = True
                alert = {
                    "source": "load_generator",
                    "alert_name": "HTTP_500_Internal_Server_Error",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error_signature": "Error rate spike detected",
                    "error_rate_pct": round(err_pct, 1),
                }
                try:
                    await client.post(CORE, json=alert, timeout=5.0)
                    print(f"\n[load] alert fired → sentinel core")
                except Exception as e:
                    print(f"\n[load] core unreachable: {e}")

            await asyncio.sleep(max(0.0, interval - (time.monotonic() - t0)))

    print(f"\n[load] done — ok={counts['ok']} err={counts['err']}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--tps", type=int, default=5)
    p.add_argument("--duration", type=int, default=30)
    args = p.parse_args()
    asyncio.run(run(args.tps, args.duration))
