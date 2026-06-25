"""loop.py — ออร์เคสเตรเตอร์วงจรปิด ngernduangold (Cowork คุม).

  plan     : dispatcher (council ตรวจ 5 ชั้น) -> executor (รวมแผน -> ส่ง CC inbox)   [อัตโนมัติ]
  <รอ>      : Claude Code execute งานใน cc-inbox -> เขียนผล cc-outbox                [CC/เจ้าของ]
  collect  : report_to_cowork (รับผล CC -> brief ให้ Cowork)                         [อัตโนมัติ]
  <รอ>      : Cowork วิเคราะห์ -> เขียน orders.txt รอบใหม่ -> วนกลับ plan             [Cowork]

รัน:  py pipeline/loop.py plan   |   py pipeline/loop.py collect
"""
import os, sys
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def stage_plan():
    import dispatcher, executor
    print('=== stage: PLAN (council -> aggregate -> CC inbox) ===')
    dispatcher.main()
    executor.main()
    print('>> รอ Claude Code execute งานใน cc-inbox/ แล้วเขียนผลที่ cc-outbox/ -> จากนั้น: py loop.py collect')


def stage_collect():
    import report_to_cowork
    print('=== stage: COLLECT (CC results -> Cowork review) ===')
    report_to_cowork.main()
    print('>> Cowork วิเคราะห์ cowork-review/ ล่าสุด -> เขียน orders.txt รอบใหม่ -> py loop.py plan')


if __name__ == '__main__':
    s = sys.argv[1] if len(sys.argv) > 1 else 'plan'
    {'plan': stage_plan, 'collect': stage_collect}.get(s, lambda: print('usage: loop.py plan|collect'))()
