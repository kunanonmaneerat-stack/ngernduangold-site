"""cc_bridge.py — agent สะพานคุยกับ Claude Code (CC).

send(title, body) : เขียน work order ที่ cc-inbox/order-<ts>.md ให้ CC execute (+ ping Telegram)
collect()         : อ่านผลที่ CC เขียนไว้ cc-outbox/*.md, ย้ายเข้า cc-archive, คืน list ผล

เป็น "กล่องจดหมายไฟล์" — CC คือคนรัน (มีเจ้าของคุม) ไม่โพสต์/commit/deploy เอง.
"""
import os, glob, shutil, datetime, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOG = os.path.join(ROOT, 'automation-log')
INBOX = os.path.join(LOG, 'cc-inbox')
OUTBOX = os.path.join(LOG, 'cc-outbox')
ARCH = os.path.join(LOG, 'cc-archive')
HERMES_HOME = r'C:\Users\nL_ku\AppData\Local\hermes'
HERMES_PY = os.path.join(HERMES_HOME, 'hermes-agent', 'venv', 'Scripts', 'python.exe')


def ping(msg):
    try:
        env = dict(os.environ); env['HERMES_HOME'] = HERMES_HOME
        subprocess.run([HERMES_PY, '-m', 'hermes_cli.main', 'send', '--to', 'telegram', msg],
                       cwd=os.path.join(HERMES_HOME, 'hermes-agent'), timeout=90, env=env)
    except Exception as e:
        print('ping skip:', str(e)[:60])


def send(title, body):
    os.makedirs(INBOX, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    p = os.path.join(INBOX, 'order-' + ts + '.md')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(body)
    ping('CC inbox: งานใหม่ "' + title + '" -> automation-log/cc-inbox/order-' + ts +
         '.md (execute แล้วเขียนผลที่ cc-outbox/) · ห้ามโพสต์/commit/deploy')
    return p


def collect():
    os.makedirs(ARCH, exist_ok=True)
    out = []
    for f in sorted(glob.glob(os.path.join(OUTBOX, '*.md'))):
        name = os.path.basename(f)
        out.append({'file': name, 'text': open(f, encoding='utf-8').read()})
        shutil.move(f, os.path.join(ARCH, name))
    return out
