"""Weekly GA4 intent diagnostics plus GSC discovery signals.

Affiliate clicks are not conversions or revenue.  GA4 trust gates every
decision, and even trusted clicks cannot authorize scaling without confirmed
commission evidence from the money ledger.
ใช้:  py pipeline/weekly_growth_review.py
"""
import argparse, os, sys, csv, datetime
try:
    from ga4_schema import affiliate_click
except ImportError:
    from pipeline.ga4_schema import affiliate_click
try:
    import decision_readiness
except ImportError:  # package import path
    from pipeline import decision_readiness
try:
    import report_trust_guard
except ImportError:  # package import path
    from pipeline import report_trust_guard

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOG = os.path.join(ROOT, "automation-log")
GA4 = os.path.join(LOG, "ga4-metrics.csv")
PAGES = os.path.join(LOG, "ga4-pages.csv")
GSC = os.path.join(LOG, "gsc-queries.csv")
GSCP = os.path.join(LOG, "gsc-pages.csv")
INBOX = os.path.join(LOG, "cowork-inbox")
POLICY = os.path.join(ROOT, ".system_control", "policy.json")
HOST_IP = os.path.join(ROOT, ".system_control", "host_ip.json")

VIEW_MIN_LEAK = 5
UTILITY = {"/", "/index.html", "/contact", "/about", "/disclaimer", "/privacy",
           "/quiz", "/quiz.html", "/links", "/links.html"}


