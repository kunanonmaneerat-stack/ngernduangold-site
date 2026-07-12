#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# internal_link_sprint.py — WO-3 (decision D2, 2026-07-12)
# แกน: systematic in-body internal link จาก 55 บทความ -> หน้าเงิน (/debt-calculator, /kept-savings-2026, /links)
# GSC = ตัวช่วยจัดลำดับ (property ยังเด็ก ~7 rows) — API หลัก (pipeline/gsc_pull creds) · data/gsc/*.csv = fallback
#
# ความจริงของ repo: บทความเป็น f-string ฝังใน build_site.py (ART.append((slug,title,desc,body,faqs,camp)))
#   -> dry-run: parse source อ่าน body ตรง ๆ · --apply: anchored-replace ใน build_site.py (python I/O byte-safe)
#
# Usage:
#   python tools/seo/internal_link_sprint.py            dry-run -> automation-log/INTERNAL-LINK-PLAN.md
#   python tools/seo/internal_link_sprint.py --apply    แทรกจริงตามแผน (รันหลัง Cowork/เจ้าของรีวิวแผนแล้วเท่านั้น)
#
# กติกา apply: แทรก "ประโยคลิงก์ contextual" ต่อท้ายย่อหน้า host ที่เลือก (ไม่ใช่ spam ท้ายบทความ) ·
#   ข้ามบทความที่ in-body มีลิงก์ target นั้นแล้ว · ทุก <a> มี title · ไม่มี { } ในข้อความแทรก (กัน f-string พัง) ·
#   หลังแก้: py_compile + UFFFD ต้องเท่าเดิม + .bak ไว้กู้
import io, os, re, sys, csv, glob, shutil, argparse, datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BS = os.path.join(ROOT, "build_site.py")
PLAN = os.path.join(ROOT, "automation-log", "INTERNAL-LINK-PLAN.md")
GSC_DIR = os.path.join(ROOT, "data", "gsc")

# หน้าเงิน (ตาม D2) + คีย์เวิร์ดจับบริบท + anchor 3 แบบหมุนเวียน (เลี่ยง anchor ซ้ำทั้งไซต์)
TARGETS = [
    ("/debt-calculator", ["หนี้", "ผ่อน", "โปะ", "ปลดหนี้", "ขั้นต่ำ", "ค่างวด", "สินเชื่อ"],
     [("เครื่องคำนวณแผนปลดหนี้ฟรี", "คำนวณหนี้มนุษย์เงินเดือน เห็นเดือนปลอดหนี้"),
      ("ลองคำนวณแผนปลดหนี้ของคุณ", "เครื่องคำนวณปลดหนี้ Snowball/Avalanche ฟรี"),
      ("วางแผนปลดหนี้ด้วยตัวเลขจริง", "เครื่องคำนวณแผนปลดหนี้ ไม่เก็บข้อมูล")],
     "ลองกรอกหนี้ของคุณใน{A}ดูก่อน — เห็นเดือนปลอดหนี้ชัด ๆ แล้วค่อยตัดสินใจก้าวต่อไป"),
    ("/kept-savings-2026", ["ออม", "เงินสำรอง", "ดอกเบี้ยสูง", "ฝาก", "เงินเก็บ", "เงินเย็น"],
     [("บัญชีออมดอกสูงที่ถอนได้ไว", "รีวิวบัญชีเงินฝากดอกเบี้ยสูง Kept 2026"),
      ("ที่พักเงินสำรองแบบถอนได้ทันที", "บัญชีออมดอกสูง เปิดฟรี"),
      ("เปิดบัญชีออมดอกสูง", "เงินสำรองฉุกเฉินควรอยู่ที่ไหน")],
     "ระหว่างทาง อย่าลืมกันเงินสำรองฉุกเฉินไว้ใน{A} — บิลด่วนมาจะได้ไม่ต้องกลับไปกู้"),
    ("/links", ["สมัคร", "เปรียบเทียบ", "ตัวเลือก", "รวม", "โปรโมชัน", "ผู้ให้บริการ"],
     [("หน้ารวมลิงก์ทางการของเรา", "รวมลิงก์สมัคร/เปรียบเทียบทุกผลิตภัณฑ์ที่เรารีวิว"),
      ("ลิงก์รวมทุกตัวเลือกที่รีวิวไว้", "หน้ารวมลิงก์ เงินเดือนสมองทอง"),
      ("ดูตัวเลือกทั้งหมดที่คัดไว้", "ลิงก์รวมทางการ ngernduangold")],
     "ตัวเลือกทั้งหมดที่เรารีวิวและคัดแล้ว รวมอยู่ที่{A} อัปเดตอยู่เสมอ"),
]

