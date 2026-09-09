#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# run_daily.py — retired TikTok route, local plan inspection only
#
# การแบ่งช่องโดยออกแบบ (channel isolation — ช่องนึงพังไม่ลากอีกช่อง):
#   IG Reels  = GitHub Action `ig-reels` (cloud, 20:00TH) — ไม่ได้รันจากไฟล์นี้
#   TikTok    = retired; ตัวนี้ตรวจแผน local เท่านั้นและไม่ใช้ login profile/browser
#
# Scheduled/default execution must never open a browser or upload a draft.  The
# legacy ``--live`` passthrough was especially unsafe because arbitrary argv was
# forwarded to the publisher.  This wrapper now permits only the publisher's
# local ``--plan`` mode; live/browser actions remain outside the scheduled loop.
import argparse, os, sys, subprocess, datetime

HERE = os.path.dirname(os.path.abspath(__file__))


def main(argv=None, runner=subprocess.run):
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="")
    parser.add_argument("--local-only", action="store_true",
                        help="explicitly document the scheduled local-only posture")
    args = parser.parse_args(argv)
    date = args.date or datetime.datetime.now().strftime("%Y-%m-%d")
    command = [sys.executable, os.path.join(HERE, "publish_tiktok.py"),
               "--plan", "--date", date]
    print("[run_daily] %s | TikTok retired route: local plan only" % date)
    r = runner(command, check=False)
    print("[run_daily] local plan exit=%d" % r.returncode)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
