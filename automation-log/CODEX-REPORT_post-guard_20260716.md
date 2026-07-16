# Post guard delivery — 16 July 2026

Built `tools/post_guard.py`, a deterministic nightly verifier for the daily 19:00 Asia/Bangkok posting plan. It writes a human-readable status table to `automation-log/post-guard/status-YYYY-MM-DD.md` and appends a machine-readable run record to `automation-log/post-guard/history.jsonl`.

## Verification rules

| Channel | Verification performed | Safe recovery/action |
|---|---|---|
| YouTube | If `.system_control/yt_upload_log.json` has the date, calls `videos.list` and, after 19:05 local time, requires `privacyStatus=public`. Legacy UI-scheduled dates use `channels.list(mine=True)` plus the 10 most recent upload-playlist entries and the manifest YouTube title prefix. | For 2026-07-26 onward only, an unlogged clip can run `tools/yt_upload_batch2.py --live --limit 1`, then is rechecked. The guard skips this if the cached token would need rewriting. |
| Instagram | Reads only `automation-log/ig-reels/published.json` and `log-YYYY-MM-DD.*` artifacts. Dates 13-19 July are explicitly reported as `SCHEDULED-UI`. | No post is sent. Missing configured IG workflow credentials produce `BLOCKED`, not `FAIL`. |
| Facebook | Searches only explicitly named FB schedule/feed/publish run logs; 20 July is recorded as the known manual schedule. | Dates 21-26 are `BLOCKED` without the configured FB scheduler environment. |
| TikTok | Best-effort public profile GET to `https://www.tiktok.com/@ngernduangold` with a 10-second timeout, looking for the first 25 caption characters. | Never fails the run; blocked or unparseable responses are `UNKNOWN`. |
| Threads | Looks for a `threads` entry containing the target date in `automation-log/post-ledger.jsonl`. | No post is sent; missing evidence is `UNKNOWN` with a Cowork/Threads-profile hint. |

The script supports the default Bangkok-date check, `--date YYYY-MM-DD`, `--check-tomorrow`, and a single-JSON-object `--json` stdout mode. `UNKNOWN`, `BLOCKED`, and `SCHEDULED-UI` do not make the run fail; only a definite `FAIL` returns exit code 2.

## Validation and real run

The Windows `py` launcher is not installed in this environment, so the available `python` launcher was used:

```text
python -m py_compile tools/post_guard.py
python tools/post_guard.py --check-tomorrow
```

The second command was run for real on 2026-07-16 after 21:00 Asia/Bangkok. Its output was:

```text
Post guard 2026-07-16 (Asia/Bangkok):
- YOUTUBE: UNKNOWN — No yt_upload_log entry and manifest captions.youtube has no first-line title to match.
- INSTAGRAM: SCHEDULED-UI — UI-scheduled date (13-19 Jul); no local IG publish artifact yet.
- FACEBOOK: UNKNOWN — scanned 1 FB/feed-named log(s); none mention 2026-07-16
- TIKTOK: UNKNOWN — Public profile GET was unavailable/unparseable: URLError
- THREADS: UNKNOWN — No Threads ledger entry dated 2026-07-16 (video tasks do not ledger).
Report: automation-log/post-guard/status-2026-07-16.md
```

It exited 0: there was no definite failed post. The tomorrow preview found the 17 July reel, but recorded missing Facebook, YouTube, and Threads captions. It also gave one consolidated reminder that the 23-26 July TikTok manual UI dates are now within the 10-day scheduling window.

## Daily operations meaning

- `OK` — direct API, public-page, or local-ledger evidence supports the plan.
- `SCHEDULED-UI` — a known UI schedule exists but has no local publication proof yet; verify in that channel's UI.
- `UNKNOWN` — the guard could not obtain conclusive read-only evidence; investigate, but the verifier did not establish a missed post.
- `BLOCKED` — local credentials/configuration needed for a safe check are unavailable; no posting attempt was made.
- `FAIL` — a check established a real problem (for example, an API-logged YouTube video is still non-public after 19:05); the process exits 2.
