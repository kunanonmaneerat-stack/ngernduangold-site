"""weekly_growth_review.py — Loop วัดผลรายสัปดาห์ (Gemini idea #5/#6).
อ่าน GA4 (source+page) + GSC (keywords) -> จัดอันดับ winner -> "ขยายผล (double-down)" actions.
ปลอดภัย: อ่าน csv + เขียน report เท่านั้น (ไม่โพสต์/ไม่ deploy/ไม่ลบ).
ใช้:  py pipeline/weekly_growth_review.py
"""
import os, sys, csv, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOG = os.path.join(ROOT, "automation-log")
GA4 = os.path.join(LOG, "ga4-metrics.csv")
PAGES = os.path.join(LOG, "ga4-pages.csv")
GSC = os.path.join(LOG, "gsc-queries.csv")
INBOX = os.path.join(LOG, "cowork-inbox")

VIEW_MIN_LEAK = 5
REACH_BASELINE = 500
UTILITY = {"/", "/index.html", "/contact", "/about", "/disclaimer", "/privacy",
           "/quiz", "/quiz.html", "/links", "/links.html"}


def _rows(path):
    if not os.path.exists(path):
        return []
    try:
        return list(csv.DictReader(open(path, encoding="utf-8")))
    except Exception:
        return []


def _i(r, k):
    try:
        return int(float(r.get(k, 0) or 0))
    except Exception:
        return 0


def _f(r, k):
    try:
        return float(r.get(k, 0) or 0)
    except Exception:
        return 0.0


def topic(path):
    s = (path or "/").split("?")[0].strip("/")
    s = s.replace(".html", "").replace("-2026", "")
    if not s:
        return "(home)"
    return s.replace("-", " ")