ART_RE = re.compile(r'slug(\w+)\s*=\s*"([^"]+\.html)"')
BODY_RE = 'body%s=f"""'


WINNER_EXCLUDE = {"kept-savings-2026.html", "title-loan-2026.html", "debt-consolidation-2026.html"}


def load_articles(src):
    arts, seen = [], set()
    for m in ART_RE.finditer(src):
        n, slug = m.group(1), m.group(2)
        if slug in seen or slug in WINNER_EXCLUDE:
            continue
        seen.add(slug)
        key = BODY_RE % n
        i = src.find(key)
        if i < 0:
            continue
        j = src.find('"""', i + len(key))
        arts.append({"n": n, "slug": slug, "body": src[i + len(key):j]})
    return arts


def gsc_hints():
    """query->page hints เพื่อจัดลำดับ (API ก่อน, CSV fallback) — ล้มเหลว = เดินต่อแบบไม่มี hint"""
    hints = {}
    try:
        sys.path.insert(0, os.path.join(ROOT, "pipeline"))
        import gsc_pull as G
        from googleapiclient.discovery import build
        svc = build("searchconsole", "v1", credentials=G._creds(), cache_discovery=False)
        site = G._resolve_site(svc)
        end = datetime.date.today().isoformat()
        start = (datetime.date.today() - datetime.timedelta(days=28)).isoformat()
        rows = svc.searchanalytics().query(siteUrl=site, body={
            "startDate": start, "endDate": end, "dimensions": ["query", "page"],
            "rowLimit": 500}).execute().get("rows", [])
        for r in rows:
            page = r["keys"][1].split("ngernduangold.com/")[-1].split("?")[0]
            page = page if page.endswith(".html") else page + ".html"
            hints.setdefault(page, []).append((r["keys"][0], round(r.get("position", 0), 1),
                                               int(r.get("impressions", 0))))
        print("[gsc] live API: %d rows" % len(rows))
        return hints
    except Exception as e:
        print("[gsc] API unavailable (%s) — CSV fallback" % str(e)[:60])
    for f in glob.glob(os.path.join(GSC_DIR, "queries-*.csv")) + glob.glob(os.path.join(GSC_DIR, "*.csv")):
        try:
            with io.open(f, encoding="utf-8-sig") as fh:
                for row in csv.DictReader(fh):
                    q = row.get("Top queries") or row.get("Query") or row.get("query") or ""
                    pos = float(row.get("Position") or row.get("position") or 0)
                    imp = int(float(row.get("Impressions") or row.get("impressions") or 0))
                    if q:
                        hints.setdefault("*", []).append((q, pos, imp))
        except Exception:
            pass
    return hints


def choose_host_paragraph(body, keywords, taken):
    """เลือกย่อหน้า host: <p>...</p> แรก ๆ ที่มีคีย์เวิร์ด และยังไม่ถูกใช้แทรกอย่างอื่น"""
    for m in re.finditer(r"<p>(.{40,400}?)</p>", body, re.S):
        text = re.sub(r"<[^>]+>", "", m.group(1))
        if m.group(0) in taken:
            continue
        if any(k in text for k in keywords):
            return m.group(0), text
    return None, None


