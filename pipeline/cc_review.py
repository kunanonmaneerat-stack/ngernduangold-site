"""cc_review.py — agent รีวิวงานของ Claude Code -> ส่งให้ Cowork.

อ่านผล CC จาก cc-outbox (cc_bridge.collect) -> free_llm รีวิวคุณภาพ/ตรงบรีฟไหม/ความเสี่ยง
-> cowork-review/cc-review-<ts>.md + ping Cowork ให้คุมต่อ.
ใช้:  py pipeline/cc_review.py
"""
import os, sys, datetime
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import free_llm, cc_bridge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REV = os.path.join(ROOT, 'automation-log', 'cowork-review')


def main():
    results = cc_bridge.collect()
    if not results:
        print('no CC results in cc-outbox'); return
    os.makedirs(REV, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    p = os.path.join(REV, 'cc-review-' + ts + '.md')
    with open(p, 'w', encoding='utf-8') as f:
        f.write('# CC REVIEW (รีวิวงาน Claude Code) ' + ts + '\n\n> Cowork: ยกระดับ/ตัดสินใจ/สั่งรอบใหม่\n\n')
        for r in results:
            v, _ = free_llm.generate(
                'รีวิวงานนี้: ตรงบรีฟไหม คุณภาพโอเคไหม ความเสี่ยง/จุดต้องแก้ 3 ข้อ (สั้นๆ):\n\n' + r['text'][:4000],
                max_tokens=500, temperature=0.3)
            f.write('## ' + r['file'] + '\n**รีวิว:** ' + (v or '-') +
                    '\n\n<details><summary>งาน CC</summary>\n\n' + r['text'][:3000] + '\n</details>\n\n---\n\n')
    cc_bridge.ping('CC review พร้อม -> cc-review-' + ts + '.md (Cowork คุมต่อ)')
    print('cc review ->', p)


if __name__ == '__main__':
    main()
