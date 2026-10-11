"""Builds a throwaway git repo for one eval case. Never touches the Sentinel repo."""

import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from eval.config import ALERT_TS

BASES_DIR = Path(__file__).parent / "bases"
CASES_DIR = Path(__file__).parent / "cases"


def load_case(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def all_case_paths(pattern: str = "*.json") -> list[Path]:
    return sorted(CASES_DIR.glob(pattern))


def _git(repo: Path, *args, when: datetime | None = None, author: str = "dev@example.com") -> str:
    env = {**os.environ, "GIT_AUTHOR_EMAIL": author, "GIT_COMMITTER_EMAIL": author}
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = author.split("@")[0]
    if when:
        # git log --since/--until filters on committer date, so both must be set
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when.isoformat()
    out = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return out.stdout.strip()


def _apply(repo: Path, files: dict):
    """Each value is either full file content (str) or a list of [old, new] edits."""
    for rel, change in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(change, str):
            path.write_text(change, encoding="utf-8", newline="\n")
            continue
        text = path.read_text(encoding="utf-8")
        for old, new in change:
            if text.count(old) != 1:
                raise ValueError(
                    f"{rel}: edit target must occur exactly once, found {text.count(old)}: {old!r}"
                )
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8", newline="\n")


def _rmtree(path: str):
    # git marks object files read-only; Windows refuses to delete those without a chmod
    def _chmod_retry(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    shutil.rmtree(path, onerror=_chmod_retry)


APP_ROOT = "/srv/orders"  # deploy path frames carry; repo paths are relative to it


def render_traceback(repo: Path, spec: dict, error: str) -> str:
    """Python-style traceback whose app frames point at real lines of the post-commit repo.

    Frame forms: [repo_file, func, anchor] (line = first line containing anchor after `def func(`, or the
    file's only line containing it for <module>/<genexpr>), [abs_path, line, func, code] for library frames,
    or [text] for a literal line such as "[Previous line repeated 996 more times]".
    """
    out = ["Traceback (most recent call last):"]
    for fr in spec["frames"]:
        if len(fr) == 1:
            out.append(f"  {fr[0]}")
            continue
        if len(fr) == 4:
            path, line, func, code = fr
        else:
            rel, func, anchor = fr
            lines = (repo / rel).read_text(encoding="utf-8").splitlines()
            start = next(
                (i for i, x in enumerate(lines) if re.match(rf"\s*def {re.escape(func)}\(", x)), None
            )
            hits = [i for i, x in enumerate(lines) if anchor in x and (start is None or i >= start)]
            if not hits or (start is None and len(hits) != 1):
                raise ValueError(
                    f"{rel}:{func}: anchor must match {'once' if start is None else ''}: {anchor!r}"
                )
            path, line, code = f"{APP_ROOT}/{rel}", hits[0] + 1, lines[hits[0]].strip()
        out += [f'  File "{path}", line {line}, in {func}', f"    {code}"]
    out.append(spec.get("error", error))
    return "\n".join(out)


@contextmanager
def build(case: dict):
    """Yields (repo_path, alert, label). label gains culprit_hash for the scorer."""
    alert_dt = datetime.fromisoformat(ALERT_TS)
    tmp = tempfile.mkdtemp(prefix="sentinel_eval_")
    repo = Path(tmp)
    try:
        _git(repo, "init", "-q")
        base_dir = BASES_DIR / case["base"]
        for src in base_dir.rglob("*"):
            if src.is_file():
                dest = repo / src.relative_to(base_dir)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(src.read_bytes().replace(b"\r\n", b"\n"))
        _apply(repo, case.get("base_files", {}))
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "initial import", when=alert_dt - timedelta(days=3))

        hashes = []
        for c in case["commits"]:
            _apply(repo, c["files"])
            _git(repo, "add", "-A")
            when = alert_dt - timedelta(minutes=c["minutes_before_alert"])
            _git(repo, "commit", "-q", "-m", c["message"], when=when, author=c["author"])
            hashes.append(_git(repo, "rev-parse", "HEAD")[:7])  # same truncation as git_client

        alert = {
            "source": "mock_sentry",
            "alert_name": case["alert"]["alert_name"],
            "timestamp": ALERT_TS,
            "error_signature": case["alert"]["error_signature"],
        }
        if case.get("traceback"):  # only the traceback condition sends it; run_eval strips it otherwise
            alert["traceback"] = render_traceback(repo, case["traceback"], case["alert"]["error_signature"])
        label = {**case["label"], "culprit_hash": hashes[case["label"]["culprit_index"]]}
        yield str(repo), alert, label
    finally:
        _rmtree(tmp)
