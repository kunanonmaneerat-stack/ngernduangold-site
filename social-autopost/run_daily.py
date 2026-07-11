#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# run_daily.py — orchestrator โพสต์โซเชียลรายวัน (order MASTER 2026-07-11)
#
# การแบ่งช่องโดยออกแบบ (channel isolation — ช่องนึงพังไม่ลากอีกช่อง):
#   IG Reels  = GitHub Action `ig-reels` (cloud, 20:00TH) — ไม่ได้รันจากไฟล์นี้
#   TikTok    = ตัวนี้ รันบนเครื่องเจ้าของ (ต้องใช้ persistent login profile) 19:00TH
#
# ใช้กับ Windows Task Scheduler (ดู runbook.md §schedule):
#   python social-autopost/run_daily.py            -> TikTok DRY RUN ของวันนี้
#   python social-autopost/run_daily.py --live     -> TikTok โพสต์จริง (หลังผ่านเทส 1 คลิป)
import os, sys, subprocess, datetime

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    args = [a for a in sys.argv[1:]]
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    print("[run_daily] %s | TikTok publisher (IG = GitHub Action แยกต่างหาก)" % date)
    r = subprocess.run([sys.executable, os.path.join(HERE, "publish_tiktok.py")] + args)
    print("[run_daily] tiktok exit=%d" % r.returncode)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
