"""gsc_pull.py — ดึงคีย์เวิร์ดจริงจาก Google Search Console -> gsc-queries.csv
(ปิด loop ฝั่ง SEO: คีย์ไหนมา impression/click/อันดับเท่าไหร่ -> weekly_growth_review ชี้ "ดันขึ้นหน้า 1")

auth: ใช้ secrets/gsc-token.json (OAuth scope webmasters.readonly) ถ้ามี
      ไม่งั้นลอง secrets/ga4-token.json (อาจไม่มี scope GSC -> จะ fail บอกให้เพิ่ม scope)
ทางลัดไม่ต้อง auth: export Performance จาก Search Console เป็น CSV
      แล้ว save เป็น automation-log/gsc-queries.csv (คอลัมน์ query,clicks,impressions,ctr,position)
ปลอดภัย: อ่าน GSC อย่างเดียว + เขียน csv
"""
import os, sys, csv, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "automation-log", "gsc-queries.csv")
SITE = os.environ.get("GSC_SITE", "https://ngernduangold.netlify.app/")
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
        start = (datetime.date.today() - datetime.timedelta(days=DAYS)).isoformat()
        end = datetime.date.today().isoformat()
        body = {"startDate": start, "endDate": end, "dimensions": ["query"], "rowLimit": 200}
        resp = svc.searchanalytics().query(siteUrl=SITE, body=body).execute()
        rows = resp.get("rows", [])
        out = [("query", "clicks", "impressions", "ctr", "position")]
        for r in rows:
            q = (r.get("keys") or ["?"])[0]
            out.append((q, int(r.get("clicks", 0)), int(r.get("impressions", 0)),
                        round(r.get("ctr", 0) * 100, 2), round(r.get("position", 0), 1)))
        with open(OUT, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(out)
        _log("OK -> gsc-queries.csv | queries=%d" % (len(out) - 1))
        return {"file": OUT, "queries": len(out) - 1}
    except Exception as e:
        _log("ดึง GSC ล้มเหลว (%s) — เช็ก scope/สิทธิ์ property หรือใช้ export มือ" % e)
        return None


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    pull()
