# PROJECT HANDOFF — ngernduangold (เงินเดือนสมองทอง)
_Continuity doc. If the main PC dies, clone the repo + read this + redo the machine-local setup below to continue on any machine._
_Last updated by the Cowork agent on 2026-06-25._

## 1. What this project is
A Thai affiliate personal-finance site for salaried workers ("manut ngerndeuan"): credit cards, loans,
debt, savings, insurance, budgeting. Genuinely-useful guides + a 2-question quiz that recommends
products. Monetised via AccessTrade (atth.me) affiliate links (rel=sponsored + sub-id).
Goal funnel: traffic -> engagement -> quiz_start -> recommendation -> affiliate_click -> conversion.
Current bottleneck = quiz_start is tiny, so DISTRIBUTION is the lever (not funnel tweaks).

## 2. Live assets / accounts
- Site (live): https://ngernduangold.com  (apex is canonical; www + *.netlify.app 301 to apex)
- Quiz entry: https://ngernduangold.com/quiz
- Hosting: Netlify, Git-connected to GitHub: https://github.com/kunanonmaneerat-stack/ngernduangold-site
- Analytics: GA4  G-17PPE0M1B8
- Socials (brand): TikTok @ngernduangold, Instagram @ngernduangold, Threads @ngernduangold,
  Facebook Page "Ngern Duang Gold". YouTube/Pinterest = personal accounts only (no brand presence yet).
- Pantip account used for replies: member 9373300

## 3. Repo layout (key files)
- build_site.py ........... static-site generator (self-contained; templates/CSS/JS inline). Output -> site/
- netlify.toml ........... build config (SITE_BASE, 301 redirects, AND a build-ignore rule; see section 6)
- *-infographic.html ..... static infographic pages copied into site/ by build_site.py
- pipeline/ .............. ga4_pull.py, gsc_pull.py, ga4_auth.py, comply_gate.py, _pantip_forum_live.py, _pantip_thread_scrape.py
- automation-log/ ........ run logs + gitignored drafts (_pantip_*, post-ready/, ga4-*.csv). NOT served.
- tiktok-pipeline/ ....... video system: src/00..07 stages, drafts/scripts_clean.json (5 scripts tt-001..005),
                          captions/vid_*.txt (post captions, compliance-passed), fonts/, ready-for-cowork/
