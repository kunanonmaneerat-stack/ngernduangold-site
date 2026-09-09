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
import argparse, os, sys, csv, datetime, hashlib, json, math, tempfile, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "automation-log", "gsc-queries.csv")
OUTP = os.path.join(ROOT, "automation-log", "gsc-pages.csv")
OUT_SNAPSHOT = os.path.join(ROOT, "automation-log", "gsc-snapshot.json")
SITE = os.environ.get("GSC_SITE", "https://ngernduangold.com/")
DAYS = 28
BANGKOK = datetime.timezone(datetime.timedelta(hours=7))
ROW_LIMIT = 25_000
FINALIZATION_LAG_DAYS = 3
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


class ProducerBlocked(RuntimeError):
    """A known credential/property/dependency prerequisite is unavailable."""


class ProducerRunnerFailed(RuntimeError):
    """The producer failed during API, validation, or local persistence work."""


def _date_window(today=None, days=DAYS, lag_days=FINALIZATION_LAG_DAYS):
    """Return a finalized inclusive window ending ``lag_days`` before today."""
    if not isinstance(days, int) or days < 1:
        raise ValueError("days must be a positive integer")
    if not isinstance(lag_days, int) or lag_days < 0:
        raise ValueError("lag_days must be a non-negative integer")
    current = today or datetime.date.today()
    if not isinstance(current, datetime.date):
        raise TypeError("today must be a date")
    end = current - datetime.timedelta(days=lag_days)
    start = end - datetime.timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def _capture_context(now=None):
    captured = now or datetime.datetime.now().astimezone()
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("capture time must be timezone-aware")
    captured = captured.astimezone(BANGKOK)
    start, end = _date_window(captured.date())
    return {
        "captured_at": captured.astimezone(datetime.timezone.utc).isoformat(timespec="seconds"),
        "window_start": start,
        "window_end": end,
        "window_days": DAYS,
        "finalization_lag_days": FINALIZATION_LAG_DAYS,
    }


def _log(m):
    print("[%s] %s" % (datetime.datetime.now().isoformat(timespec="seconds"), m))


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _finite_number(value, label, *, minimum=None, maximum=None):
    if isinstance(value, bool) or value is None:
        raise ValueError("%s must be numeric" % label)
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("%s must be numeric" % label) from None
    if not math.isfinite(number):
        raise ValueError("%s must be finite" % label)
    if minimum is not None and number < minimum:
        raise ValueError("%s is below its valid range" % label)
    if maximum is not None and number > maximum:
        raise ValueError("%s is above its valid range" % label)
    return number


def _nonnegative_int(value, label):
    number = _finite_number(value, label, minimum=0)
    if not number.is_integer():
        raise ValueError("%s must be an integer" % label)
    return int(number)


def _normal_query(value):
    if not isinstance(value, str):
        raise ValueError("GSC query key must be text")
    normalized = unicodedata.normalize("NFKC", value)
    normalized = " ".join(normalized.strip().split()).casefold()
    if not normalized:
        raise ValueError("GSC query key must not be empty")
    return normalized


def _normal_page(value):
    if not isinstance(value, str):
        raise ValueError("GSC page key must be text")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized:
        raise ValueError("GSC page key must not be empty")
    return normalized


def _aggregate_rows(rows, dimension):
    """Validate and aggregate possibly duplicated Search Console rows.

    Position is impression-weighted and CTR is recomputed from the aggregate;
    averaging the API row percentages would bias small duplicate rows.
    """
    if dimension not in ("query", "page"):
        raise ValueError("unsupported GSC dimension")
    if rows is None:
        raise ValueError("GSC response has no rows collection")
    try:
        source_rows = list(rows)
    except TypeError:
        raise ValueError("GSC rows are malformed") from None
    normalize = _normal_query if dimension == "query" else _normal_page
    aggregate = {}
    for index, row in enumerate(source_rows):
        if not isinstance(row, dict):
            raise ValueError("GSC %s row %d must be an object" % (dimension, index))
        keys = row.get("keys")
        if not isinstance(keys, list) or len(keys) != 1:
            raise ValueError("GSC %s row %d has malformed keys" % (dimension, index))
        key = normalize(keys[0])
        clicks = _nonnegative_int(row.get("clicks"), "GSC clicks")
        impressions = _nonnegative_int(row.get("impressions"), "GSC impressions")
        ctr = _finite_number(row.get("ctr"), "GSC ctr", minimum=0, maximum=1)
        position = _finite_number(row.get("position"), "GSC position", minimum=0)
        if clicks > impressions:
            raise ValueError("GSC clicks cannot exceed impressions")
        if impressions == 0:
            if clicks or ctr or position:
                raise ValueError("GSC zero-impression row has non-zero metrics")
        elif abs(ctr - (clicks / impressions)) > 0.000001:
            raise ValueError("GSC ctr is inconsistent with clicks/impressions")
        item = aggregate.setdefault(key, {
            "clicks": 0, "impressions": 0, "position_weight": 0.0,
        })
        item["clicks"] += clicks
        item["impressions"] += impressions
        item["position_weight"] += position * impressions

    output = []
    for key in sorted(aggregate):
        item = aggregate[key]
        impressions = item["impressions"]
        ctr_pct = (item["clicks"] / impressions * 100) if impressions else 0.0
        position = (item["position_weight"] / impressions) if impressions else 0.0
        output.append((key, item["clicks"], impressions,
                       round(ctr_pct, 2), round(position, 1)))
    return output, {
        "api_rows": len(source_rows),
        "output_rows": len(output),
        "duplicate_rows_collapsed": len(source_rows) - len(output),
    }


