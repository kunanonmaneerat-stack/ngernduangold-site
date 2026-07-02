# CC → Cowork — Link-audit patches PREPARED (3 commits, NOT pushed) 2026-06-27
**สถานะ: เตรียมเสร็จ commit แยก 3 ตัว ค้างใน local (ahead 3, ยังไม่ push) — รอ owner approve → push_agent push (= deploy)**
RULES ที่ทำตาม: ห้าม auto-deploy (push build_site.py = deploy → ไม่ push) · comply_gate/smoke ผ่าน · byte-safe Thai · 1 commit/patch

## PATCH 1 — affiliate liveness regex (commit eef5270)
ไฟล์: check_affiliate_links.py:15 + tools/postdeploy_smoke.py:64
- regex `https://atth\.me/[0-9A-Za-z]+` → `https://atth\.me/(?:go/)?[0-9A-Za-z]+` (รับ /go/<token>)
- VERIFY: รัน check_affiliate_links.py → **15/15 = HTTP 200 รวม AXA `atth.me/go/PhAKgrKX`** (เดิมตัดเป็น atth.me/go = ไม่เคยถูกเช็ก); smoke label code ถูกด้วย

## PATCH 2 — FTC disclosure เหนือ CTA แรก (commit 0e7cc4e)
ไฟล์: build_site.py (helper AFF_DISC + affil_disclose() + wrap 2 จุดเขียนหน้า: article-loop + links) + tools/postdeploy_smoke.py (assertion)
- affil_disclose() แทรก disclosure `* มีลิงก์พันธมิตร — เราอาจได้รับค่าตอบแทนเมื่อสมัครผ่านลิงก์ โดยไม่มีค่าใช้จ่ายเพิ่มกับคุณ` ก่อน `<a...atth.me/...>` ตัวแรกของหน้า (idempotent; anchor บน anchor จริง ไม่แตะ GA4 listener string ใน head)
- ครอบคลุม: 57 บทความ (ART loop) + links.html = ทุกหน้าที่มี affiliate anchor (index/quiz/contact/about/disclaimer ไม่มี static anchor → ข้าม)
- smoke assertion: ถ้าหน้ามี `<a...atth.me/...>` → disclosure ("มีลิงก์พันธมิตร"/"ได้รับค่าตอบแทน") ต้องมาก่อน anchor นั้น
- VERIFY: rebuild → disclosure offset < first-anchor offset ทุกหน้า (car-for-cash 15564<15819, bureau 15316<15571, links 17748<18003); **smoke 60/60 PASS** (รวม assertion ใหม่)

## PATCH 3 — canonical duplicate 301 (commit b94153d)
ไฟล์: build_site.py (_redirects generation)
- เพิ่มใน site/_redirects: `/quiz.html   /quiz   301!` + `/links.html  /links  301!` (คง canonical pretty เดิมที่ตรง nav/bio)
- VERIFY: rebuild → site/_redirects มี 2 บรรทัดใหม่ต่อท้าย 5 /go/* ; smoke 60/60 PASS

## ไม่ patch (ตามที่ Cowork ปิดจบ)
E FB-id (583765282304956 = เพจถูกต้อง dual-id) · MINOR /go/* rel (bio-layer ของ Cowork) · NIT anchor count (smoke per-button การันตีอยู่แล้ว — ตอนนี้ build จริง = 188 ปุ่ม)

## รอ approve
3 commits ahead origin/main=857fe46: eef5270 (P1) · 0e7cc4e (P2) · b94153d (P3). **CC ไม่ push** — owner/push_agent approve แล้ว push (Netlify build เพราะแตะ build_site.py = deploy). ถ้า approve: push 3 commits → Netlify rebuild → live.
