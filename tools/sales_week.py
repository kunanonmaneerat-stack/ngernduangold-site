#!/usr/bin/env python3
"""sales_week.py — summarize sales-log for the current (or given) Mon–Sun week. Read-only."""
import json, datetime, os, sys, collections
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(BASE, "automation-log", "sales-log.jsonl")
def parse(d): return datetime.date.fromisoformat(d)
def main():
    today = datetime.date.today()
    if len(sys.argv) > 1: today = parse(sys.argv[1])
    mon = today - datetime.timedelta(days=today.weekday())
    sun = mon + datetime.timedelta(days=6)
    rows=[]
    if os.path.exists(LOG):
        for l in open(LOG, encoding="utf-8"):
            try:
                r=json.loads(l)
                if "date" not in r: continue
                if mon <= parse(r["date"]) <= sun: rows.append(r)
            except: pass
    total=sum(r["amount_thb"] for r in rows)
    by_prod=collections.Counter(); rev_prod=collections.Counter(); by_src=collections.Counter()
    for r in rows:
        by_prod[r["product"]]+=1; rev_prod[r["product"]]+=r["amount_thb"]; by_src[r["channel_source"]]+=r["amount_thb"]
    print(f"WEEK {mon}..{sun}  —  sales={len(rows)}  revenue={total:.0f} THB")
    if rows:
        print("by product:", {k:f'{by_prod[k]}x={rev_prod[k]:.0f}' for k in rev_prod})
        print("revenue by source:", {k:f'{v:.0f}' for k,v in by_src.most_common()})
    else:
        print("(ยังไม่มี sale บันทึกสัปดาห์นี้ — owner บันทึกผ่าน py tools/log_sale.py หลังปิดดีลใน LINE/Gumroad)")
if __name__=="__main__": main()
