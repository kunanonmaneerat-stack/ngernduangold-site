# CODEX TASK - Build YouTube batch2 scheduled-uploader (2026-07-16, ordered by Cowork)

## Context
Repo = Thai personal-finance site "ngernduangold" static generator + social pipeline.
7 rendered Shorts (1080x1920, ~10s, mp4) live in `reels/batch2/` named `20_*.mp4` .. `26_*.mp4`.
They must appear on YouTube channel UCVuqb7l5rJ4Q7PUKSIgsL4w as SCHEDULED Shorts, one per day
2026-07-20 .. 2026-07-26, publish time 19:00 Asia/Bangkok (= 12:00 UTC) each day.
Manual UI upload is the current bottleneck - we want an API uploader so no human file-picking is needed.
Captions/titles source of truth: `.system_control/content_manifest.json` -> items with date 2026-07-20..26,
field `captions.youtube` (already filled), video path in field `reel`.

## HARD RULES
- Do NOT `git push`. Do NOT `git add -A` (only add the specific new files if you commit; committing is optional).
- Do NOT touch `build_site.py`, site content, or any file not listed in Deliverables.
- Do NOT print, log, or copy secret VALUES (tokens/client secrets). Paths and key NAMES are fine.
- Thai text: read/write files as UTF-8 only. Do not re-encode the manifest.
- If something is impossible, write it in the report and stop that part - no risky workarounds.

## Step 1 - Recon (read-only)
Find what Google credentials already exist in this repo/machine setup:
- Locate how `gsc_pull` (Search Console pull used by weekly analytics) authenticates:
  search repo for `gsc` scripts (`tools/`, `pipeline/`, `automation-log/`), look for
  `client_secret*.json`, `credentials*.json`, `token*.json|pickle`, service-account json,
  and env/config references. Determine: OAuth installed-app vs service account.
- NOTE: YouTube upload to a personal channel requires OAuth installed-app flow with scope
  `https://www.googleapis.com/auth/youtube.upload` (a service account will NOT work).
- Record findings (paths + type only, no secret values) in the report.

## Step 2 - Deliverable: tools/yt_upload_batch2.py
Python 3 (`py` launcher on this Windows machine), deps: `google-api-python-client google-auth-oauthlib google-auth-httplib2`
(add a `requirements` comment at top; install with `py -m pip install --user` if missing).
Behavior:
1. `--dry-run` (default) and `--live` modes. Dry-run prints the exact plan (file, title, publishAt UTC, desc first 80 chars) and exits.
2. Reads manifest items 2026-07-20..26. For each:
   - video file = repo-root-relative `reel` path; verify exists.
   - title = first line of `captions.youtube`, strip emojis is NOT needed, but truncate to <=100 chars; ensure it ends with ` #Shorts` (add if missing).
   - description = full `captions.youtube`.
   - publishAt = that date 19:00 +07:00 converted to RFC3339 UTC (`YYYY-MM-DDT12:00:00Z`).
   - request: videos.insert part=snippet,status; snippet {title, description, categoryId "27", defaultLanguage "th"};
     status {privacyStatus "private", publishAt, selfDeclaredMadeForKids false}; resumable upload.
3. Auth: look for OAuth client json (from Step 1 or `secrets/` folder). Token cache -> `secrets/yt_token.json`
   (create `secrets/` if needed - it is gitignored; VERIFY it is gitignored before writing, else write token to `%USERPROFILE%\.ngernduangold\yt_token.json`).
   If no OAuth client json exists anywhere: script must exit with a clear message telling the owner to create an
   OAuth Desktop client in Google Cloud Console (API: YouTube Data API v3) and where to drop the json. Also write that
   instruction into the report (step-by-step, <=8 steps, include console URLs).
4. Quota guard: max 6 uploads per run (each ~1600 units of 10000/day). `--limit N` flag. Print which items remain.
5. Dedup guard: maintain `.system_control/yt_upload_log.json` {date: videoId}; skip any date already logged.
   Also `--check` mode: call channel search/list to confirm none of the 7 titles already exist (best effort; if quota
   or auth missing, note and continue).
6. On each successful upload: print videoId + update manifest item `posted.youtube` = "scheduled (yt-api <videoId>)".
   Save manifest preserving UTF-8 + 2-space indent exactly as it is now.
7. Robust errors: quotaExceeded -> stop gracefully and say resume tomorrow; uploadLimitExceeded -> report;
   network retry x3 with backoff on 5xx.

## Step 3 - Verify
- `py -m py_compile tools/yt_upload_batch2.py` must pass.
- Run `py tools/yt_upload_batch2.py --dry-run` - must print the 7-row plan using real manifest data (auth NOT required for dry-run; do not trigger OAuth in dry-run).
- Do NOT run `--live` yourself. Owner/Cowork will run it (consent screen needs the owner).

## Step 4 - Report
Write `automation-log/CODEX-REPORT_yt-upload_20260716.md` (English or Thai ok):
- Step 1 findings (creds type/paths, whether reusable for YouTube).
- What was built, dry-run output sample (7 rows).
- EXACT next actions for the owner: (a) if OAuth client exists: single command to run + what the consent screen will ask;
  (b) if not: the <=8-step Google Cloud Console instruction, then the command.
- Any caveats (quota math: 6 today + 1 tomorrow, or all 7 if headroom).
