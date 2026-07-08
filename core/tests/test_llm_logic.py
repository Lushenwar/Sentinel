# ponytail: mocks openrouter.chat so test runs without a live API key
from unittest.mock import patch
from core.services.llm_analyzer import rank_suspect_commits

_DIFFS = [
    {
        "commit_hash": "a1b2c3d",
        "author": "dev@co.com",
        "timestamp": "2026-07-03T11:25:00Z",
        "subject": "chore: inject bug=db_failure",
        "diff": '--- a/sandbox/app/config.json\n+++ b/sandbox/app/config.json\n-{"bug": null}\n+{"bug": "db_failure"}',  # noqa: E501
    }
]
_ALERT = {
    "alert_name": "HTTP_500_Internal_Server_Error",
    "error_signature": "OperationalError: connection refused",
    "timestamp": "2026-07-03T11:29:00Z",
}


def test_rank_returns_empty_for_no_diffs():
    assert rank_suspect_commits([], _ALERT) == []


def test_rank_calls_openrouter_and_returns_sorted():
    fake_response = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "rank_commits",
                                "arguments": (
                                    '{"ranked_commits": [{"commit_hash": "a1b2c3d", '
                                    '"author": "dev@co.com", "timestamp": "2026-07-03T11:25:00Z", '
                                    '"rationale": "Directly set db_failure bug.", "confidence_score": 0.95}]}'
                                ),
                            },
                        }
                    ],
                },
            }
        ],
    }

    with patch("core.services.llm_analyzer.chat", return_value=fake_response):
        result = rank_suspect_commits(_DIFFS, _ALERT)

    assert len(result) == 1
    assert result[0]["confidence_score"] == 0.95


if __name__ == "__main__":
    test_rank_returns_empty_for_no_diffs()
    test_rank_calls_openrouter_and_returns_sorted()
    print("✓ llm_logic tests passed")
