"""run_batch.py — ยิงหลายหัวข้อรวดเดียวผ่าน head_content (รันบนเครื่อง owner)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import head_content

TOPICS = [
    "เงินเดือน 15000 อยากได้บัตรเครดิตใบแรก สมัครใบไหนพอมีโอกาสผ่าน",
    "ฟรีแลนซ์รายได้ไม่ประจำ อยากได้บัตรหรือสินเชื่อ ทำโปรไฟล์การเงินยังไงให้มีโอกาสผ่าน",
    "ผ่อนรถอยู่แต่เริ่มผ่อนไม่ไหว ควรขายดาวน์ รีไฟแนนซ์ หรือคืนรถ ต่างกันยังไง",
]
for i, t in enumerate(TOPICS, 1):
    print(f"=== [{i}/{len(TOPICS)}] {t[:46]} ===", flush=True)
    try:
        head_content.run(t)
    except Exception as e:
        print("  ERROR:", str(e)[:120], flush=True)
print("=== BATCH DONE ===", flush=True)