def _atomic_csv(path, rows):
    selected = os.path.abspath(path)
    directory = os.path.dirname(selected)
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=os.path.basename(selected) + "-", suffix=".tmp",
                                     dir=directory)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, selected)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _write_snapshot_metadata(start=None, end=None, coverage=None, *, context=None,
                             files=None, output_path=None):
    capture = context or _capture_context()
    if start is not None or end is not None:
        if not isinstance(start, str) or not isinstance(end, str):
            raise ValueError("GSC snapshot window must provide both endpoints")
        capture = dict(capture, window_start=start, window_end=end)
    if not isinstance(coverage, dict) or set(coverage) != {"queries", "pages"}:
        raise ValueError("GSC snapshot coverage is incomplete")
    selected_files = files or {"queries": OUT, "pages": OUTP}
    if set(selected_files) != {"queries", "pages"}:
        raise ValueError("GSC snapshot requires query and page files")
    site_url = str(capture.get("site_url") or "").strip()
    if not site_url:
        raise ValueError("GSC snapshot source property is missing")
    payload = {
        "schema_version": 2,
        "captured_at": capture["captured_at"],
        "window_start": capture["window_start"],
        "window_end": capture["window_end"],
        "window_days": capture["window_days"],
        "finalization_lag_days": capture["finalization_lag_days"],
        "site_url": site_url,
        "producer_sha256": _sha256(__file__),
        "files": {name: _sha256(path) for name, path in selected_files.items()},
        "coverage": coverage,
    }
    snapshot_path = output_path or OUT_SNAPSHOT
    os.makedirs(os.path.dirname(snapshot_path), exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="gsc-snapshot-", suffix=".json",
                                     dir=os.path.dirname(snapshot_path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, snapshot_path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


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


def _api_service():
    try:
        from googleapiclient.discovery import build
    except Exception as exc:
        _log("ยังไม่ได้ติดตั้ง -> pip install google-api-python-client google-auth (%s)" % exc)
        return None
    creds = _creds()
    if creds is None:
        _log("ไม่มี token GSC. ทางเลือก: (1) auth เพิ่ม scope webmasters.readonly "
             "(2) export Performance จาก Search Console -> automation-log/gsc-queries.csv")
        return None
    return build("searchconsole", "v1", credentials=creds, cache_discovery=False)


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
        _log("list sites ไม่ได้ (%s) — ไม่ fallback ไป property ที่ยังยืนยันไม่ได้" % e)
        raise


def pull(*, exit_contract=False):
    try:
        svc = _api_service()
        if svc is None:
            if exit_contract:
                raise ProducerBlocked(
                    "GSC credentials or client dependency are unavailable"
                )
            return None
        capture = _capture_context()
        site = _resolve_site(svc)
        if not site:
            _log("ไม่มี property ngernduangold.com ที่ verify — ข้าม (ไม่อ่าน netlify.app/ผิดโดเมน)")
            if exit_contract:
                raise ProducerBlocked(
                    "verified ngernduangold.com GSC property is unavailable"
                )
            return None
        _log("GSC property = %s" % site)
        # Bind both tables and the sidecar to the one property selected for this
        # run.  This makes a wrong-property snapshot detectable downstream.
        capture = dict(capture, site_url=site)
        start, end = capture["window_start"], capture["window_end"]
        body = {"startDate": start, "endDate": end, "dimensions": ["query"],
                "rowLimit": ROW_LIMIT}
        resp = svc.searchanalytics().query(siteUrl=site, body=body).execute()
        if not isinstance(resp, dict):
            raise ValueError("GSC query response must be an object")
        rows = resp.get("rows", [])
        query_rows, query_counts = _aggregate_rows(rows, "query")
        queries_truncated = query_counts["api_rows"] >= ROW_LIMIT
        pbody = {"startDate": start, "endDate": end, "dimensions": ["page"],
                 "rowLimit": ROW_LIMIT}
        presp = svc.searchanalytics().query(siteUrl=site, body=pbody).execute()
        if not isinstance(presp, dict):
            raise ValueError("GSC page response must be an object")
        page_source_rows = presp.get("rows", [])
        page_rows, page_counts = _aggregate_rows(page_source_rows, "page")
        pages_truncated = page_counts["api_rows"] >= ROW_LIMIT

        coverage = {
            "queries": {"row_limit": ROW_LIMIT, "rows": query_counts["output_rows"],
                        "api_rows": query_counts["api_rows"],
                        "output_rows": query_counts["output_rows"],
                        "duplicate_rows_collapsed": query_counts["duplicate_rows_collapsed"],
                        "truncated": queries_truncated},
            "pages": {"row_limit": ROW_LIMIT, "rows": page_counts["output_rows"],
                      "api_rows": page_counts["api_rows"],
                      "output_rows": page_counts["output_rows"],
                      "duplicate_rows_collapsed": page_counts["duplicate_rows_collapsed"],
                      "truncated": pages_truncated},
        }
        output_dir = os.path.dirname(OUT_SNAPSHOT) or "."
        os.makedirs(output_dir, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="gsc-bundle-", dir=output_dir) as stage:
            staged = {
                "queries": os.path.join(stage, "gsc-queries.csv"),
                "pages": os.path.join(stage, "gsc-pages.csv"),
            }
            _atomic_csv(staged["queries"], [
                ("query", "clicks", "impressions", "ctr", "position"), *query_rows,
            ])
            _atomic_csv(staged["pages"], [
                ("page", "clicks", "impressions", "ctr", "position"), *page_rows,
            ])
            staged_snapshot = os.path.join(stage, "gsc-snapshot.json")
            _write_snapshot_metadata(coverage=coverage, context=capture,
                                     files=staged, output_path=staged_snapshot)
            os.replace(staged["queries"], OUT)
            os.replace(staged["pages"], OUTP)
            os.replace(staged_snapshot, OUT_SNAPSHOT)
        _log("OK -> gsc-queries.csv | api_rows=%d normalized_queries=%d" %
             (query_counts["api_rows"], query_counts["output_rows"]))
        _log("OK -> gsc-pages.csv | api_rows=%d pages=%d" %
             (page_counts["api_rows"], page_counts["output_rows"]))
        return {"file": OUT, "queries": query_counts["output_rows"],
                "query_api_rows": query_counts["api_rows"],
                "pages_file": OUTP, "pages": page_counts["output_rows"],
                "page_api_rows": page_counts["api_rows"], "snapshot": OUT_SNAPSHOT}
    except ProducerBlocked:
        raise
    except Exception as e:
        _log("ดึง GSC ล้มเหลว (%s) — เช็ก scope/สิทธิ์ property หรือใช้ export มือ" % e)
        if exit_contract:
            raise ProducerRunnerFailed(
                "GSC API, validation, or write failed"
            ) from e
        return None


def _parser():
    parser = argparse.ArgumentParser(
        description=(
            "Pull a finalized 28-day Google Search Console observation bundle. "
            "The API access is read-only; local CSV and snapshot files are replaced "
            "only after the complete bundle validates."
        )
    )
    return parser


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    # Parse before credentials, API clients, or output paths are touched.  In
    # particular, ``--help`` and invalid arguments must never trigger a pull.
    _parser().parse_args([] if argv is None else argv)
    try:
        result = pull(exit_contract=True)
        if result is None:
            raise ProducerRunnerFailed("GSC pull returned no classified result")
        return 0
    except ProducerBlocked as exc:
        _log("GSC observation bundle BLOCKED; metadata not advanced (%s)" % exc)
        return 2
    except ProducerRunnerFailed as exc:
        _log("GSC observation bundle RUNNER_FAILED; metadata not advanced (%s)" % exc)
        return 3
    except Exception as exc:
        _log("GSC observation bundle RUNNER_FAILED; metadata not advanced (%s)" % exc)
        return 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
