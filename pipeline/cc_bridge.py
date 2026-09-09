"""cc_bridge.py — local file bridge for Claude Code (CC).

send(title, body) : เขียน work order ที่ cc-inbox/order-<ts>.md ให้ CC execute
collect()         : อ่านผลที่ CC เขียนไว้ cc-outbox/*.md, ย้ายเข้า cc-archive, คืน list ผล

Scheduled/local callers never send Telegram, Slack, email, or browser messages.
An actor string or command-line flag is not owner-authentication, so the old
Hermes subprocess sink is deliberately absent from this bridge.
"""
import os, glob, shutil, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOG = os.path.join(ROOT, 'automation-log')
INBOX = os.path.join(LOG, 'cc-inbox')
OUTBOX = os.path.join(LOG, 'cc-outbox')
ARCH = os.path.join(LOG, 'cc-archive')


def ping(msg):
    """Compatibility no-op: retain local workflows without external mutation."""
    print('notification local-only: ' + str(msg)[:120])
    return False


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
        with open(f, encoding='utf-8') as handle:
            text = handle.read()
        out.append({'file': name, 'text': text})
        shutil.move(f, os.path.join(ARCH, name))
    return out
