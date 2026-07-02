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

## 2026-06-26 lessons (dual-system + posting safety)
- TWO automation systems coexist: the established Claude Code / Cowork tasks under C:\Users\nL_ku\Claude\Scheduled\
  (social-ops-daily etc.) AND any new Cowork tasks. ALWAYS list scheduled-tasks before adding a poster - do not duplicate.
- NO-BOT-POST / shadowban policy: bot-posting (Postiz, Threads 8/day) was deliberately disabled. Manual / low-freq / no-link only.
- Pantip: brand account = member 9373300 (personal 8912721 = wrong; social-ops will skip and fail-closed).
- New-domain Chrome-MCP navigation pops an Allow prompt that may be denied; do not retry a denied permission repeatedly.
- AccessTrade Sub ID = utm_source + utm_medium (NOT utm_content). Conversion-level Sub ID report is empty until >=1 conversion.
## 2026-06-26 Pantip posting mechanics (hard-won; for automation + future sessions)
- DELETE does not exist for Pantip comments. Own comment only exposes EDIT ("แก้ไข") + report.
  To fix an accidental duplicate: open EDIT on the extra copy and shrink it to a 1-line note
  (e.g. "ขออภัยค่ะ คอมเมนต์ซ้ำ ข้อความเต็มอยู่ด้านบนนะคะ"). Keep the lower comment-id (posted first).
- CLEAR the Lexical/edit editor with TRUSTED keys via the Chrome extension computer tool:
  computer key "ctrl+a" then key "Delete". JS execCommand('delete') AND sel.modify loops do NOT
  clear Pantip's editor (len stays unchanged). Confirmed: ctrl+a + Delete -> len 0.
- SUBMIT/SAVE only via a TRUSTED single ref-click: find -> computer left_click {ref}. 
  NEVER submit with JS element.click() -> it double-fires and DOUBLE-POSTS (this caused the #3 dup).
- ALWAYS verify after posting: count a unique phrase via body.innerText.split(phrase).length-1 AND
  list the closest [id^="comment-"] box ids. occurrences must == 1. Two distinct comment-ids = dup.
- RE-SKIM the thread before replying. 2026-06-26 thread 44140019 (car-for-cash) was an ACTIVE SCAM:
  a fake broker "ป๋าสูทเหลือง" harvested the OP's real name+phone. Our anti-scam PSA (comment 119498960)
  was the correct protective reply. Watch for impersonation/PII-harvest threads; our value-add there is safety.
- Brand account = Pantip member 9373300. social-ops-daily auto-run was blocked posting (wrong account);
  Pantip posts are done MANUALLY from 9373300 in-session until the automation's Pantip login is fixed.

## 2026-06-26 Pantip status (today)
All 4 drafts from _pantip_POST_NOW_20260625.md are LIVE, single copies, no links, comply_gate pass:
  #1 guarantor/2558-law -> 44137088 | #2 DSR/condo -> 44137623 | #3 BBL card -> 44140264 (dup fixed)
  #4 car-for-cash anti-scam PSA -> 44140019 (comment 119498960). 4 threads, under the <=5/day cap.

## 2026-06-26 on-site winner amplification (PENDING OWNER COMMIT - Claude did NOT push)
WHY: GA4 says /kept-savings-2026 = breakout winner (24 views -> 21 clicks ~88% CTR) but the homepage
("dead router": ~78 views/window, 0 onward clicks) did NOT feature it. Direction "amplify the winner".
CHANGE: build_site.py HOME_FEATURED guide-row now leads with a Kept pill ->
  <a href="/kept-savings-2026.html">Kept: บัญชีออมเงินดอกสูง สมัครฟรี</a> (label REUSED from existing
  in-file Thai string via a pure-ASCII patcher = byte-safe; backup = build_site.py.bak_homefeat).
QA: rebuilt site/ with SITE_BASE=https://ngernduangold.com -> pill present & first in row, canonical ok,
  0 example.com, 0 mojibake, winner still in article cards. Surgical/additive; no article/canonical/SITE_BASE change.
TO SHIP (owner): git add build_site.py site/ && git commit -m "home: feature Kept winner pill" && git push
  (Netlify auto-deploys on push). Revert = restore build_site.py.bak_homefeat + rebuild.

## 2026-06-26 SHIPPED - homepage Kept-winner pill is LIVE (was "pending owner commit")
- CC deployed: commit e751f08, Netlify Published (~12s), browser-verified first pill in คู่มือแนะนำ =
  "Kept: บัญชีออมเงินดอกสูง สมัครฟรี" -> /kept-savings-2026.html. QA 4/4. DONE.
- OPS LESSONS (from CC, keep for future deploys):
  1) site/ is GITIGNORED -> Netlify rebuilds from source. Commit build_site.py ONLY (not site/). My CC prompt
     said "git add site/" - unnecessary; harmless but site/ won't stage. Future: commit source files only.
  2) automation-log/ is gitignored too (Netlify ignore-rule cancels automation-log-only commits) -> all my
     packs/findings/session logs there are LOCAL + Drive-backup only, never deployed. Correct/expected.
  3) Live-verify gotcha: urllib/web_fetch can return STALE CACHE (CC saw age~2986s false "not live").
     BROWSER is truth. For future live checks use the Netlify deploy permalink, or browser, not a bare fetch.
