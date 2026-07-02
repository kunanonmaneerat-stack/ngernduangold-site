# DEPLOY REPORT — e-book launch (2026-06-28) — ✅ ALL GREEN, LIVE
ref: cc-inbox/APPROVE-push-ebook-launch + RUNBOOK-deploy-ebook-launch-20260628.md (owner approved "push ทั้ง 5 commit")

- pushed: 857fe46..2356873 (5 commits) → origin/main : **OK** (origin/main = 2356873 = HEAD, ahead 0)
- Netlify deploy: rebuilt + LIVE (button found on first poll ~<1 min after push)
- /links ปุ่ม e-book: **พบ** — slug `l/debt-payoff-planner` + ข้อความปุ่ม "คู่มือ + Worksheet ปลดหนี้บัตรเครดิต" ครบ
- ปลายทาง: https://ngernduangold.gumroad.com/l/debt-payoff-planner : **OK (HTTP 200)**
- rel=noopener / ไม่มี sponsored-nofollow บนปุ่ม e-book: **OK** (สินค้าเราเอง ไม่ใช่ affiliate — ถูกต้อง)
- 3 link-patches (deployed ในชุดเดียวกัน):
  * P3 canonical 301: **OK live** — `HEAD /links.html → 301 → /links` (และ /quiz.html ตามกฎเดียวกัน)
  * P2 FTC disclosure: **OK live** — bureau page: aff-disc มาก่อน atth.me anchor แรก (15296 < 15551)
  * P1 affiliate liveness regex: deployed (source); pre-push verified 15/15 atth.me = 200 รวม AXA /go/
- gates ก่อน push: link_check broken_files 0 · check_affiliate_links 15/15 0 problem · smoke 60/60 PASS
- byte-safe: site/links.html utf-8 OK, 0 mojibake
- ปัญหา/หมายเหตุ: ไม่มี. ทั้ง 5 commit ขึ้น live แล้ว (e-book button + link-audit P1/P2/P3 + report)

## NEXT (Cowork/owner)
พร้อมโพสต์ caption แล้ว (ปุ่มขึ้น /links จริง — คนกดแล้วเจอ). draft: automation-log/_product1_promo_captions_20260628.md · ลำดับ Threads/FB ก่อน → IG/TikTok · ทุกโพสต์ CTA → ngernduangold.com/links. → Cowork ปิด task #37 + แจ้งเจ้าของเริ่มโพสต์.
