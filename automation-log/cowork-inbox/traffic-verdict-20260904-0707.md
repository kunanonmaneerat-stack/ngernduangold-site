# Traffic Analyst — decision safety (20260904-0707)
> manual reach + GA4 observed intent + verified money ledger; คลิกไม่ใช่รายได้

## สรุปข้อมูลปัจจุบัน
- manual metrics: 49 แถว · ช่องที่มีข้อมูล: bing, chatgpt, direct, fb, ig, pantip, threads, yt
- manual reach: views=1557 clicks=0
- GA4 observed: sessions=102 quiz_start=0 affiliate_click=6 buy_intent_click=2
- GA4 Decision Trust=UNTRUSTED — bundle=INVALID_METADATA; capture=UNTRUSTED; current=UNTRUSTED

## ความหมายที่ห้ามสลับกัน
- **affiliate_click**: 6 — คลิกแสดงความสนใจ ไม่ใช่ conversion/รายได้
- **buy_intent_click**: 2 — เจตนาซื้อ ยังไม่ใช่ยอดขาย
- **verified affiliate revenue**: unavailable · UNRECONCILED · do not interpret as zero
- diagnostic event density: suppressed while GA4 Decision Trust is UNTRUSTED

## ช่องว่างข้อมูล
- GA4 Decision Trust=UNTRUSTED: bundle=INVALID_METADATA; capture=UNTRUSTED; current=UNTRUSTED
- สมุดรายได้ยังไม่ trusted: reconciled source coverage is stale for the requested window

## VERDICT
**UNTRUSTED: GA4 ใช้เป็นหลักฐานตัดสินไม่ได้**

## DECISION
แสดง sessions/affiliate_click ได้เฉพาะเป็น observed diagnostics; ห้ามเลือกช่องชนะ เพิ่มความถี่ เปลี่ยนเวลาโพสต์ หรือ scale จนกว่า internal-traffic coverage จะผ่าน