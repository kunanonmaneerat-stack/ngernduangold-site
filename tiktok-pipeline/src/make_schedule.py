#!/usr/bin/env python3
# make_schedule.py — clip_registry + week1 order -> posting-schedule.csv (owner tracker + kill-criterion).
# 14 days from day 8 (after 7-day warm-up), 1 clip/day, alternating bio/follow per week1 pack order.
import argparse, csv, datetime, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import config as C

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-06-27", help="วันโพสต์ day-8 (หลัง warm-up 7 วัน) — owner ปรับได้")
    a = ap.parse_args()
    reg = C.jload(C.ROOT / "clip_registry.json")
    by_clip = {r["clip"]: r for r in reg}
    # week1 order (day 8-14)
    wk_order = []
    wk = C.INPUT / "week1_captions.json"
    if wk.exists():
        wk_order = [c["clip"] for c in sorted(C.jload(wk), key=lambda x: x["day"])]
    rest = [r["clip"] for r in reg if r["clip"] not in wk_order]
    ordered = wk_order + rest
    ordered = ordered[:14]
    try:
        start = datetime.date.fromisoformat(a.start)
    except ValueError:
        start = datetime.date(2026, 6, 27)
    rows = []
    for i, clip in enumerate(ordered):
        r = by_clip.get(clip, {})
        d = start + datetime.timedelta(days=i)
        rows.append({"date": d.isoformat(), "day": 8 + i, "clip": clip, "topic": r.get("topic_th", ""),
                     "cta": r.get("cta", ""), "caption_file": r.get("caption_file", ""),
                     "posted(Y/N)": "", "views": "", "likes": "", "follows": "", "profile_clicks": "", "notes": ""})
    out = C.READY / "posting-schedule.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        f.write("# kill-criterion: วัน 30 view เฉลี่ย <300 ทุกคลิป = ทบทวน · วัน 60 ยังติดเพดาน 0-200 = หยุด TikTok กลับ Pantip/Threads\n")
        w = csv.DictWriter(f, fieldnames=["date", "day", "clip", "topic", "cta", "caption_file",
                                          "posted(Y/N)", "views", "likes", "follows", "profile_clicks", "notes"])
        w.writeheader()
        for row in rows:
            w.writerow(row)
    print(f"[make_schedule] {len(rows)} วัน (day 8-{7+len(rows)}, เริ่ม {start}) → ready-for-cowork/posting-schedule.csv")

if __name__ == "__main__":
    main()
