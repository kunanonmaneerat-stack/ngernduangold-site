#!/usr/bin/env python3
# comply_gate_stitch.py - scan Stitch/AI-exported HTML for Thai-finance compliance risks.
# Rule: real numbers (rate/%/fee/approval-time) and reviews must NOT be hardcoded in design markup;
# numbers belong in verified Python/Jinja variables ({{...}}) from a checked DB, reviews must be real+sourced.
# Usage:  python3 tools/comply_gate_stitch.py <file_or_dir>
# Exit 1 if any FAIL finding (use in build_site.py / comply_gate before a Stitch component can ship).
import sys, os, re, glob

PLACEHOLDER = re.compile(r'\{\{[^}]*\}\}')                       # {{bank_rate}} etc = OK (dynamic)
PERCENT  = re.compile(r'\d+(?:\.\d+)?\s*%')
RATE_CTX = re.compile(r'(ดอกเบี้ย|ดอก|อัตรา|ต่อปี|ผลตอบแทน|ปันผล|APR|interest|rate)\D{0,14}\d', re.I)
FEE_CTX  = re.compile(r'(ค่าธรรมเนียม|ค่าบริการ|fee)\D{0,14}\d', re.I)
APPROVE  = re.compile(r'(อนุมัติ|รู้ผล|สมัครเสร็จ|approve[d]?)\D{0,10}\d+\s*(นาที|ชั่วโมง|ชม|วัน|min|hour|day)', re.I)
AMOUNT_CTX = re.compile(r'(วงเงิน|ยอด|สูงสุด|ขั้นต่ำ|เครดิต|ผ่อน)\D{0,14}\d', re.I)
MULTIPLIER = re.compile(r'(\d+(?:\.\d+)?\s*เท่า|สูงถึง\D{0,12}\d|มากกว่า\D{0,10}\d)', re.I)
THAINAME = re.compile(r'(คุณ|นาย|นาง|น\.ส\.)[ ฀-๿]{1,20}\s*[:"]')   # "คุณสมชาย:" fake quote
MONEY    = re.compile(r'\d[\d,]*\s*(บาท|฿|THB)', re.I)
STAR     = re.compile(r'(★|⭐|[0-5]\.[0-9]\s*/\s*5|[0-5]\s*ดาว)')
TESTI    = re.compile(r'(รีวิวจาก|ความคิดเห็นจาก|ผู้ใช้จริง|testimonial|customer review)', re.I)
DISCLAIM = re.compile(r'(ตรวจสอบ.{0,24}(เงื่อนไข|ค่าธรรมเนียม|อีกครั้ง)|โปรดตรวจสอบ|ข้อมูลอัปเดต)', re.I)
DATESTAMP= re.compile(r'(\{\{\s*updated_date|ณ\s*วันที่|อัปเดตล่าสุด)')

BARE_THOUSANDS = re.compile(r'\b\d{1,3}(?:,\d{3})+\b')

FAIL_RULES = [(PERCENT,'hardcoded %'),(RATE_CTX,'hardcoded rate+number'),
              (FEE_CTX,'hardcoded fee+number'),(APPROVE,'hardcoded approval-time claim'),
              (AMOUNT_CTX,'hardcoded amount+number'),(MULTIPLIER,'hardcoded multiplier/superlative claim')]

def scan(text):
    fails=[]; warns=[]
    for i,ln in enumerate(text.split('\n'),1):
        bare=PLACEHOLDER.sub('',ln)              # ignore dynamic placeholders
        for rx,lab in FAIL_RULES:
            if rx.search(bare): fails.append((i,lab,ln.strip()[:90]))
        if THAINAME.search(ln): fails.append((i,'fake testimonial (named quote)',ln.strip()[:90]))
        if MONEY.search(bare):  warns.append((i,'money amount (verify: variable, not a product claim)',ln.strip()[:80]))
        if STAR.search(ln):     warns.append((i,'star/rating (verify real, not decorative)',ln.strip()[:80]))
        if BARE_THOUSANDS.search(bare): warns.append((i,'bare grouped number - verify it is a {{variable}}',ln.strip()[:80]))
    if TESTI.search(text):      warns.append((0,'review wording present - verify real & sourced',''))
    if not DISCLAIM.search(text):  warns.append((0,'no disclaimer phrase (add "ตรวจสอบเงื่อนไข...อีกครั้ง")',''))
    if not DATESTAMP.search(text): warns.append((0,'no date-stamp ({{updated_date}} / "ณ วันที่")',''))
    return fails,warns

def main():
    if len(sys.argv)<2: print('usage: comply_gate_stitch.py <file_or_dir>'); sys.exit(2)
    t=sys.argv[1]
    if os.path.isdir(t):
        exts=('*.html','*.htm','*.jsx','*.tsx','*.vue')
        files=[f for e in exts for f in glob.glob(os.path.join(t,'**',e),recursive=True)]
    else:
        files=[t]
    tot=0
    for f in files:
        text=open(f,encoding='utf-8',errors='replace').read()
        fails,warns=scan(text)
        if fails or warns: print('\n== %s ==' % f)
        for i,lab,s in fails: print('  FAIL L%s: %s :: %s' % (i,lab,s))
        for i,lab,s in warns: print('  warn L%s: %s :: %s' % (i,lab,s))
        tot+=len(fails)
    print('\nSUMMARY: %d file(s), %d FAIL finding(s).' % (len(files),tot))
    sys.exit(1 if tot else 0)

if __name__=='__main__': main()
