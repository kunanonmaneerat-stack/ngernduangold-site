# Operating notes / gotchas (lessons learned) — ngernduangold ops

Read this before doing local execution or video work in this repo. These are real failure
modes hit in production; each line is a mistake already paid for once.

## Tool-call / session reliability
- Emit every tool call in the exact function-call format. A malformed call = the turn ends
  with nothing executed ("stall"). If a turn stalls, the owner types "continue" and the step
  is retried. This is a generation-level glitch, not the user's machine — never blame their setup.
- Prefer ONE big batched operation over many small round-trips. Fewer turns = fewer stalls.

## Windows / paths
- Native exes (python.exe, ffmpeg.exe) CANNOT open paths longer than ~260 chars. The Cowork
  outputs sandbox path is >260 and silently fails ("no output" / "can't open file").
  -> Do all render/ffmpeg work in a SHORT repo path (e.g. C:\Users\nL_ku\ngernduangold-site\_vidout).
     Copy results out with PowerShell Copy-Item (long-path aware) only at the end.
- New PowerShell windows start at the home dir. Always cd into the repo first.
- Console is cp874: Thai shows as mojibake in the terminal. NEVER judge Thai by console echo —
  verify by reading the file back as UTF-8 (Read tool) or writing a UTF-8 file and reading it.

## Byte-safe Thai (critical)
- NEVER put Thai / emoji literals in a file written via the Write/Edit tool — they get corrupted.
- Put Thai ONLY in data files (read at runtime with open(..., encoding="utf-8")), or as \u escapes
  in ASCII source. Scripts that process Thai must be ASCII-only and read the Thai from JSON/txt.

## Netlify (site stability)
- Site is Git-connected; every push to main triggers a build. Free tier = 300 build min/mo.
  Automation/pipeline commits used to trigger builds and exhausted the quota -> site PAUSED.
- Fixed: netlify.toml has an ignore rule that skips builds when a commit only touches
  automation-log/ , pipeline/ , tiktok-pipeline/ . Keep it. Confirm Usage on the Netlify dash.
- If the site shows "Site not available / paused", DO NOT drive traffic to it. The daily cycle
  has a STEP 0 health check; the uptime-monitor task pings every 6h.

## Video pipeline (Reels / TikTok)
- media/clips/*-2026.mp4 = Google Flow (Veo) footage: 720x1280, ~10s, HAS aac stereo audio,
  and a MOVING sparkle watermark in the bottom-right (drifts, so static delogo won't remove it).
  -> Cover it with an opaque bottom scrim (~bottom 30-38%) which doubles as the caption band.
  -> Keep the footage audio (don't pass ffmpeg -an); map 0:a:0?. Veo audio = free sound.
- tiktok-pipeline/src/07_render.py = clean kinetic-text on navy gradient (NO footage, NO watermark).
- tiktok-pipeline/drafts/scripts_clean.json: use topic_th for the full on-screen HOOK
  (the onscreen fields are TRUNCATED mid-word). Use the last scene onscreen for the CTA, and the
  disclosure field. Only 5 scripts exist (tt-001..tt-005; tt-005=/quiz), so refinance /
  salary-budgeting / title-loan footage has NO matching script yet.
- Build hybrid clips with _hb_batch.py (footage + overlay + scrim, keeps audio). Render to _vidout.
- Captions for the post body live in tiktok-pipeline/captions/vid_*.txt (compliance-passed).

## Posting
- Pantip reply editor (CKEditor): click the editor CONTENT AREA BY COORDINATE (~center) to focus —
  clicking the textarea by ref does NOT focus it. Char counter may read 0 + show a fill-text
  notice even on SUCCESS; verify by reloading the thread and finding your opening line.
- Threads: after typing, the link-preview card loads and shifts the Post button UP — re-aim.
- Trending audio is a MOBILE-app feature; desktop web upload can't pick trending sounds.
- Owner commits/pushes git; Claude never commits. No PII/tokens/revenue in the public repo.