def build_plan(arts, hints):
    plan = []
    anchor_i = {t[0]: 0 for t in TARGETS}
    for art in arts:
        body, slug = art["body"], art["slug"]
        taken = set()
        for target, kws, anchors, template in TARGETS:
            if slug.replace(".html", "") == target.lstrip("/"):
                continue  # ห้าม self-link
            forms = (target, target + ".html", target.replace("/", "", 1))
            if any(('href="%s"' % f) in body or ('href="%s?' % f) in body or ('href="%s.html' % target) in body
                   for f in forms):
                continue  # in-body มีลิงก์ target นี้แล้ว
            host, text = choose_host_paragraph(body, kws, taken)
            if not host:
                continue
            taken.add(host)
            ai = anchor_i[target] % len(anchors)
            anchor_i[target] += 1
            anchor, title = anchors[ai]
            a_html = '<a href="%s" title="%s">%s</a>' % (target, title, anchor)
            sentence = " " + template.replace("{A}", a_html)
            q = ""
            for query, pos, imp in hints.get(slug, [])[:1]:
                q = "%s (pos %.0f, imp %d)" % (query, pos, imp)
            plan.append({"slug": slug, "n": art["n"], "target": target, "anchor": anchor,
                         "query": q, "host": host, "host_text": text[:60],
                         "insert": host + sentence})
    return plan


def write_plan_md(plan, arts):
    per_art = {}
    for p in plan:
        per_art.setdefault(p["slug"], []).append(p)
    lines = ["# INTERNAL-LINK-PLAN — WO-3 dry-run · %s" % datetime.date.today().isoformat(), "",
             "แกน: in-body contextual link จาก 55 บทความ -> หน้าเงิน 3 หน้า (D2) · GSC = จัดลำดับ",
             "รวมข้อเสนอ: **%d ลิงก์ ใน %d บทความ** (จาก %d บทความทั้งหมด)" % (len(plan), len(per_art), len(arts)),
             "กติกา apply: แทรกประโยคต่อท้ายย่อหน้า host (contextual) · anchor หมุน 3 แบบ/เป้า · ทุกลิงก์มี title", "",
             "| บทความ | query (GSC) | anchor | ปลายทาง | แทรกหลังย่อหน้า (ต้น 60 ตัวอักษร) |",
             "|---|---|---|---|---|"]
    for p in plan:
        lines.append("| %s | %s | %s | `%s` | %s… |" % (
            p["slug"].replace(".html", ""), p["query"] or "-", p["anchor"], p["target"], p["host_text"]))
    lines += ["", "## ประโยคที่จะแทรก (ตัวอย่าง 3 แบบตามเป้า)",
              "- calc: “ลองกรอกหนี้ของคุณใน**[anchor]**ดูก่อน — เห็นเดือนปลอดหนี้ชัด ๆ แล้วค่อยตัดสินใจก้าวต่อไป”",
              "- kept: “ระหว่างทาง อย่าลืมกันเงินสำรองฉุกเฉินไว้ใน**[anchor]** — บิลด่วนมาจะได้ไม่ต้องกลับไปกู้”",
              "- links: “ตัวเลือกทั้งหมดที่เรารีวิวและคัดแล้ว รวมอยู่ที่**[anchor]** อัปเดตอยู่เสมอ”",
              "", "รีวิวแล้วสั่ง `--apply` เพื่อแทรกจริง (anchored-replace ใน build_site.py + build + gates + push)"]
    io.open(PLAN, "w", encoding="utf-8").write(chr(10).join(lines) + chr(10))


def apply_plan(plan, src):
    n_ufffd = src.count(chr(0xFFFD))
    shutil.copy(BS, BS + ".bak_linksprint")
    applied = 0
    for p in plan:
        if src.count(p["host"]) != 1:
            print("SKIP %s -> %s (host paragraph ไม่ unique: %d)" % (p["slug"], p["target"], src.count(p["host"])))
            continue
        src = src.replace(p["host"], p["insert"], 1)
        applied += 1
    assert src.count(chr(0xFFFD)) == n_ufffd, "mojibake introduced"
    assert "{A}" not in src
    io.open(BS, "w", encoding="utf-8").write(src)
    import py_compile
    py_compile.compile(BS, doraise=True)
    print("APPLIED %d/%d links | py_compile OK | backup: build_site.py.bak_linksprint" % (applied, len(plan)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    src = io.open(BS, encoding="utf-8").read()
    arts = load_articles(src)
    print("articles parsed: %d" % len(arts))
    hints = gsc_hints()
    plan = build_plan(arts, hints)
    if not a.apply:
        write_plan_md(plan, arts)
        n_arts = len({p["slug"] for p in plan})
        print("DRY-RUN: %d links across %d articles -> %s" % (len(plan), n_arts, PLAN))
        return 0
    apply_plan(plan, src)
    return 0


if __name__ == "__main__":
    sys.exit(main())
