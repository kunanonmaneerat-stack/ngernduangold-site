"""dispatcher.py — agent รับ order จาก Cowork แล้วกระจายงานต่อ.

flow:  Cowork ตั้ง order (automation-log/orders.txt หรือใช้ default)
       -> dispatcher ส่งแต่ละหัวข้อเข้าสภา content_council (expert->compliance->value->review->correct)
       -> draft ที่ตรวจ 5 ชั้นแล้ว เข้าคิว automation-log/council-<date>.md
       -> แจ้งเตือน Telegram ผ่าน Hermes ("คิวพร้อม approve")
       -> เจ้าของเปิดคิว กด approve แล้วโพสต์เอง (20%)

ปลอดภัยโดยออกแบบ: ไม่โพสต์ ไม่ commit ไม่ deploy ไม่ใช้โมเดล paid (free_llm pool, GLM ก่อน).
รัน:  py pipeline/dispatcher.py        (ตั้ง schedule ทุกเช้า = handoff)
"""
import os, sys, subprocess, datetime
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import content_council

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ORDERS = os.path.join(ROOT, 'automation-log', 'orders.txt')
HERMES_HOME = r'C:\Users\nL_ku\AppData\Local\hermes'
HERMES_PY = os.path.join(HERMES_HOME, 'hermes-agent', 'venv', 'Scripts', 'python.exe')

DEFAULT_ORDER = [
 "หนี้บัตรเครดิต/บัตรกดเงินสดหลายใบ จ่ายขั้นต่ำยอดไม่ลด อยากรวมหนี้",
 "เงินเดือนน้อยราว 15000 อยากสมัครบัตรเครดิต/สินเชื่อ กลัวไม่ผ่าน",
 "อยากเริ่มออมเงินให้ได้เป็นก้อน แบบทำได้จริงไม่เครียด",
 "ต้องการเงินด่วน มีรถ คิดเรื่องจำนำทะเบียน ดอกเท่าไรถึงคุ้ม",
 "จะไปเที่ยวต่างประเทศ ควรเลือกประกันเดินทางดูอะไรบ้าง",
]


def load_orders():
    if os.path.exists(ORDERS):
        lines = [l.strip() for l in open(ORDERS, encoding='utf-8') if l.strip() and not l.startswith('#')]
        if lines:
            return lines
    return DEFAULT_ORDER


def hermes_notify(msg):
    try:
        env = dict(os.environ)
        env['HERMES_HOME'] = HERMES_HOME
        subprocess.run([HERMES_PY, '-m', 'hermes_cli.main', 'send', '--to', 'telegram', msg],
                       cwd=os.path.join(HERMES_HOME, 'hermes-agent'), timeout=90, env=env)
        print('notified Telegram via Hermes')
    except Exception as e:
        print('notify skipped:', str(e)[:80])


def main():
    orders = load_orders()
    d = datetime.date.today().isoformat()
    ok = 0
    for topic in orders:
        try:
            final, rep = content_council.run(topic)
            content_council._write_queue(topic, final, rep)
            ok += 1
            print('queued:', topic[:42], '| draft', rep['m_expert'], '| final', rep['m_final'])
        except Exception as e:
            print('FAIL:', topic[:42], '|', str(e)[:80])
    msg = ("ngernduangold daily queue: " + str(ok) + "/" + str(len(orders)) +
           " draft ตรวจ 5 ชั้นแล้ว พร้อม approve -> automation-log/council-" + d + ".md (ลิงก์ DM/bio เท่านั้น คนกดโพสต์)")
    print('---'); print(msg)
    hermes_notify(msg)


if __name__ == '__main__':
    main()
