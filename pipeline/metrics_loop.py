"""metrics_loop.py — agent วนข้อมูลกลับ (Data-Driven Feedback Loop · Gemini แนะนำ).

อ่าน automation-log/metrics.csv (source,topic,views,clicks,quiz_start,conversion)
-> จัดอันดับว่าหัวข้อ/ช่องไหนเวิร์กจริง -> feedback ให้ Cowork + เสนอหัวข้อรอบใหม่จากของจริง.
ยังไม่มีไฟล์ = แจ้งให้ export GA4/แพลตฟอร์ม. ปรับจากข้อมูลจริง ไม่ใช่เดา.
ใช้:  py pipeline/metrics_loop.py
"""
import os, sys, csv, datetime
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cc_bridge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, 'automation-log')
SRC = os.path.join(LOG, 'metrics.csv')


def _num(r, k):
    try:
        return float(r.get(k, 0) or 0)
    except Exception:
        return 0.0


def main():
    if not os.path.exists(SRC):
        print('ยังไม่มี', SRC)
        print('-> export GA4/แพลตฟอร์มเป็น metrics.csv (คอลัมน์: source,topic,views,clicks,quiz_start,conversion) แล้วรันใหม่')
        return
    rows = list(csv.DictReader(open(SRC, encoding='utf-8')))
    rank = sorted(rows, key=lambda r: (-_num(r, 'conversion'), -_num(r, 'quiz_start'), -_num(r, 'clicks')))
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    p = os.path.join(LOG, 'metrics-feedback-' + ts + '.md')
    with open(p, 'w', encoding='utf-8') as f:
        f.write('# METRICS FEEDBACK (ข้อมูลจริง -> Cowork) ' + ts + '\n\n')
        f.write('> Cowork: ดันหัวข้อ/ช่องที่เวิร์กจริง เขียน orders.txt จากของจริง ไม่ใช่เดา\n\n')
        f.write('| # | source | topic | views | clicks | quiz_start | conversion |\n|--|--|--|--|--|--|--|\n')
        for i, r in enumerate(rank[:15], 1):
            f.write('| ' + str(i) + ' | ' + str(r.get('source', '')) + ' | ' + str(r.get('topic', ''))[:40] +
                    ' | ' + str(r.get('views', '')) + ' | ' + str(r.get('clicks', '')) +
                    ' | ' + str(r.get('quiz_start', '')) + ' | ' + str(r.get('conversion', '')) + ' |\n')
        top = [r.get('topic', '') for r in rank[:3] if r.get('topic')]
        f.write('\n## หัวข้อที่ควรดันต่อ (ป้อน dispatcher)\n' + '\n'.join('- ' + t for t in top) + '\n')
    cc_bridge.ping('Metrics feedback พร้อม -> metrics-feedback-' + ts + '.md (Cowork ปรับ orders จากของจริง)')
    print('metrics feedback ->', p, '| rows', len(rows))


if __name__ == '__main__':
    main()
