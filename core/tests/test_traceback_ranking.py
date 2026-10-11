# ponytail: traceback context must not move the baseline prompt; overlap must match path segments only
from types import SimpleNamespace as NS
from unittest.mock import patch

from core.services import llm_analyzer
from core.tests.test_rag_ranking import _ALERT, _DIFFS, _GOLDEN_BASELINE_PROMPT

_TB = (
    "Traceback (most recent call last):\n"
    '  File "/srv/orders/app/db.py", line 24, in fetch_all\n'
    "    conn = pool.getconn()\n"
    "psycopg2.pool.PoolError: connection pool exhausted"
)
_FILED = [{**_DIFFS[0], "files": ["config.json", "app/db.py"]}, {**_DIFFS[1], "files": ["README.md"]}]


def _prompt(diffs, alert):
    captured = []

    def fake_chat(messages, **_):
        captured.append(messages[0]["content"])
        return NS(
            stop_reason="tool_use",
            content=[NS(type="tool_use", name="rank_commits", input={"ranked_commits": []})],
        )

    with patch.object(llm_analyzer, "chat", fake_chat):
        llm_analyzer.rank_suspect_commits(diffs, alert)
    return captured[0]


def test_no_traceback_prompt_is_byte_identical_to_baseline():
    assert _prompt(_FILED, _ALERT) == _GOLDEN_BASELINE_PROMPT
    assert _prompt(_FILED, {**_ALERT, "traceback": ""}) == _GOLDEN_BASELINE_PROMPT


def test_traceback_sits_after_alert_and_marks_only_overlapping_commits():
    prompt = _prompt(_FILED, {**_ALERT, "traceback": _TB})
    assert prompt.index("ALERT:") < prompt.index("<traceback>") < prompt.index("RECENT COMMITS:")
    assert prompt.count("Touches files in the stack trace:") == 1
    assert "Subject: config: raise pool size\nTouches files in the stack trace: app/db.py\nDiff:" in prompt


def test_overlap_matches_whole_path_segments():
    tb = 'File "/srv/orders/app/db.py", line 1\nFile "C:\\svc\\app\\cart.py", line 2'
    files = ["app/db.py", "db.py", "pp/db.py", "app/cart.py", "app/orders.py"]
    assert llm_analyzer.files_in_traceback(files, tb) == ["app/db.py", "db.py", "app/cart.py"]
    assert llm_analyzer.files_in_traceback(files, None) == []


def test_long_traceback_keeps_newest_frames():
    tb = "x" * 10_000 + "\nTypeError: newest"
    block = llm_analyzer._traceback_block(tb)
    assert "TypeError: newest" in block and len(block) < llm_analyzer._TRACEBACK_MAX_CHARS + 200


def test_sandbox_app_traceback_matches_its_repo_path():
    from fastapi.testclient import TestClient

    from sandbox.app import main as sandbox_app

    with patch.object(sandbox_app, "_bug", return_value="db_failure"):
        r = TestClient(sandbox_app.app, raise_server_exceptions=False).get("/api/data")
    assert r.status_code == 500 and r.json()["error"].startswith("RuntimeError: OperationalError")
    tb = r.json()["traceback"]
    assert llm_analyzer.files_in_traceback(["sandbox/app/main.py", "core/db.py"], tb) == [
        "sandbox/app/main.py"
    ]
