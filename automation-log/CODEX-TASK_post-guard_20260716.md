# CODEX TASK - Build daily posting controller/verifier (2026-07-16, ordered by Cowork)

## Goal
One deterministic script that "controls the posting plan": every evening it verifies today's
scheduled posts actually went live on each channel, auto-fixes what is fixable, and reports.
It becomes the nightly source of truth. A Cowork scheduled task will run it daily at 19:25.

## Plan context (source of truth files)
- `.system_control/content_manifest.json` - items 2026-07-13..26, per-channel captions + posted fields.
- `.system_control/yt_upload_log.json` - {date: videoId} for API-scheduled YouTube (20..25 now, 26 tomorrow).
- `secrets/yt_token.json` + `secrets/ga4-client.json` - working YouTube OAuth (upload scope).
- IG automation logs (when it runs): `automation-log/ig-reels/log-<date>.md`, `automation-log/ig-reels/published.json` (check actual paths).
- Threads/FB text ledger: `automation-log/post-ledger.jsonl`.
- Channel plan: TikTok+FB+IG+YT daily 19:00 Asia/Bangkok video; Threads daily 19:00 via Cowork one-time tasks (16..26).

## HARD RULES
- No git push / no `git add -A`. Deliverables only.
- Never print secret values. Never write secrets to files.
- Read-only against all channels EXCEPT the explicitly allowed fix actions below.
- Timezone: Asia/Bangkok for all date logic.

## Deliverable 1: tools/post_guard.py  (py launcher, stdlib + existing installed google libs)
Modes: default = today's evening check; `--date YYYY-MM-DD` override; `--check-tomorrow` add readiness preview; `--json` machine output.
Per-channel checks for target date D:
1. YOUTUBE (authoritative, API):
   - If D in yt_upload_log: videos.list(id) -> check status.privacyStatus + publishAt; after 19:05 local it should be public -> OK/FAIL(reason).
   - Else (13..19 were UI-scheduled): search().list is quota-costly; instead channels.list(mine)->uploads playlist, playlistItems most recent 10, match title prefix from manifest captions.youtube first line -> OK/UNKNOWN.
   - Auto-fix allowed: if D >= 2026-07-26 and D not in yt_upload_log and quota likely available -> run `py tools/yt_upload_batch2.py --live --limit 1` via subprocess and re-verify (this covers clip 26 and any future backfill).
2. INSTAGRAM: no local Meta token by design. Check automation artifacts only: published.json / log-<D>.md exists mentioning D -> OK; if IG workflow secrets absent (no way to run) -> BLOCKED(token) status, not FAIL. UI-scheduled dates 13..19 -> SCHEDULED-UI (info).
3. FACEBOOK: same approach: fb-feed/schedule_fb_batch2 logs if any (search automation-log for fb feed run logs pattern; note what you find); 20 = manual-scheduled OK(info); 21..26 -> BLOCKED(token) until secrets exist.
4. TIKTOK: best-effort HTTP GET https://www.tiktok.com/@ngernduangold (urllib, UA header, timeout 10s). If today's manifest tiktok caption first 25 chars appear in HTML -> OK; blocked/unparseable -> UNKNOWN (never FAIL).
5. THREADS: read post-ledger.jsonl for a threads entry dated D -> OK; else UNKNOWN (video tasks do not ledger) - include hint "ask Cowork/Threads profile".
Output:
- Write `automation-log/post-guard/status-<D>.md` - Thai table: ช่อง | สถานะ (OK/UNKNOWN/BLOCKED/FAIL) | หลักฐาน | การแก้ที่ทำไป
- Also append one JSON line to `automation-log/post-guard/history.jsonl`.
- Exit code: 0 if no FAIL, 2 if any FAIL (UNKNOWN/BLOCKED do not fail the run).
- `--check-tomorrow`: verify tomorrow has: reel file exists + captions present + (if 20..26) yt log or plan + note TikTok schedule horizon (23..26 need manual UI scheduling once within 10-day window; today 16th all are within window - remind once).
## Deliverable 2: automation-log/CODEX-REPORT_post-guard_20260716.md
What was built, how each channel is verified, sample run output for today (RUN IT for real: today=2026-07-16, after building; YT check should find UI-scheduled short for 16th or UNKNOWN pre-19:00 - that is fine, show real output), and the daily-ops meaning of each status.

## Verify
- `py -m py_compile tools/post_guard.py` (locate a working python launcher; normal shells have `py`).
- Run once for real: `py tools/post_guard.py --check-tomorrow` and include its real output in the report.
- YT API read calls are fine (cheap). No uploads unless the explicit clip-26 fix path triggers naturally (it should NOT today; 26 is future).
