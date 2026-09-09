"""Render manual social diagnostics without inferring revenue.

The legacy ``conversion`` column is treated as an unverified intent signal.
This file cannot select a winner or authorize scaling.
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
    with open(SRC, encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    rank = sorted(rows, key=lambda r: (-_num(r, 'conversion'), -_num(r, 'quiz_start'), -_num(r, 'clicks')))
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    p = os.path.join(LOG, 'metrics-feedback-' + ts + '.md')
    with open(p, 'w', encoding='utf-8') as f:
        f.write('# MANUAL METRICS DIAGNOSTIC (not revenue / not scale) ' + ts + '\n\n')
        f.write('> `metrics.csv` เป็น manual snapshot; คอลัมน์เดิม `conversion` '
                'ถูกตีความเป็น legacy intent เท่านั้น ไม่ใช่ conversion/รายได้ '
                'และห้ามเลือก winner หรือ scale จากไฟล์นี้\n\n')
        f.write('| # | source | topic | views | clicks | quiz_start | legacy_intent |\n|--|--|--|--|--|--|--|\n')
        for i, r in enumerate(rank[:15], 1):
            f.write('| ' + str(i) + ' | ' + str(r.get('source', '')) + ' | ' + str(r.get('topic', ''))[:40] +
                    ' | ' + str(r.get('views', '')) + ' | ' + str(r.get('clicks', '')) +
                    ' | ' + str(r.get('quiz_start', '')) + ' | ' + str(r.get('conversion', '')) + ' |\n')
        f.write('\n## คำตัดสิน\n'
                '- ใช้เพื่อหาแถวที่ควรตรวจต่อเท่านั้น\n'
                '- ต้องมี GA4 Decision Trust=TRUSTED และ paid affiliate commission '
                'ที่ผูกกับ source/content ก่อนพิจารณาเพิ่มน้ำหนัก\n')
    cc_bridge.ping('Manual metrics diagnostic ready -> metrics-feedback-' + ts + '.md (not revenue / not scale)')
    print('metrics feedback ->', p, '| rows', len(rows))
    return p


if __name__ == '__main__':
    main()
