#!/usr/bin/env python3
"""log_sale.py — append one North Star sale to automation-log/sales-log.jsonl (append-only, UTF-8, no PII).
Usage:
  py tools/log_sale.py --product letter-kit-199 --amount 199 --source line --ref "keyword-jotmai" --note "ปิดผ่านแชท LINE"
  py tools/log_sale.py --product ebook-59 --amount 59 --source gumroad
  py tools/log_sale.py --product affiliate-commission --amount 85 --source fb --note "happycash approved"
Rules: log ONLY product/amount/channel — NEVER customer name/phone/PII.
"""
import argparse, json, datetime, os, sys
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(BASE, "automation-log", "sales-log.jsonl")
PRODUCTS = {"letter-kit-199":199, "ebook-59":59, "affiliate-commission":None}
SOURCES = {"line","gumroad","fb","fb-page2","threads","ig","yt","pinterest","pantip","direct","organic"}
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--product", required=True, choices=list(PRODUCTS))
    p.add_argument("--amount", required=True, type=float)
    p.add_argument("--source", required=True, choices=sorted(SOURCES))
    p.add_argument("--ref", default="")
    p.add_argument("--note", default="")
    p.add_argument("--date", default=None, help="YYYY-MM-DD (default today, Asia/Bangkok)")
    a = p.parse_args()
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    d = a.date or now.strftime("%Y-%m-%d")
    # guard: refuse anything that looks like PII in ref/note
    import re
    blob = (a.ref + " " + a.note)
    if re.search(r"\b0\d{8,9}\b", blob) or re.search(r"@\w+\.\w+", blob):
        sys.exit("REFUSED: ref/note looks like it contains a phone/email — do NOT log customer PII.")
    rec = {"date": d, "product": a.product, "amount_thb": round(a.amount,2),
           "channel_source": a.source, "ref": a.ref, "note": a.note,
           "ts": now.strftime("%Y-%m-%dT%H:%M:%S+07:00")}
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("logged:", json.dumps(rec, ensure_ascii=False))
if __name__ == "__main__":
    main()
