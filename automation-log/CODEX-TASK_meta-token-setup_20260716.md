# CODEX TASK - Build interactive Meta token setup helper (2026-07-16, ordered by Cowork)

## Goal
The owner must provision Meta (FB/IG) credentials as GitHub Actions secrets so two existing
automations start firing: IG Reels publisher (needs IG_ACCESS_TOKEN + IG_USER_ID) and the FB
batch2 scheduler (needs FB_PAGE_ID + FB_PAGE_TOKEN; auto-fires when FB_PAGE_TOKEN appears).
Manual runbook takes ~30 min. Build a single interactive script that shrinks the owner's job to:
paste 3 values into the terminal, done. SECRET VALUES MUST NEVER leave the script's runtime
(no files in repo, no stdout echo of values, no logs) except being sent to Meta/GitHub APIs.

## HARD RULES
- No `git push`, no `git add -A`. Only deliverable files below.
- NEVER print/echo/log secret values (tokens, app secret). Print only key NAMES + validation results.
- Do not store secrets in any file inside the repo. In-memory only.
- If GitHub CLI (`gh`) is unavailable or not authenticated, fall back gracefully (see step 4).
- UTF-8 safe output (Thai text allowed in prompts/messages).

## Known public constants (verified by Cowork, safe to hardcode as defaults)
- FB_PAGE_ID = 583765282304956 (page "เงินเดือนสมองทอง")
- IG_USER_ID = 17841439942473239 (@ngernduangold IG business account)
- GitHub repo: kunanonmaneerat-stack/ngernduangold-site
- Graph API version: v22.0 (follow repo convention from RUNBOOK_ig-reels-api_20260711.md)

## Deliverable: tools/meta_token_setup.py
Interactive console script (stdlib only preferred: urllib.request + json + getpass; no heavy deps). Flow:
1. Intro (Thai): explain it will ask for 3 pastes from Graph API Explorer / app dashboard and
   never displays them back.
2. Prompt via getpass (hidden input):
   a. SHORT_LIVED_USER_TOKEN (from Graph API Explorer "Generate Access Token" with permissions:
      instagram_content_publish, instagram_basic, pages_show_list, pages_read_engagement, pages_manage_posts)
   b. FB_APP_ID (public-ish, normal input ok)
   c. FB_APP_SECRET (getpass)
3. Steps, each with clear Thai progress lines (no secret values):
   a. Validate short token: GET /v22.0/me?fields=id,name -> print name only.
   b. Exchange long-lived user token: GET /v22.0/oauth/access_token?grant_type=fb_exchange_token&client_id=...&client_secret=...&fb_exchange_token=...
   c. GET /v22.0/me/accounts?fields=id,name,access_token (with long-lived token) -> locate page id 583765282304956
      -> capture its page access_token (this is FB_PAGE_TOKEN, long-lived automatically).
      If page not found: list page names+ids found (names/ids ok to print) and abort with guidance.
   d. Verify IG link: GET /v22.0/583765282304956?fields=instagram_business_account -> expect 17841439942473239;
      if different, use the returned id (print it - it is a public id) and continue.
   e. Sanity check IG token: GET /v22.0/<ig-user-id>?fields=id,username with the long-lived user token -> print username.
4. Set GitHub secrets (repo kunanonmaneerat-stack/ngernduangold-site) for:
   IG_ACCESS_TOKEN=<long-lived user token>, IG_USER_ID, FB_PAGE_ID, FB_PAGE_TOKEN=<page token>,
   FB_APP_ID, FB_APP_SECRET  (the last two enable the existing auto-refresh workflow ig-token-check).
   Method A (preferred): `gh secret set NAME --repo kunanonmaneerat-stack/ngernduangold-site --body -` piping the
   value via stdin (subprocess, never shell string interpolation). Detect gh presence + `gh auth status` first.
   Method B (fallback if gh missing/unauthed): open https://github.com/kunanonmaneerat-stack/ngernduangold-site/settings/secrets/actions
   in the default browser (webbrowser module), then loop: for each secret NAME print the name and copy the VALUE
   to the Windows clipboard one at a time (use `clip` via subprocess stdin), waiting for Enter between each,
   so the owner just pastes into the GitHub UI. Clear clipboard at the end (send empty string to clip).
5. Final verification (print PASS/FAIL table, names only): re-list which secrets were set via
   `gh secret list --repo ...` when Method A; otherwise remind owner to check the UI list.
6. Exit summary (Thai): which automations will now fire on their own (ig-reels daily 20:00; fb-feed daily 15:00
   triggers schedule_fb_batch2.py automatically) and that nothing else is needed.

## Verify (you must run)
- `py -m py_compile tools/meta_token_setup.py` (find a working Python launcher; on this machine `py` exists
  in normal shells - if your sandbox PATH lacks it, try `C:\Windows\py.exe` or locate python.exe under
  %LOCALAPPDATA%\Python; if truly unavailable, note it).
- Do NOT run the interactive flow yourself. No network calls in your run.

## Report: automation-log/CODEX-REPORT_meta-token-setup_20260716.md
- What was built, how secrets are protected (in-memory, hidden input, clipboard cleared).
- Exact owner run command: `py tools\meta_token_setup.py`
- The 3 things the owner pastes and exactly where each comes from (Explorer URL + app dashboard URL).
- Fallback behavior when gh CLI is absent.
