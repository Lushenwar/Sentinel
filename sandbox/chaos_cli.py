"""
Usage (from Sentinel/ root):
  python -m sandbox.chaos_cli trigger-bug [--type db_failure|memory_leak|null_pointer]
  python -m sandbox.chaos_cli resolve-bug
  python -m sandbox.chaos_cli status
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import click
import httpx

from sandbox.alert_signing import signed

REPO_ROOT = Path(__file__).parent.parent
CONFIG = REPO_ROOT / "sandbox" / "app" / "config.json"
CORE_ALERT = "http://localhost:8000/alert"
APP = "http://localhost:8001"
# endpoint that raises for each bug; memory_leak degrades without raising, so it has none
_PROBES = {"db_failure": ("GET", "/api/data"), "null_pointer": ("POST", "/api/process")}

_ERROR_SIGS = {
    "db_failure": "OperationalError: connection to server at '127.0.0.1' failed: Connection refused",
    "memory_leak": "MemoryError: unable to allocate memory for request buffer",
    "null_pointer": "'NoneType' object has no attribute 'encode'",
}


def _write_config_and_commit(bug: str | None):
    cfg = json.loads(CONFIG.read_text())
    cfg["bug"] = bug
    CONFIG.write_text(json.dumps(cfg, indent=2) + "\n")
    msg = f"chore: {'inject bug=' + bug if bug else 'resolve bug'} [{datetime.now(timezone.utc).isoformat()}]"
    subprocess.run(["git", "add", str(CONFIG)], cwd=REPO_ROOT, check=True)
    subprocess.run(["git", "commit", "-m", msg], cwd=REPO_ROOT, check=True)


def _probe_traceback(bug_type: str) -> str | None:
    """Hit the sandbox app once so the alert carries the real stack trace, as Sentry would."""
    if bug_type not in _PROBES:
        return None
    method, path = _PROBES[bug_type]
    try:
        r = httpx.request(method, APP + path, json={} if method == "POST" else None, timeout=3.0)
        return r.json().get("traceback") if r.status_code >= 500 else None
    except (httpx.HTTPError, ValueError):
        return None


@click.group()
def cli():
    pass


@cli.command("trigger-bug")
@click.option(
    "--type", "bug_type", default="db_failure", type=click.Choice(list(_ERROR_SIGS)), show_default=True
)
def trigger_bug(bug_type: str):
    _write_config_and_commit(bug_type)
    click.echo(f"[chaos] injected: {bug_type}")

    alert = {
        "source": "mock_sentry",
        "alert_name": "HTTP_500_Internal_Server_Error",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error_signature": _ERROR_SIGS[bug_type],
        "bug_type": bug_type,
    }
    tb = _probe_traceback(bug_type)
    if tb:
        alert["traceback"] = tb
    click.echo(f"[chaos] traceback: {'captured from sandbox app' if tb else 'none (app not running?)'}")
    try:
        body, headers = signed(alert)
        r = httpx.post(CORE_ALERT, content=body, headers=headers, timeout=5.0)
        data = r.json()
        click.echo(f"[chaos] incident created: {data['incident_id']} (status={data['status']})")
    except Exception as e:
        click.echo(f"[chaos] core unreachable ({e}) -- alert not forwarded")


@cli.command("resolve-bug")
@click.option(
    "--incident", "incident_id", default=None, help="Incident ID to resolve + generate postmortem for"
)
def resolve_bug(incident_id: str | None):
    _write_config_and_commit(None)
    click.echo("[chaos] bug resolved")

    if incident_id:
        try:
            r = httpx.post(f"http://localhost:8000/incidents/{incident_id}/resolve", timeout=5.0)
            click.echo(f"[chaos] postmortem requested for {incident_id} (status={r.json()['status']})")
        except Exception as e:
            click.echo(f"[chaos] core unreachable ({e}) -- resolve not forwarded")


@cli.command("status")
def status():
    cfg = json.loads(CONFIG.read_text())
    click.echo(f"[chaos] active bug: {cfg.get('bug') or 'none'}")


if __name__ == "__main__":
    cli()
