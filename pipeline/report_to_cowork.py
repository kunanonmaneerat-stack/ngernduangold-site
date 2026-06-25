"""report_to_cowork.py — agent รับผลจาก Claude Code -> ส่งให้ Cowork วิเคราะห์ละเอียด.

อ่านผล CC จาก cc-outbox (ผ่าน cc_bridge.collect) -> brief ที่ cowork-review/review-<ts>.md
-> ping Telegram. จากนั้น Cowork อ่าน -> วิเคราะห์/ยกระดับ -> เขียน orders.txt รอบใหม่ -> dispatcher.
"""
import os, sys, datetime
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cc_bridge
import comply_gate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REVIEW = os.path.join(ROOT, 'automation-log', 'cowork-review')


def main():
    results = cc_bridge.collect()
    if not results:
        print('no CC results in cc-outbox'); return
    os.makedirs(REVIEW, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    p = os.path.join(REVIEW, 'review-' + ts + '.md')
    with open(p, 'w', encoding='utf-8') as f:
        f.write('# COWORK REVIEW — ผลจาก Claude Code (' + ts + ')\n\n')
        f.write('> Cowork: วิเคราะห์ละเอียด ยกระดับ/ปรับปรุง แล้วเขียนหัวข้อรอบใหม่ลง orders.txt -> dispatcher\n\n')
        f.write('## เช็กลิสต์วิเคราะห์ (Cowork)\n')
        f.write('- คอนเทนต์แต่ละแพลตฟอร์ม hook แรงพอ? คปภ-safe? ไม่มีลิงก์ในโพสต์?\n')
        f.write('- ข้อเสนอปรับปรุงฟันเนลของ CC คุ้มทำไหม? ส่งต่อ owner/CC ทำต่อไหม?\n')
        f.write('- หัวข้อรอบถัดไปที่ควรปั่น (ป้อน dispatcher)?\n\n')
        for r in results:
            ok, issues = comply_gate.check(r['text'])
            verdict = '✅ compliance PASS' if ok else '⚠️ FAIL: ' + '; '.join(issues)
            f.write('## ผล: ' + r['file'] + '  — ' + verdict + '\n\n' + r['text'].strip() + '\n\n---\n\n')
    cc_bridge.ping('Cowork review พร้อม: ' + str(len(results)) + ' ผลจาก CC -> cowork-review/review-' + ts + '.md')
    print('collected', len(results), 'CC result(s) ->', p)


if __name__ == '__main__':
    main()