def _rows(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as source:
            return list(csv.DictReader(source))
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


def _decision_readiness():
    return decision_readiness.read()


def _write_atomic(path, text):
    """Write one complete report or leave the previous file untouched."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    temporary = "%s.tmp.%d" % (path, os.getpid())
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as destination:
            destination.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def main():
    ts = datetime.datetime.now().strftime("%Y%m%d")
    readiness = _decision_readiness()
    trust = readiness.ga4
    gsc_trust = readiness.gsc
    ga4_trusted = bool(trust.trusted)
    gsc_trusted = bool(gsc_trust.trusted)
    trust_label = trust.label
    trust_reason = trust.reason
    trust_schema = trust.schema
    src = _rows(GA4)
    pages = _rows(PAGES)
    gsc = _rows(GSC)
    gscp = _rows(GSCP)

    tot_sess = sum(_i(r, "sessions") for r in src)
    tot_clicks = sum(affiliate_click(r) for r in src)
    tot_quiz = sum(_i(r, "quiz_start") for r in src)
    # affiliate_click is an event count, while sessions is a session count.
    # Their ratio is an event-density diagnostic and can legitimately exceed
    # 100; calling it a click/conversion rate would mix grains and imply a
    # unique-session numerator that this export does not contain.
    click_events_per_100_sessions = (
        100.0 * tot_clicks / tot_sess if tot_sess else 0.0
    )

    for r in src:
        r["_intent"] = affiliate_click(r)
        r["_sess"] = _i(r, "sessions")
        r["_event_density"] = (
            100.0 * r["_intent"] / r["_sess"] if r["_sess"] else 0.0
        )
    src_rank = sorted(src, key=lambda r: (-r["_intent"], -r["_event_density"]))

    clicked_pages = sorted([r for r in pages if affiliate_click(r) > 0],
                           key=lambda r: (-affiliate_click(r), -_i(r, "views")))
    leaks = sorted([r for r in pages if _i(r, "views") >= VIEW_MIN_LEAK and affiliate_click(r) == 0
                    and (r.get("page", "").split("?")[0] not in UTILITY)],
                   key=lambda r: -_i(r, "views"))

    strike = []
    top_q = []
    top_pages_imp = []
    weak_pages = []
    if gsc and gsc_trusted:
        for r in gsc:
            r["_pos"] = _f(r, "position")
            r["_imp"] = _i(r, "impressions")
            r["_clk"] = _i(r, "clicks")
        # near-ranking / striking distance: อันดับ ~5-20, impression>0 (หนึ่งก้าวจากหน้า 1)
        strike = sorted([r for r in gsc if 5.0 <= r["_pos"] <= 20.0 and r["_imp"] >= 1],
                        key=lambda r: -r["_imp"])[:10]
        top_q = sorted(gsc, key=lambda r: -r["_clk"])[:8]
    if gscp and gsc_trusted:
        for r in gscp:
            r["_pos"] = _f(r, "position")
            r["_imp"] = _i(r, "impressions")
            r["_clk"] = _i(r, "clicks")
        top_pages_imp = sorted([r for r in gscp if r["_imp"] >= 1], key=lambda r: -r["_imp"])[:8]
        weak_pages = sorted([r for r in gscp if r["_imp"] >= 1 and r["_pos"] > 20.0],
                            key=lambda r: -r["_imp"])[:8]

    out = os.path.join(LOG, "weekly-growth-%s.md" % ts)
    L = []
    L.append("# Weekly Growth Review — %s" % ts)
    L.append("")
    L.extend(report_trust_guard.canonical_block(readiness))
    L.append(
        "**ภาพรวม 28 วัน [source=GA4 state=%s]:** sessions=%d · affiliate_click(intent events)=%d · "
        "affiliate_click events/100 sessions=%.1f · quiz_start=%d"
        % (
            "READY" if ga4_trusted else "BLOCKED",
            tot_sess,
            tot_clicks,
            click_events_per_100_sessions,
            tot_quiz,
        )
    )
    L.append("")
    L.append("## GA4 Decision Trust — %s" % trust_label)
    L.append("")
    if ga4_trusted:
        L.append("> TRUSTED — %s (schema: %s)" % (trust_reason, trust_schema))
    else:
        L.append("> **UNTRUSTED — %s**" % trust_reason)
        L.append("> DECISION BLOCK: แสดงตัวเลขเพื่อวินิจฉัยเท่านั้น ห้ามใช้เป็นคำสั่งขยายผลหรือเปลี่ยน cadence รอบนี้")
    L.append("")

    L.append("## affiliate_click รายช่อง (intent signal ไม่ใช่รายได้)" if ga4_trusted
             else "## affiliate_click ตามข้อมูล GA4 ดิบ (UNTRUSTED — ไม่จัดอันดับผู้ชนะ)")
    if src_rank:
        L.append("| # | ช่อง | sessions | affiliate_click events | events/100 sessions |")
        L.append("|--|--|--|--|--|")
        for i, r in enumerate(src_rank[:8], 1):
            density = ("%.1f" % r["_event_density"]) if r["_sess"] >= 10 else "— (n ต่ำ)"
            L.append("| %d | %s | %d | %d | %s |" %
                     (i, r.get("source", "?"), r["_sess"], r["_intent"], density))
        L.append("")
        if ga4_trusted:
            L.append("คำตัดสิน [basis=GA4]: ใช้ได้เฉพาะวินิจฉัย intent; ห้ามเลือก revenue winner หรือ scale "
                     "จนกว่าจะมี paid affiliate commission ที่ผูกกับ source/content")
        else:
            L.append("การตัดสินใจ: BLOCKED — ห้ามเลือกช่องชนะหรือเปลี่ยน cadence จน GA4 Decision Trust = TRUSTED")
    else:
        L.append("_ยังไม่มีข้อมูล GA4 — รัน ga4_pull.py_")
    L.append("")

    L.append("## หน้าที่มี affiliate_click (intent signal)" if ga4_trusted
             else "## หน้าที่มี affiliate_click ตาม GA4 ดิบ (UNTRUSTED)")
    if clicked_pages:
        L.append("| # | หน้า | views | affiliate_click |")
        L.append("|--|--|--|--|")
        for i, r in enumerate(clicked_pages[:6], 1):
            L.append("| %d | %s | %d | %d |" % (i, topic(r.get("page", "")), _i(r, "views"), affiliate_click(r)))
        L.append("")
        if ga4_trusted:
            L.append("ทำต่อ [basis=GA4]: ตรวจว่า intent ผูกถึง approved commission ได้หรือไม่; ห้ามดันซ้ำจากคลิกอย่างเดียว")
        else:
            L.append("การตัดสินใจ: BLOCKED — ห้ามสร้างบทความเลียนแบบหรือดันซ้ำจาก GA4 ชุดนี้")
    else:
        L.append("_ยังไม่มีหน้าใดเกิด affiliate_click_")
    L.append("")

    L.append("## หน้าที่มี views แต่ affiliate_click=0 (ผู้สมัครตรวจ CTA/intent)" if ga4_trusted
             else "## หน้า views แต่ affiliate_click=0 ตามข้อมูล GA4 ดิบ (UNTRUSTED)")
    if leaks:
        L.append("| # | หน้า | views | affiliate_click |")
        L.append("|--|--|--|--|")
        for i, r in enumerate(leaks[:6], 1):
            L.append("| %d | %s | %d | 0 |" % (i, topic(r.get("page", "")), _i(r, "views")))
        L.append("")
        if ga4_trusted:
            L.append("ทำต่อ [basis=GA4]: หน้าเหล่านี้มีคนอ่านแต่ไม่คลิก — เช็ก CTA ตรง intent, เพิ่มปุ่ม above-the-fold, แมตช์ออฟเฟอร์ให้ตรงหัวข้อ")
        else:
            L.append("การตัดสินใจ: BLOCKED — ห้ามแก้ CTA/intent จาก GA4 จนยืนยัน internal-traffic coverage")
    else:
        if ga4_trusted:
            L.append("_ยังไม่พบหน้ารั่วชัดเจน [basis=GA4] (บทความ)_")
        else:
            L.append("_GA4 BLOCKED — ไม่สรุปหน้ารั่วจากข้อมูลชุดนี้_")
    L.append("")

    L.append("## SEO คีย์เวิร์ด (GSC)")
    if not gsc_trusted:
        L.append("> **DECISION BLOCK — %s**" % gsc_trust.reason)
        L.append("_อาจแสดงไฟล์ดิบเพื่อตรวจระบบได้ แต่ห้ามเลือกคีย์หรือสั่งปรับ SEO จน bundle 28 วันผ่าน_")
    elif gsc:
        if strike:
            L.append("Striking distance [basis=GSC] — คีย์ใกล้ขึ้นหน้า 1 (อันดับ ~5-20, impression>0):")
            L.append("| คีย์เวิร์ด | imp | clicks | pos |")
            L.append("|--|--|--|--|")
            for r in strike:
                L.append("| %s | %d | %d | %.1f |" % (r.get("query", "?"), r["_imp"], r["_clk"], r["_pos"]))
            L.append("")
            L.append("ทำต่อ [basis=GSC]: ปรับ title/H2/เนื้อหา + internal link ตรงคีย์เหล่านี้ -> ดันขึ้นหน้า 1")
        if top_q:
            L.append("")
            L.append("คีย์ที่ได้คลิกจริง: " + ", ".join("%s(%d)" % (r.get("query", "?"), r["_clk"]) for r in top_q if r["_clk"] > 0)[:300])
    elif os.path.exists(GSC):
        L.append("_ดึง GSC สำเร็จแล้ว (property ngernduangold.com) แต่ยังไม่มีแถวคีย์เวิร์ด — property เพิ่ง verify + GSC latency ~2-3 วัน ข้อมูลจะทยอยมาใน ~1 สัปดาห์_")
    else:
        L.append("_ยังไม่มี gsc-queries.csv — รัน gsc_pull.py (เพิ่ม scope) หรือ export Performance จาก Search Console_")
    L.append("")

    L.append("## SEO หน้าเว็บ (GSC page-level)")
    if not gsc_trusted:
        L.append("> **DECISION BLOCK — %s**" % gsc_trust.reason)
    elif gscp:
        if top_pages_imp:
            L.append("หน้าได้ impression สูงสุด [basis=GSC] (โอกาสทราฟฟิก — ดันต่อ):")
            L.append("| หน้า | imp | clicks | pos |")
            L.append("|--|--|--|--|")
            for r in top_pages_imp:
                L.append("| %s | %d | %d | %.1f |" % (topic(r.get("page", "")), r["_imp"], r["_clk"], r["_pos"]))
            L.append("")
        if weak_pages:
            L.append("หน้า indexed แต่ยังอ่อน [basis=GSC] (impression>0, อันดับ >20 -> เสริมเนื้อหา/internal link):")
            L.append("| หน้า | imp | clicks | pos |")
            L.append("|--|--|--|--|")
            for r in weak_pages:
                L.append("| %s | %d | %d | %.1f |" % (topic(r.get("page", "")), r["_imp"], r["_clk"], r["_pos"]))
            L.append("")
            L.append("ทำต่อ [basis=GSC]: Google เห็นหน้าเหล่านี้แล้วแต่อันดับยังต่ำ — เพิ่ม internal link จากหน้าอื่น + เสริมเนื้อหา/คีย์ที่ตรง")
        if not top_pages_imp and not weak_pages:
            L.append("_gsc-pages.csv ยังไม่มีแถว (property เพิ่ง verify / GSC latency ~2-3 วัน) — กลับมาดูใน ~1 สัปดาห์_")
    elif os.path.exists(GSCP):
        L.append("_ดึง GSC page-level สำเร็จแล้วแต่ยังไม่มีแถว — property เพิ่ง verify + GSC latency ~2-3 วัน กลับมาดูใน ~1 สัปดาห์_")
    else:
        L.append("_ยังไม่มี gsc-pages.csv — รัน gsc_pull.py (ดึง page dimension)_")
    L.append("")
    L.append("---")
    # Do not restate mixed source states on one prose line.  A READY token for
    # one source can otherwise look like it promotes a different BLOCKED
    # source on the same line, and Markdown's closing underscore also breaks
    # exact blocked-state token boundaries.  The canonical block above is the
    # sole machine-readable state authority.
    L.append(
        "_auto by weekly_growth_review.py · canonical evidence states are bound above_"
    )

    report = "\n".join(L)
    trust_errors = report_trust_guard.validate_report(report, readiness)
    if trust_errors:
        raise RuntimeError(
            "weekly report contradicted canonical evidence: %s"
            % "; ".join(trust_errors)
        )
    _write_atomic(out, report)
    _write_atomic(os.path.join(INBOX, "weekly-growth-%s.md" % ts), report)
    print(
        "weekly growth review ->",
        out,
        "| sessions=%d affiliate_click=%d ga4_trust=%s" % (tot_sess, tot_clicks, trust_label),
    )
    return out


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-only", action="store_true",
                        help="explicitly document the scheduled local-only posture")
    parser.parse_args()
    main()