- Uncommitted/local (intentional): OPERATING-NOTES.md, PROJECT-HANDOFF.md, _show.py, _vidout/.

## 2026-06-26 STILL OPEN (owner)
- linktr.ee titleloan posts queued FB+IG 27 มิ.ย. (Postiz ids cmqdkfau4/cmqdkfboe/cmqdkfawf/cmqdkfbsc):
  Postiz MCP cannot delete -> delete in Postiz UI (or CC via browser if given the Postiz URL) BEFORE 27 มิ.ย.
- GSC reindex /kept-savings-2026 + /links: owner UI-only (no GSC API creds).

## 2026-07-02 launch status + Pantip incident + monitoring (จาก Cowork audit — CC sync)
- PANTIP INCIDENT: กระทู้ 44143972 ถูกลบโดย mod (เหตุ: ขายของ/โฆษณา) + บัญชีแบรนด์เคยโดน mod-warning (29 มิ.ย.)
  -> นโยบายใหม่ (มีผลทันที): ห้ามตั้ง/ตอบกระทู้ Pantip ที่มีลิงก์ขาย/ราคาสินค้า จนกว่าเจ้าของสั่งเปลี่ยน
  (Pantip = value-first เท่านั้น; ช่องทางขายใช้ IG/FB/YT + /links)
- IG Reel เปิดตัว e-book ขึ้นแล้ว: DaRaYRLD80W (2 ก.ค.) cross-post FB+IG ผ่าน Business Suite composer สำเร็จ
  · FB Reel ตัวซ้ำไร้แคปชัน (โพสต์ 5:39) ลบแล้ว (อยู่ถังขยะ 30 วัน กู้ได้ถ้าจำเป็น)
- LAUNCH STATUS เป็นระบบไฟล์แล้ว: automation-log/launch-status.json = single source สถานะ launch
  (Cowork/CC/เจ้าของแก้ไฟล์นี้ -> dashboard การ์ด "🚀 Launch" อัปเดตเอง ผ่าน pipeline/dashboard_agent.py _launch())
- MONITORING แบ่งงานกันแล้ว (กันซ้ำซ้อน): Cowork มี scheduled check ทุกเช้า 08:00 (อ่านอย่างเดียว YT/IG/funnel)
  -> ฝั่ง CC/local ไม่ต้องตั้ง monitor ใหม่ซ้ำ · traffic_monitor.py อัปเกรดแล้ว: อ่าน GA4 จริง (ga4-funnel/pages/metrics.csv)
  + ช่องครบ fb/ig/tiktok/pantip/threads/yt/pinterest (ช่องที่ metrics.csv ไม่ track = n/a) + บรรทัด Sales
  (Gumroad ไม่มี API ฟรี -> เจ้าของ export CSV วาง automation-log/gumroad-sales.csv คอลัมน์ date,units,amount_thb)
