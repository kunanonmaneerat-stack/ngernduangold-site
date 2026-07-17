# CODEX TASK: Harden tools/post_guard.py public verification (v2)

Date: 2026-07-16 (late evening). You are Codex running inside the repo at
C:\Users\nL_ku\ngernduangold-site (Windows). ASCII-only file on purpose.

## Context
tools/post_guard.py (built earlier today) verifies daily 19:00 Asia/Bangkok posts.
Current TikTok check = naive HTML substring, usually UNKNOWN. Threads check = local
ledger only. Upgrade BOTH to real public evidence. Everything else stays as is.

New facts you must encode:
- TikTok clips are UI-scheduled through 2026-07-26 inclusive (13..26).
- Threads: from 2026-07-16 onward, posts may be recorded in
  automation-log/post-ledger.jsonl with source "cowork-zero-touch-*" or posted via
  one-time tasks; public profile check is now the authoritative fallback.

## Deliverables
1) Edit tools/post_guard.py only. Keep CLI, outputs, exit-code semantics identical.
   a) TIKTOK check upgrade:
      - GET https://www.tiktok.com/@ngernduangold with realistic browser headers
        (User-Agent Chrome on Windows, Accept, Accept-Language th-TH, gzip ok).
      - Parse embedded JSON: look for script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"
        (fallback: window['SIGI_STATE'] JSON). Extract item descriptions and
        createTime values wherever they appear (defensive: walk the JSON for dicts
        having both "desc" and "createTime").
      - Evidence rule: normalize whitespace; if the first 25 chars of the manifest
        tiktok caption appear in any desc -> OK. Else if any item createTime falls on
        the target date (Asia/Bangkok) -> OK with evidence "an item was published on
        the target date (caption mismatch)".
      - If target date <= 2026-07-26 and now < 19:05 local -> status SCHEDULED-UI
        (skip fetch). If fetch/parse fails -> UNKNOWN (never FAIL, never crash).
      - Timeout 12s. No retries storms (max 2 attempts).
   b) THREADS check upgrade:
      - Keep ledger check first (OK if entry for date).
      - Else GET https://www.threads.com/@ngernduangold (same header style).
        Normalize page text (strip tags roughly, collapse whitespace) and search for
        the first 30 chars (whitespace-normalized) of manifest captions.threads.
        Found -> OK "caption prefix found on public profile". Not found or blocked ->
        UNKNOWN (never FAIL).
   c) Do not touch YouTube/IG/FB logic, outputs, readiness preview, or recovery.
2) Validate: python -m py_compile tools/post_guard.py must pass.
3) REAL RUN (mandatory, read-only): python tools/post_guard.py --check-tomorrow
   Include its full stdout in the report. Today 2026-07-16 Threads should come out OK
   (ledger entry exists). TikTok tonight may be OK or UNKNOWN depending on parse.
4) Write automation-log/CODEX-REPORT_post-guard-v2_20260716.md (English ok):
   what changed, the real run output, and any caveats.

## HARD RULES (same as before, strictly)
- NEVER run: git push, git add -A, git commit of unrelated files. You may leave all
  changes uncommitted.
- Do not print, echo, or copy any secret VALUES. Names/paths are fine.
- Do not touch build_site.py, site content, pipeline/, tiktok-pipeline/, Pantip
  anything, or scheduled task folders.
- UTF-8 only when writing files. post_guard.py already sets utf-8 stdout.
- If something is impossible, stop and write the report explaining why.
- The python launcher on this machine for you: use `python` (py may be absent in
  your shell). Network access is allowed for the two public GETs above.
