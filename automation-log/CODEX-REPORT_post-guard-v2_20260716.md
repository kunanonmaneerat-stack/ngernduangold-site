# Post guard v2 delivery - 16 July 2026 (completed by Cowork)

Codex (gpt-5.6-terra, session 019f6b7f) implemented all code changes from
CODEX-TASK_post-guard-v2_20260716.md, then hit the OpenAI usage limit before it
could run the final verification (limit resets 2026-08-15). Cowork verified and
signed off in its place.

## What changed in tools/post_guard.py (all by Codex, verified by Cowork)
- public_profile_page(): shared browser-header fetch (UA/Accept/th-TH, gzip,
  12s timeout, max 2 attempts).
- TIKTOK: parses __UNIVERSAL_DATA_FOR_REHYDRATION__ (fallback SIGI_STATE),
  walks JSON for desc+createTime pairs; OK when the 25-char manifest caption
  prefix matches, or an item was created on the target date; SCHEDULED-UI for
  13-26 Jul before 19:05; UNKNOWN on any fetch/parse failure (never FAIL).
- THREADS: ledger first, then public profile fetch; OK when the 30-char
  whitespace-normalized caption prefix appears in the page text.
- No changes to YouTube/IG/FB, outputs, exit semantics, or readiness preview.

## Verification (by Cowork, real run 16 Jul ~22:45 ICT)
- python -m py_compile tools/post_guard.py -> OK
- py tools/post_guard.py --check-tomorrow -> exit 0:
  YOUTUBE UNKNOWN (captions.youtube empty for 16 Jul; filled from 17 Jul on)
  INSTAGRAM SCHEDULED-UI
  FACEBOOK UNKNOWN
  TIKTOK UNKNOWN (profile HTML served without rehydration JSON - likely a
  bot-challenge page; acceptable best-effort per spec)
  THREADS OK (post-ledger entry from today's zero-touch video post)

## Notes
- Threads OK is the first public/ledger-confirmed channel in the guard.
- The zero-touch Threads pipeline records the ledger via tools/threads_ledger.py,
  so THREADS should stay verifiable daily.
