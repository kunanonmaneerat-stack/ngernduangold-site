# CC → Cowork — Full Link-Binding Audit (site/ 67 หน้า + source) 2026-06-27
scope: site/*.html (60 indexable + 6 infographic + 1 GSC-verify) + build_site.py + pipeline templates
**รายงานอย่างเดียว — ไม่ deploy/ไม่ push fix (รอ approval ผ่าน push_agent gate)**

## สรุปตาราง (A-E)
| มิติ | ผล | รายละเอียด |
|---|---|---|
| A) rel=sponsored บน affiliate | ✅ ผ่าน | atth.me anchors ทุกตัวมี rel="sponsored noopener nofollow" — ขาด 0 จุด (รวม CTA ที่ JS quiz-reco inject ก็มี rel). 3 anchor class hubbtn ที่ไม่มี rel = internal nav (/quiz, /insurance-compare, /) ถูกต้องแล้ว |
| B) affiliate integrity | ✅ ผ่าน | 15 unique atth.me codes — live-check **HTTP 200 ทั้ง 15** (ไม่มี 4xx/ตาย); utm_source/medium/campaign/content ครบทุกลิงก์ (0 ขาด); disclosure ปรากฏทุกหน้าที่มี affiliate |
| C) internal 404 + netlify | ✅ ผ่าน | link_check.py: broken_files 0, routes 0; netlify.app ใน site/*.html = 0; sitemap 60 urls = .com ล้วน; robots Sitemap -> .com |
| D) canonical / OG | ✅ ผ่าน (เนื้อหา) | หน้าเนื้อหาทุกหน้า canonical+og:url+og:image = https://ngernduangold.com; 7 หน้า asset (6 infographic + google-verify) ไม่มี canonical/og = **ตั้งใจ** (มี meta robots=noindex + ไม่อยู่ใน sitemap -> ไม่เสี่ยง dup) |
| E) FB page ID | ⚠️ รอ Cowork ยืนยัน | โค้ดใช้ **583765282304956** อย่างสม่ำเสมอ (build_site.py: L2240 JSON-LD sameAs, L2313 contact, L2480 footer; L441 sharer.php = แชร์ ไม่เกี่ยว). เพจที่ Cowork จัดการ = 100029060247015 -> **Cowork ยืนยัน live ว่า 2 ID เพจเดียวกัน (New Pages dual-id) หรือคนละเพจ** แล้วบอก CC ว่าจะแก้เป็น URL/ID ไหน |

## เพิ่มเติม: blind spots ที่เจอจาก completeness-critic (verified ในโค้ดจริง) — เสนอ patch รอ approval
1) **[MAJOR] liveness-gate regex ตัด AXA /go/ link** — `tools/postdeploy_smoke.py:64` + `pipeline/check_affiliate_links.py` ใช้ regex `atth\.me/([0-9A-Za-z]+)` ซึ่ง match `atth.me/go/PhAKgrKX` (AXA PA, live 4 หน้า: insurance-compare/links/quiz/travel-insurance) ได้แค่ `atth.me/go` (ตัดที่ "/"). ผล: gate ตรวจ liveness ลิงก์ AXA ผิด URL = ไม่ถูก monitor (CC เช็กตรง ๆ แล้ว = 200 จริง แต่ gate มองไม่เห็น). neither tool สแกน site/_redirects.
   - **เสนอ patch:** เปลี่ยน regex เป็น `atth\.me/((?:go/)?[0-9A-Za-z]+)` (หรือ `[0-9A-Za-z/]+`) ทั้ง 2 ไฟล์ + เพิ่ม 5 /go/* targets จาก _redirects เข้าชุด liveness
2) **[MAJOR] disclosure วางหลัง CTA แรก (FTC clear-and-conspicuous)** — verified: หน้าเนื้อหา 58/60 มี atth.me ลิงก์แรก (offset ~14k) มา **ก่อน** คำ disclosure "ลิงก์พันธมิตร" (offset ~22k+). มีแต่ about/disclaimer ที่ disclosure มาก่อน. ปุ่ม hero affiliate ยิงก่อนผู้อ่านเลื่อนถึง disclaimer ท้ายหน้า.
   - **เสนอ patch:** เพิ่มบรรทัด disclosure สั้น ๆ ที่/เหนือปุ่ม CTA แรกของหน้าเนื้อหา (แก้ใน build_site.py helper cta() หรือ head/intro) + เพิ่ม assert ใน postdeploy_smoke.py (first-disclosure-offset <= first-atth-offset)
3) **[MAJOR/SEO] quiz.html + links.html canonical extensionless = dup** — quiz.html/links.html ประกาศ canonical `/quiz` `/links` (ไม่มี .html) + sitemap ก็ extensionless แต่ทุกหน้าเนื้อหาอื่นใช้ .html; Netlify เสิร์ฟทั้ง /quiz และ /quiz.html (200) ไม่ auto-301 (netlify.toml = host-only redirects, _redirects = /go/* เท่านั้น) -> /quiz.html, /links.html เป็น URL ซ้ำที่ canonical ชี้ไปคนละ URL.
   - **เสนอ patch:** เพิ่มใน _redirects (สร้างใน build_site.py _GO block): `/quiz.html /quiz 301!` + `/links.html /links 301!` (คง canonical extensionless ให้ตรง internal links nav) — หรือเปลี่ยน canonical 2 หน้าเป็น .html. แนะนำ 301 (internal nav ใช้ /quiz /links อยู่แล้ว)
4) **[MINOR] /go/ bio-redirect surface นอก gate** — site/_redirects มี 5 cloaked 301 (/go/card,/save,/loan,/debt,/title -> atth.me) ใช้เป็น bio link โซเชียล; 301 ไม่มี body -> ไม่มี rel/disclosure บนตัว redirect + อยู่นอกทั้ง 2 gate. (5 ปลายทางทับกับ inline codes -> liveness ครอบโดยบังเอิญ). disclosure ของ /go/* ต้องอยู่ใน bio/caption โซเชียล (เป็น layer ของ Cowork/owner).
   - **เสนอ:** doc ว่า disclosure /go/* = bio-layer + เพิ่ม /go/ targets เข้า affiliate-health gate
5) **[NIT] นับ anchor** — CC รายงาน "170 atth.me" (= unique URL occurrences); จำนวน anchor จริงสูงกว่า (~188). ข้อสรุป "0 missing rel" ยังถูกต้อง เพราะ postdeploy_smoke.py assert rel ราย-ปุ่มทุกปุ่มอยู่แล้ว (gate backstop). แค่ตัวเลข enumeration คลาดเล็กน้อย

## verdict: core A-E สะอาด · gaps ที่เจอเป็นฝั่ง compliance/SEO/tooling — เสนอ patch ไว้ทั้งหมด **รอ approval ก่อนทำ** (ไม่แตะ canonical/เนื้อหาเอง, ไม่ push)
