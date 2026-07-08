# Demo Recording Script (Step 6A)

Record a 60–90s screen capture (e.g. ScreenToGif or OBS on Windows), convert to
GIF **under 10MB**, save as `docs/demo.gif`, and replace the placeholder comment
at the top of README.md with `![Sentinel demo](docs/demo.gif)`.

Beat sheet — keep the dashboard and Slack visible side by side:

| Time | On screen |
|------|-----------|
| 0:00 | Dashboard healthy / empty incident feed; terminal running load generator |
| 0:15 | Run `python -m sandbox.chaos_cli trigger-bug --type db_failure` |
| 0:30 | Alert fires — incident appears in the feed, status flips to triaging |
| 0:55 | Drilldown: ranked suspect commit with diff viewer open **and** the Slack card arriving — the two most impressive moments, keep both clearly in frame |
| 1:20 | Run `resolve-bug --incident <id>` — postmortem renders in the editor workspace |

Verify: the GIF autoplays on GitHub and communicates the full loop without audio.
