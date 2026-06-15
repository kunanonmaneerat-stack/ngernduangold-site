# 🔒 ngernduangold — Posting dedup protocol (กันโพสต์ซ้ำ / รับคำสั่งแทรก)

> สร้าง 2026-06-15 หลัง adversarial audit (3 reviewer). ทั้ง 3 ยืนยัน: **ก่อนหน้านี้ระบบโพสต์ซ้ำได้จริง** —
> ad-hoc (`type=now`) กับ scheduled loop **มองไม่เห็นกัน**, และ Postiz **ลบโพสต์ที่ schedule แล้วไม่ได้**
> → ถ้าซ้ำหลุดไป = ยิงแน่นอน แก้ได้ทางเดียวคือ Cowork ลบมือใน Postiz web UI ก่อนถึงเวลา.

## หลักการเดียวที่ต้องจำ
**ตัดสิน dedup *ก่อน* ยิงเสมอ** (เพราะลบทีหลังไม่ได้). ทุก path เช็ก ledger เดียวกันก่อน แล้ว record ทันทีหลังยิง.

Ledger = `automation-log/post-ledger.jsonl` (append-only, path ตายตัว — ทุก routine ใน Claude Code อ่าน/เขียนตรงๆ ได้
บนเครื่องเดียวกัน ไม่ต้องพึ่ง git; git push = ให้ Cowork *เห็น* เท่านั้น). repo public → row มีแค่ channel/clip/date/postId ไม่มีรายได้/PII.

Helper: `post_ledger.py`
- `dedup_key = sha1(channel | clip_key | local-date)` = "คลิปนี้ ช่องนี้ วันนี้"
- `is_twin()` สแกน ±16 วัน → คลิปเดิมลงช่องเดิมในกรอบนี้ = ซ้ำ (กันทั้ง "ยิงวันนี้แล้วซ้ำพรุ่งนี้")
- **clip_key resolver**: แปลง mp4 / postiz library id / topic-slug → key มาตรฐานจาก content_queue → ทุก path key ตรงกัน
- **multicast = N rows** (1 ต่อช่อง) → ad-hoc ลงช่องใดช่องหนึ่งทีหลังจับซ้ำได้
- **cross-channel อนุญาต** (titleloan ลง TikTok + IG วันเดียวกัน = OK เพราะคนละช่อง) แต่ซ้ำช่องเดิม = บล็อก

## A) AD-HOC INTERRUPT (คุณสั่ง "โพสต์ X เดี๋ยวนี้") — ปิดความเสี่ยงซ้ำได้ ✅
ad-hoc เป็น **interactive (มีคน/Claude อยู่)** → อ่าน live queue ที่เชื่อถือได้ (Chrome list-view) ได้ → จึงกันซ้ำได้จริง:
1. **resolve** X → clip_key (`post_ledger.resolve_clip_key`). ถ้า resolve ไม่ได้ = **หยุด** (fail-closed) ถาม owner.
2. **เช็ก ledger**: `python post_ledger.py check --channel <ch> --clip <X> --date <today>` → exit 2 = ซ้ำ/เต็ม cap, exit 0 = ว่าง.
3. **เช็ก live Postiz queue (บังคับ)**: Chrome MCP → `platform.postiz.com/launches` list-view → ยืนยันว่า X ไม่ได้ถูก schedule ลงช่องนั้นใน ±16 วัน (จับโพสต์ที่ ledger ไม่รู้ เช่น Cowork ตั้งมือ / record หลุด). ask_postiz = advisory เท่านั้น (run-log บอกเชื่อไม่ได้).
4. **ถ้าเจอฝาแฝด** → **อย่าโพสต์ซ้ำ**: เลือกคลิปอื่นหัวข้อเดียวกันที่ check ผ่าน → หรือถ้า owner ยืนกรานคลิปนี้ทั้งที่มีตัว schedule ค้าง = **เตือน + ขอ confirm ชัด** และให้ owner รับปากลบตัวค้างใน Postiz UI ก่อน (log เป็น note `owner_override`). ห้ามสร้างซ้ำเงียบๆ.
5. **ยิง** `integrationSchedulePostTool(type=now)` → เก็บ postId.
6. **record ทันที**: `python post_ledger.py record --channel <ch> --clip <key> --date <today> --post-id <id> --video <file> --topic <t> --type now --source adhoc` → นี่คือสิ่งที่กัน "รอบหน้า/ad-hoc ถัดไป" ไม่ให้ทำซ้ำตัวที่เพิ่งยิง.
7. set `used=true` ใน content_queue.json ของคลิปนั้น + log_run.py + telegram_notify.py (เหมือนเดิม).

