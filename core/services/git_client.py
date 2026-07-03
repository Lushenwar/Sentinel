import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

def get_recent_diffs(repo_path: str, alert_ts: str, window_minutes: int = 60) -> list[dict]:
    """Return commits with diffs in [alert_ts - window_minutes, alert_ts]."""
    alert_dt = datetime.fromisoformat(alert_ts.replace("Z", "+00:00"))
    since = (alert_dt - timedelta(minutes=window_minutes)).isoformat()
    until = alert_dt.isoformat()

    log = subprocess.run(
        ["git", "log", "--format=%H|%ae|%aI|%s", f"--since={since}", f"--until={until}"],
        cwd=repo_path, capture_output=True, text=True,
    )
    if log.returncode != 0 or not log.stdout.strip():
        return []

    commits = []
    for line in log.stdout.strip().splitlines():
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue
        full_hash, author, ts, subject = parts

        diff = subprocess.run(
            ["git", "show", "--stat", "--patch", full_hash],
            cwd=repo_path, capture_output=True, text=True,
        )
        commits.append({
            "commit_hash": full_hash[:7],
            "full_hash": full_hash,
            "author": author,
            "timestamp": ts,
            "subject": subject,
            "diff": diff.stdout[:3000],  # ponytail: truncated for LLM context; raise if diffs are large
        })

    return commits
