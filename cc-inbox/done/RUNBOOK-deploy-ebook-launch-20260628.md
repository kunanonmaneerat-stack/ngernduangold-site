# RUNBOOK (CC) — Deploy e-book launch (push 5-commit stack + verify /links)

**สำหรับ:** Claude Code (CC) · **สร้างโดย:** Cowork · 2026-06-28
**อนุมัติ push แล้ว:** เจ้าของเลือก "Push ทั้ง 5 commit" → `cc-inbox/APPROVE-push-ebook-launch-20260628.md`
**เป้าหมาย:** push stack 5 commit (`857fe46..2356873`) → Netlify rebuild → ปุ่ม e-book ขึ้น `ngernduangold.com/links` → verify
**กฎเหล็ก:** ทำทีละ step · ถ้า step ไหน "ผลไม่ตรงคาด (❌ ABORT)" ให้ **หยุด + รายงาน** อย่า push/แก้มั่ว · ไฟล์สินค้า (PDF/xlsx) ห้ามเข้า repo

---

## STEP 0 — Orient & ยืนยัน stack (อ่านอย่างเดียว)
```bash
cd C:\Users\nL_ku\ngernduangold-site
git branch --show-current                 # คาด: main
git fetch origin
git status                                # คาด: working tree clean
git log --oneline origin/main..HEAD       # คาด: 5 commits, บนสุด=2356873 ปุ่ม e-book
git log --oneline -6
```
**✅ ผ่านเมื่อ:** อยู่ branch หลัก · tree clean · เห็น **5 commit** ระหว่าง origin..HEAD (3 link-patches + report + 2356873)
**❌ ABORT ถ้า:** commit ≠ 5 / มี commit แปลกปลอม / tree ไม่ clean → รายงานสิ่งที่เห็น อย่า push

---

## STEP 1 — Verify เนื้อหา commit ปุ่ม e-book (2356873)
```bash
# 1.1 source มีปุ่ม + URL ถูก
grep -n "debt-payoff-planner" build_site.py

# 1.2 built output มีปุ่ม (อย่างน้อย 1)
grep -c "l/debt-payoff-planner" site/links.html

# 1.3 ต้องเป็นสินค้าเราเอง: rel=noopener, ห้ามมี sponsored/nofollow บนปุ่มนี้
grep -o '<a[^>]*debt-payoff-planner[^>]*>' site/links.html
#   ↑ ตรวจ string นี้: ต้องมี rel="noopener" และต้อง **ไม่มี** คำว่า sponsored หรือ nofollow

# 1.4 byte-safe Thai (เปิด utf-8 ไม่ error)
python -c "s=open('site/links.html',encoding='utf-8').read(); print('utf8 OK', s.count('debt-payoff-planner'))"
```
**✅ ผ่านเมื่อ:** 1.2 ≥ 1 · 1.3 มี `rel="noopener"` และไม่มี sponsored/nofollow · 1.4 ไม่ error
**❌ ABORT ถ้า:** ปุ่มมี sponsored/nofollow (ผิด — เป็นสินค้าเราเอง) / URL ผิด / ไทยเพี้ยน → หยุด รายงาน

---

## STEP 2 — Rebuild ยืนยัน source==built (กัน built ค้าง)
```bash
python build_site.py
git status        # คาด: ไม่มี diff ใหม่ (built ที่ commit ไว้ตรงกับ source แล้ว)
```
**✅ ผ่านเมื่อ:** `git status` clean (build ไม่สร้าง diff = ของที่ commit สด)
**⚠️ ถ้ามี diff ใน site/:** แปลว่า commit 2356873 ลืม build output → `git add -A && git commit --amend --no-edit` (หรือ commit เพิ่ม) ให้ built ตรง source **ก่อน** push แล้วทำ STEP 1 ซ้ำ
**❌ ABORT ถ้า:** build error → รายงาน traceback

---

## STEP 3 — Gates (link + affiliate + comply ตามมาตรฐานโปรเจกต์)
```bash
python pipeline/link_check.py
python check_affiliate_links.py
# + comply gate ปกติของโปรเจกต์ ถ้ามี
```
**✅ ผ่านเมื่อ:** ทุก gate เขียว/ไม่มี error ใหม่
**❌ ABORT ถ้า:** gate แดง → หยุด แก้ที่ต้นเหตุ รันใหม่ ห้าม push ทั้งที่แดง

---

## STEP 4 — PUSH (action ที่อนุมัติแล้ว)
```bash
# ใช้ gated pusher ปกติ (อ่าน approval gate):
python pipeline/push_agent.py
#   — หรือถ้า push_agent ต้องการ flag/ยืนยัน ให้ทำตาม prompt ของมัน
#   — fallback ตรง (เฉพาะเมื่อ STEP 0–3 ผ่านครบ): git push origin main
```
**✅ ผ่านเมื่อ:** push สำเร็จ, origin/main = HEAD (2356873)
```bash
git log --oneline origin/main -1          # คาด: 2356873
```
**❌ ABORT ถ้า:** push reject/conflict → รายงาน error (อย่า force-push)

---

## STEP 5 — รอ Netlify + Verify LIVE
รอ Netlify rebuild (~1–3 นาที) แล้ว:
```bash
# 5.1 ปุ่ม e-book ขึ้น /links จริง
curl -s https://ngernduangold.com/links | grep -o "l/debt-payoff-planner" | head -1
#   คาด: เจอ "l/debt-payoff-planner"

# 5.2 ปุ่มลิงก์ถูกปลายทาง + ข้อความปุ่ม
curl -s https://ngernduangold.com/links | grep -o 'คู่มือ + Worksheet ปลดหนี้บัตรเครดิต[^<]*'

# 5.3 สุ่มเช็ค 3 link-patches ไม่พัง (P3 canonical .html→pretty 301)
curl -sI https://ngernduangold.com/links.html | grep -i "location"   # คาด: redirect → /links
```
**✅ ผ่านเมื่อ:** 5.1 เจอ slug · 5.2 เจอข้อความปุ่ม · 5.3 redirect ทำงาน
**❌ ABORT/แจ้ง ถ้า:** /links ไม่มีปุ่ม หลัง deploy เสร็จ → รายงาน (อาจ build บน Netlify ต่างจาก local)

---

## STEP 6 — รายงานกลับ (ตาม template)
```
DEPLOY REPORT — e-book launch (2026-06-28)
- pushed: <commit สุดท้าย> → origin/main : <OK/FAIL>
- Netlify deploy: <deploy id / สถานะ>
- /links ปุ่ม e-book: <พบ/ไม่พบ> (slug debt-payoff-planner)
- ปลายทาง: ngernduangold.gumroad.com/l/debt-payoff-planner : <OK>
- rel=noopener / ไม่มี sponsored-nofollow: <OK>
- 3 link-patches smoke (canonical 301): <OK/FAIL>
- ปัญหา/หมายเหตุ: <...>
```
ส่ง report นี้กลับให้ Cowork → Cowork จะ verify ซ้ำหน้าเว็บ + ปิด task #37 + แจ้งเจ้าของให้เริ่มโพสต์ caption (Threads/FB ก่อน · draft: `automation-log/_product1_promo_captions_20260628.md`)

---

### Rollback (เฉพาะกรณีฉุกเฉิน หลัง push แล้วเว็บพัง)
```bash
git revert --no-edit 2356873     # revert เฉพาะปุ่ม e-book (เก็บ link-patches ไว้)
# แล้ว push ตาม STEP 4 — ไม่ force, ไม่ rebase history ที่ push ไปแล้ว
```