- media/clips/*-2026.mp4 . 7 Google-Flow (Veo) footage clips, 720x1280 ~10s, WITH aac audio + a moving watermark
- OPERATING-NOTES.md ..... gotchas / lessons learned. READ IT before local work.
- _hb_build.py, _hb_batch.py  LOCAL, may be untracked: the hybrid-Reel renderer (footage + text + scrim)
- _vidout/ ............... LOCAL render output: reel_*.mp4 finished Reels + _posted.log (which clips were posted)
- secrets/ .............. LOCAL ONLY, gitignored: ga4-token.json etc. NEVER commit / never upload to Drive.

## 4. The 3 scheduled tasks (automations) — NO channel overlap
1. ngernduangold-daily-cycle  @ 09:06 daily — STEP 0 site health-check; pull GA4/GSC; scrape live Pantip (Sinthorn),
   draft + comply-gate + DEDUPE (skip threads member 9373300 already answered) + POST Pantip replies; 1 Threads/day
   (with quiz link); write report. Channels: Pantip + Threads (text).
2. ngernduangold-video-post   @ 18:01 daily — post the next ready _vidout/reel_*.mp4 to TikTok (rotates the 4 clips
   via _vidout/_posted.log so it never repeats), caption from tiktok-pipeline/captions/vid_*.txt. Channel: TikTok (video).
3. ngernduangold-uptime-monitor @ every 6h — load the homepage; if Netlify "paused"/down, alert loudly. No posting.
DEDUPE SAFEGUARDS: Pantip = member-9373300 check; TikTok = _posted.log (debt already logged as posted). The three tasks
own DIFFERENT channels so they cannot double-post the same thing.
Scheduled tasks run only while the Claude desktop app is open; if closed at fire time they run on next launch.

## 5. Video pipeline (how a Reel is made + posted)
- Footage = media/clips/<topic>-2026.mp4 (Veo). KEEP its audio. The watermark is a MOVING sparkle bottom-right ->
  cover it with an opaque bottom scrim (~bottom 30-38%) which doubles as the caption band. Do NOT try delogo.
- On-screen text from tiktok-pipeline/drafts/scripts_clean.json: use topic_th for the HOOK (the onscreen fields are
  TRUNCATED mid-word), the last scene onscreen for the CTA, and disclosure. Only 5 scripts exist.
- Render: python3 _hb_batch.py  (ASCII-only; reads Thai from JSON/txt; outputs to _vidout). Verify a frame, then post.
- 4 clips ready: debt, credit-bureau, emergency-fund, first-card. NOT yet scripted: refinance, salary-budgeting, title-loan.
- Posting verified on TikTok Studio: file_upload to the hidden input, TYPE the caption (NOT clipboard - it gets overwritten),
  then click the "Post" button. New TikToks show "under review" + temporarily private; that is normal.

## 6. Netlify build-minutes fix (keep it)
Every push triggers a build; free tier = 300 build min/mo. Automation/pipeline commits burned the quota and the site got
PAUSED. netlify.toml now has:
  ignore = "git diff --quiet HEAD^ HEAD -- . ':(exclude)automation-log' ':(exclude)pipeline' ':(exclude)tiktok-pipeline'"
=> builds are skipped when a commit only touches those folders. Keep it. Check Netlify > Usage if the site pauses again.

## 7. HOW TO CONTINUE ON A NEW MACHINE
1. Install: git, Python 3 (pip install pillow numpy google-analytics-data google-auth playwright; playwright install chromium),
   ffmpeg on PATH, the Claude desktop (Cowork) app.
2. git clone https://github.com/kunanonmaneerat-stack/ngernduangold-site  (the real code backup).
3. Re-auth tokens (machine-local, NOT in git): python3 pipeline\ga4_auth.py  and tick BOTH Analytics + Search Console
   -> creates secrets/ga4-token.json.
4. Log into Chrome (+ Claude-in-Chrome extension) for: TikTok, Instagram, Threads, Facebook Page, Pantip (member 9373300).
5. Copy the local render scripts if missing (_hb_build.py, _hb_batch.py); re-render: python3 _hb_batch.py.
   (Best: commit them so they travel with the repo.)
6. Re-create the 3 scheduled tasks (section 4) in Cowork; click "Run now" once on each to pre-approve tools.
7. Read OPERATING-NOTES.md for all the gotchas.

## 8. Iron rules (still in force)
- Byte-safe Thai: never Write/Edit-tool a file with Thai/emoji literals (corruption) -> read Thai from UTF-8 data files
  or use \u escapes; ASCII-only scripts. Verify Thai via the Read tool, not the cp874 console.
- Native exes (python/ffmpeg) fail on paths >260 chars -> work in short repo paths (e.g. repo\_vidout).
- No PII / tokens / revenue in chat, logs, drafts, or the PUBLIC repo. Secrets stay in secrets/ (gitignored).
- Claude never git commit/push; the OWNER commits. Never git add -A.
- Compliance: rel=sponsored + sub-id; never invent rates/fees/reviews; keep disclaimers; comply_gate must pass; OIC/BoT/PDPA.
- Don't change article content / canonical / SITE_BASE casually.

## 9. Status (2026-06-25)
DONE: domain migration + canonical; Netlify build-ignore fix; GSC token scope fixed; 4 Pantip replies + 1 Threads posted;
4 hybrid Reels rendered (sound + no watermark); 1 TikTok Reel (debt) posted; 3 scheduled tasks live; OPERATING-NOTES + this doc.
PENDING / NEXT: add IG Reels + FB to the video schedule; write scripts for refinance/salary/title-loan; confirm Netlify usage;
add a GSC property for ngernduangold.com (currently the netlify.app property; queries=0); KPI to watch = quiz_start.