## B) CRON LOOP (queue-keeper จ.+พฤ. / weekly engine) — fail-closed + best-effort
ก่อน schedule ทุก candidate:
1. โหลด `load_index(since_days=16)` ครั้งเดียวตอนเริ่ม.
2. **reconcile-first**: อ่าน live queue (Chrome list-view = แหล่งเดียวที่เชื่อได้) → `record` โพสต์ที่อยู่ในคิวแต่ยังไม่มีใน ledger (จับ ad-hoc/record-หลุด/Cowork-มือ) ก่อนตัดสินใจใหม่.
3. แต่ละ candidate → `is_twin()` **และ** `day_capacity()` → ซ้ำ/เต็ม = ข้าม เลือกคลิป `used=false` ตัวถัดไป.
4. หลัง schedule สำเร็จ → `record_post(type=schedule, source=queue-keeper|weekly-engine)` ทันที + อัปเดต index ใน batch (กันยิงซ้ำภายใน run เดียว). multicast → `record_multicast` (N rows).
5. **fail-closed**: ถ้า run อัตโนมัติ (ไม่มีคน) อ่าน live queue เชื่อถือไม่ได้เลย → **อย่า schedule** candidate ที่พิสูจน์ไม่ได้ว่าไม่ซ้ำ (default-deny) ดีกว่าโพสต์มั่ว.

## 🔍 อ่าน live Postiz queue ให้ถูก (แก้บั๊ก 15 มิ.ย. — เคยเกือบ refill ซ้ำยับ)
แหล่งที่เชื่อได้ = Postiz backend API (authenticated ผ่านเบราว์เซอร์ Chrome MCP). **ไม่ใช่ ask_postiz** (garbage).
```js
// Chrome MCP: navigate platform.postiz.com แล้ว javascript_tool:
const r = await fetch('https://api.postiz.com/posts?startDate=<ISO>&endDate=<ISO>', {credentials:'include'});
const posts = (await r.json()).p || [];     // ⚠️ คีย์ .p เท่านั้น
```
- ⛔ **บั๊กที่เจอ:** เคยอ่าน `.posts`/`.data` (ไม่มีในผลลัพธ์) → fall-through `[]` → **คืน count 0 ทั้งที่คิวมี 60+ โพสต์** → ถ้า refill ตามนั้น = ซ้ำทั้งคิว (Postiz ลบไม่ได้). โพสต์อยู่ใต้ **`.p`**.
- ⛔ **ห้ามส่ง `customer`** (เช่น `&customer=null`) → กรองเหลือ 0 (false empty).
- field ต่อโพสต์: `i`=id · `c`=content HTML · `d`=date UTC ISO · `s`=state (`QUEUE`=ค้างคิวจะยิง) · `n.pi`=provider (facebook/instagram/youtube/tiktok) · `g`=group id.
- **fail-closed:** อ่านไม่สำเร็จ/ได้ 0 ผิดปกติ = UNKNOWN → ห้าม refill. เติมเฉพาะวันที่อ่าน `.p` สำเร็จแล้วพิสูจน์ว่าว่างจริง.

## ⚠️ Residual gaps (ซื่อสัตย์ — reviewer เจอ ยังปิดไม่หมด)
| gap | สถานะ | ต้องทำต่อ (owner/Cowork) |
|---|---|---|
| Cowork ตั้งโพสต์ "มือ" ใน Postiz web UI | ledger ไม่เห็น → จับได้เฉพาะตอน reconcile (Chrome list-view) | Cowork ควร**ไม่ตั้งมือ**นอกระบบ หรือบอกให้ผม record |
| engine โพสต์ผ่าน browser (ไม่มี post_id) | record ผ่าน reconcile หลัง run ไม่ใช่ MCP-return | ย้าย engine มาใช้ MCP path (มี post_id) ถ้าทำได้ |
| cron ไม่มีคน → ไม่มี Chrome list-view ที่เชื่อได้ | ปัจจุบัน fail-closed (ข้ามถ้าพิสูจน์ไม่ได้) | แก้ ask_postiz ให้เชื่อได้ **หรือ** ย้าย cron ขึ้น cloud + script queue-read |
| concurrency (cron ยิงตอน ad-hoc ทำอยู่) | lockfile กันใน env เดียวกันได้ | คุมไม่ให้ cron กับ ad-hoc ทับเวลากัน |
| owner_override | "ซ้ำได้ถ้า owner กด yes ชัด" + รับปากลบตัวค้าง | ระวังกด yes พลาด |
| app ปิด → scheduled post ยิงเอง ledger ไม่อัปเดต | dedup ใช้ scheduled_for date (ไม่พึ่ง delivery status) + reconcile ตอนเปิดแอป | — |

**สรุปการรับประกัน:** ✅ ad-hoc interrupt ของ owner (interactive) = กันซ้ำได้จริง (ทำตาม A ครบ) · 🟡 cron cross-path = best-effort + fail-closed · 🔴 โพสต์นอกระบบ (Cowork มือ) = ต้อง reconcile ถึงจะเห็น
