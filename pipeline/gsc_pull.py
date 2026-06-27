"""gsc_pull.py — ดึงคีย์เวิร์ดจริงจาก Google Search Console -> gsc-queries.csv
(ปิด loop ฝั่ง SEO: คีย์ไหนมา impression/click/อันดับเท่าไหร่ -> weekly_growth_review ชี้ "ดันขึ้นหน้า 1")

auth: ใช้ secrets/gsc-token.json (OAuth scope webmasters.readonly) ถ้ามี
      ไม่งั้นลอง secrets/ga4-token.json (อาจไม่มี scope GSC -> จะ fail บอกให้เพิ่ม scope)
ทางลัดไม่ต้อง auth: export Performance จาก Search Console เป็น CSV
      แล้ว save เป็น automation-log/gsc-queries.csv (คอลัมน์ query,clicks,impressions,ctr,position)
ปลอดภัย: อ่าน GSC อย่างเดียว + เขียน csv

property: เลือกอัตโนมัติจาก property ที่ verify จริง (prefer โดเมนหลัก ngernduangold.com
          -> sc-domain -> www; netlify.app เดิม ถูกตัดออก ไม่อ่านผิดโดเมน) override ได้ด้วย env GSC_SITE
"""
import os, sys, csv, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "automation-log", "gsc-queries.csv")
OUTP = os.path.join(ROOT, "automation-log", "gsc-pages.csv")
SITE = os.environ.get("GSC_SITE", "https://ngernduangold.com/")
DAYS = 28
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def _log(m):
    print("[%s] %s" % (datetime.datetime.now().isoformat(timespec="seconds"), m))


def _creds():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    for name in ("gsc-token.json", "ga4-token.json"):
        p = os.path.join(ROOT, "secrets", name)
        if os.path.exists(p):
            try:
                c = Credentials.from_authorized_user_file(p, SCOPES)
                if c and c.expired and c.refresh_token:
                    c.refresh(Request())
                _log("auth = %s" % name)
                return c
            except Exception as e:
                _log("token %s ใช้ไม่ได้กับ scope GSC (%s)" % (name, e))
    return None


def _resolve_site(svc):
    """เลือก GSC property ที่ถูกต้อง: prefer โดเมนหลัก -> sc-domain -> www (netlify.app เดิมไม่ใช้)
    ตามที่ verify จริงใน account (read-only sites.list). ถ้า .com ยังไม่ verify -> คืน None (ข้าม ไม่อ่านผิดโดเมน)."""
    prefer = []
    env = os.environ.get("GSC_SITE")
    if env:
        prefer.append(env)
    prefer += [
        "https://ngernduangold.com/",
        "sc-domain:ngernduangold.com",
        "https://www.ngernduangold.com/",
    ]
    # netlify.app (โดเมนเก่า) ตัดออกโดยตั้งใจ: automation ต้องไม่อ่านข้อมูลผิดโดเมน
    try:
        entries = svc.sites().list().execute().get("siteEntry", [])
        verified = {e.get("siteUrl") for e in entries
                    if e.get("permissionLevel") not in (None, "siteUnverifiedUser")}
        for cand in prefer:
            if cand in verified:
                return cand
        # ngernduangold.com ยังไม่ verify -> ห้าม fallback ไป netlify.app/property อื่น (กันอ่านผิดโดเมน)
        _log("ngernduangold.com ยังไม่ verify ใน GSC (verified=%s) — ข้ามการดึง GSC เพื่อไม่อ่านข้อมูลผิดโดเมน; ให้ owner verify .com ก่อน" % sorted(verified))
        return None
    except Exception as e:
        _log("list sites ไม่ได้ (%s) — ใช้ SITE ที่ตั้งไว้ (%s)" % (e, SITE))
    return SITE


def pull():
    try:
        from googleapiclient.discovery import build
    except Exception as e:
        _log("ยังไม่ได้ติดตั้ง -> pip install google-api-python-client google-auth (%s)" % e)
        return None
    creds = _creds()
    if creds is None:
        _log("ไม่มี token GSC. ทางเลือก: (1) auth เพิ่ม scope webmasters.readonly "
             "(2) export Performance จาก Search Console -> automation-log/gsc-queries.csv")
        return None
    try:
        svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
        site = _resolve_site(svc)
        if not site:
            _log("ไม่มี property ngernduangold.com ที่ verify — ข้าม (ไม่อ่าน netlify.app/ผิดโดเมน)")
            return None
        _log("GSC property = %s" % site)
        start = (datetime.date.today() - datetime.timedelta(days=DAYS)).isoformat()
        end = datetime.date.today().isoformat()
        body = {"startDate": start, "endDate": end, "dimensions": ["query"], "rowLimit": 200}
        resp = svc.searchanalytics().query(siteUrl=site, body=body).execute()
        rows = resp.get("rows", [])
        out = [("query", "clicks", "impressions", "ctr", "position")]
        for r in rows:
            q = (r.get("keys") or ["?"])[0]
            out.append((q, int(r.get("clicks", 0)), int(r.get("impressions", 0)),
                        round(r.get("ctr", 0) * 100, 2), round(r.get("position", 0), 1)))
        with open(OUT, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(out)
        _log("OK -> gsc-queries.csv | queries=%d" % (len(out) - 1))
        # page-dimension report -> gsc-pages.csv (top pages by impressions / indexed-but-weak)
        pages_n = 0
        try:
            pbody = {"startDate": start, "endDate": end, "dimensions": ["page"], "rowLimit": 200}
            presp = svc.searchanalytics().query(siteUrl=site, body=pbody).execute()
            pout = [("page", "clicks", "impressions", "ctr", "position")]
            for r in presp.get("rows", []):
                pg = (r.get("keys") or ["?"])[0]
                pout.append((pg, int(r.get("clicks", 0)), int(r.get("impressions", 0)),
                             round(r.get("ctr", 0) * 100, 2), round(r.get("position", 0), 1)))
            with open(OUTP, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(pout)
            pages_n = len(pout) - 1
            _log("OK -> gsc-pages.csv | pages=%d" % pages_n)
        except Exception as e:
            _log("page-dim pull ไม่สำเร็จ (%s) — ข้ามเฉพาะ gsc-pages.csv" % e)
        return {"file": OUT, "queries": len(out) - 1, "pages_file": OUTP, "pages": pages_n}
    except Exception as e:
        _log("ดึง GSC ล้มเหลว (%s) — เช็ก scope/สิทธิ์ property หรือใช้ export มือ" % e)
        return None


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    pull()