def main():
    ts = datetime.datetime.now().strftime("%Y%m%d")
    src = _rows(GA4)
    pages = _rows(PAGES)
    gsc = _rows(GSC)

    tot_sess = sum(_i(r, "sessions") for r in src)
    tot_conv = sum(_i(r, "conversion") for r in src)
    tot_quiz = sum(_i(r, "quiz_start") for r in src)
    cvr = (100.0 * tot_conv / tot_sess) if tot_sess else 0.0

    for r in src:
        r["_conv"] = _i(r, "conversion")
        r["_sess"] = _i(r, "sessions")
        r["_cvr"] = (100.0 * r["_conv"] / r["_sess"]) if r["_sess"] else 0.0
    src_rank = sorted(src, key=lambda r: (-r["_conv"], -r["_cvr"]))

    winners = sorted([r for r in pages if _i(r, "conversion") > 0],
                     key=lambda r: (-_i(r, "conversion"), -_i(r, "views")))
    leaks = sorted([r for r in pages if _i(r, "views") >= VIEW_MIN_LEAK and _i(r, "conversion") == 0
                    and (r.get("page", "").split("?")[0] not in UTILITY)],
                   key=lambda r: -_i(r, "views"))

    strike = []
    top_q = []
    if gsc:
        for r in gsc:
            r["_pos"] = _f(r, "position")
            r["_imp"] = _i(r, "impressions")
            r["_clk"] = _i(r, "clicks")
        strike = sorted([r for r in gsc if 5.5 <= r["_pos"] <= 20.5 and r["_imp"] >= 5],
                        key=lambda r: -r["_imp"])[:8]
        top_q = sorted(gsc, key=lambda r: -r["_clk"])[:8]

    out = os.path.join(LOG, "weekly-growth-%s.md" % ts)
    L = []
    L.append("# Weekly Growth Review — %s" % ts)
    L.append("")
    L.append("**ภาพรวม 28 วัน:** sessions=%d · conversion(affiliate_click)=%d · conv-rate=%.1f%% · quiz_start=%d"
             % (tot_sess, tot_conv, cvr, tot_quiz))
    if tot_sess < REACH_BASELINE:
        L.append("")
        L.append("> ยัง cold-start (sessions < %d) — โฟกัส distribution (Threads/social/SEO index) ก่อน "
                 "ตัวเลขจะแม่นขึ้นเมื่อทราฟฟิกเยอะพอ" % REACH_BASELINE)
    L.append("")

    L.append("## ช่องที่แปลงดี (ทุ่มเพิ่ม)")
    if src_rank:
        L.append("| # | ช่อง | sessions | conv | conv-rate |")
        L.append("|--|--|--|--|--|")
        for i, r in enumerate(src_rank[:8], 1):
            L.append("| %d | %s | %d | %d | %.1f%% |" % (i, r.get("source", "?"), r["_sess"], r["_conv"], r["_cvr"]))
        best = src_rank[0]
        L.append("")
        L.append("ทำต่อ: ช่อง %s แปลงดีสุด (%d conv) — เพิ่มความถี่/คอนเทนต์ช่องนี้ก่อน"
                 % (best.get("source", "?"), best["_conv"]))
    else:
        L.append("_ยังไม่มีข้อมูล GA4 — รัน ga4_pull.py_")
    L.append("")

    L.append("## บทความ winner (เขียนใกล้เคียง + ดันใน social)")
    if winners:
        L.append("| # | หน้า | views | conv |")
        L.append("|--|--|--|--|")
        for i, r in enumerate(winners[:6], 1):
            L.append("| %d | %s | %d | %d |" % (i, topic(r.get("page", "")), _i(r, "views"), _i(r, "conversion")))
        L.append("")
        L.append("ทำต่อ: เขียนบทความใกล้เคียง winner + ตั้งคิว Threads ดันหน้าเหล่านี้ซ้ำ (double-down)")
    else:
        L.append("_ยังไม่มีหน้าใดเกิด conversion_")
    L.append("")

    L.append("## หน้ารั่ว (คนเข้าแต่ไม่คลิก -> ปรับ CTA/intent)")
    if leaks:
        L.append("| # | หน้า | views | conv |")
        L.append("|--|--|--|--|")
        for i, r in enumerate(leaks[:6], 1):
            L.append("| %d | %s | %d | 0 |" % (i, topic(r.get("page", "")), _i(r, "views")))
        L.append("")
        L.append("ทำต่อ: หน้าเหล่านี้มีคนอ่านแต่ไม่คลิก — เช็ก CTA ตรง intent, เพิ่มปุ่ม above-the-fold, แมตช์ออฟเฟอร์ให้ตรงหัวข้อ")
    else:
        L.append("_ยังไม่พบหน้ารั่วชัดเจน (บทความ)_")
    L.append("")

    L.append("## SEO คีย์เวิร์ด (GSC)")
    if gsc:
        if strike:
            L.append("Striking distance (อันดับ 6-20 ดันขึ้นหน้า 1 ได้):")
            L.append("| คีย์เวิร์ด | imp | clicks | pos |")
            L.append("|--|--|--|--|")
            for r in strike:
                L.append("| %s | %d | %d | %.1f |" % (r.get("query", "?"), r["_imp"], r["_clk"], r["_pos"]))
            L.append("")
            L.append("ทำต่อ: ปรับ title/H2/เนื้อหา + internal link ตรงคีย์เหล่านี้ -> ดันขึ้นหน้า 1")
        if top_q:
            L.append("")
            L.append("คีย์ที่ได้คลิกจริง: " + ", ".join("%s(%d)" % (r.get("query", "?"), r["_clk"]) for r in top_q if r["_clk"] > 0)[:300])
    else:
        L.append("_ยังไม่มี gsc-queries.csv — รัน gsc_pull.py (เพิ่ม scope) หรือ export Performance จาก Search Console_")
    L.append("")
    L.append("---")
    L.append("_auto by weekly_growth_review.py · ข้อมูลจริง GA4/GSC · ไม่ใช่การเดา_")

    report = "\n".join(L)
    open(out, "w", encoding="utf-8").write(report)
    try:
        os.makedirs(INBOX, exist_ok=True)
        open(os.path.join(INBOX, "weekly-growth-%s.md" % ts), "w", encoding="utf-8").write(report)
    except Exception:
        pass
    try:
        sys.path.insert(0, HERE)
        import cc_bridge
        cc_bridge.ping("Weekly Growth Review ready -> weekly-growth-%s.md (winner -> double-down)" % ts)
    except Exception:
        pass
    print("weekly growth review ->", out, "| sessions=%d conv=%d" % (tot_sess, tot_conv))
    return out


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
