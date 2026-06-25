"""threads_refill.py — เติมคิว Threads อัตโนมัติแบบ "ปลอดภัย" (กัน spam-flag/shadowban)
ปลอดภัยตามบทเรียน 19 มิ.ย. (bot-post เยอะ = social ตาย):
  - คุมไว้ 1 โพสต์/วัน (ไม่เร่ง volume), เนื้อหาหมุนเวียนไม่ซ้ำ (state offset)
  - comply-safe: ไม่มีคำการันตี, ยึด ธปท/กลต/คปภ
อ่านจาก POOL (ดราฟต์ที่ตรวจแล้ว) -> เลือก N โพสต์ถัดไปแบบหมุนเวียน -> เขียน pipeline/article-posts-refill.json
แล้วตั้งคิวต่อด้วย postiz_article_scheduler.py --file pipeline/article-posts-refill.json --go
ใช้:  py pipeline/threads_refill.py [--n 7]
"""
import os, sys, json, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "pipeline", "article-posts-refill.json")
STATE = os.path.join(ROOT, "automation-log", "threads-refill-state.txt")
B = "https://ngernduangold.com/"


def u(slug):
    return f"{B}{slug}?utm_source=threads&utm_medium=social&utm_content={slug}"


# ดราฟต์ตรวจแล้ว (comply-safe) — หมุนเวียน 1/วัน เพื่อไม่ให้คิวแห้งหลังคิวเดิมหมด
POOL = [
 ("card15k", f"เงินเดือน 15,000 สมัครบัตรเครดิตได้ไหม? — ได้ ถ้าเล็งให้ถูกใบ + เตรียมเอกสารดี เล็งแบบไหน เพิ่มโอกาสผ่านยังไง อ่านก่อนยื่น\n\n{u('credit-card-salary-15000-2026')}\n\n#บัตรเครดิต #เงินเดือน15000 #FirstJobber"),
 ("save-hy", f"เงินเก็บนอนในบัญชีออมทรัพย์ปกติ = ดอกแทบ 0 ทั้งที่ทำงานแทนเราได้ บัญชีดอกสูงความเสี่ยงต่ำ ถอนได้ เลือกยังไง\n\n{u('high-yield-savings-2026')}\n\n#ออมเงิน #ดอกเบี้ย #การเงินส่วนบุคคล"),
 ("reject", f"สมัครบัตรไม่ผ่านบ่อย ๆ อันตรายกว่าที่คิด — ทุกครั้งที่ยื่นมีบันทึกในเครดิตบูโร เล็งบัตรที่เกณฑ์พอดีตัวช่วยเพิ่มโอกาสผ่าน\n\n{u('credit-card-easy-approval-2026')}\n\n#บัตรเครดิต #เครดิตบูโร #สมัครบัตร"),
 ("debt", f"มีหนี้บัตรหลายใบดอกสูง? การรวมหนี้เหลือก้อนเดียวดอกต่ำลง อาจช่วยให้จ่ายง่าย+ประหยัดดอกรวม คุ้มเมื่อไหร่ เช็กก่อน\n\n{u('debt-consolidation-2026')}\n\n#ปลดหนี้ #รวมหนี้ #การเงิน"),
 ("emergency", f"ไม่มีเงินสำรองฉุกเฉิน = พอมีเรื่องด่วน บัตรเครดิตกลายเป็นหนี้ก้อนโต ควรมีกี่เดือน เก็บที่ไหนถอนง่ายแต่ได้ดอก เริ่มยังไง\n\n{u('emergency-fund-2026')}\n\n#เงินสำรอง #ออมเงิน #วางแผนการเงิน"),
 ("interest", f"จ่ายขั้นต่ำบัตรทุกเดือน...รู้ไหมเสียดอกเท่าไหร่? เข้าใจวิธีคิดดอกเบี้ยบัตร + ระยะปลอดดอก ก่อนจะจ่ายแพงโดยไม่รู้ตัว\n\n{u('credit-card-interest-2026')}\n\n#บัตรเครดิต #ดอกเบี้ย #หนี้บัตร"),
 ("title", f"มีรถปลอดภาระ + ต้องการเงินก้อนเร็ว? จำนำทะเบียนรถ รถยังใช้ได้ เทียบดอก/ค่าธรรมเนียม/เงื่อนไขก่อนตัดสินใจ\n\n{u('title-loan-2026')}\n\n#สินเชื่อ #จำนำทะเบียนรถ #เงินด่วน"),
 ("cashback", f"รูดทุกวันแต่ไม่เคยได้เงินคืน = จ่ายแพงกว่าที่ควร บัตร cashback ทำงานยังไง ดูอะไรให้คุ้มกับไลฟ์สไตล์\n\n{u('credit-card-cashback-2026')}\n\n#บัตรเครดิต #เงินคืน #Cashback"),
 ("tax", f"มนุษย์เงินเดือนลดหย่อนภาษีได้มากกว่าที่คิด — รวมรายการลดหย่อน (ประกัน/SSF-RMF/พื้นฐาน) + วางแผนให้คุ้มก่อนสิ้นปี\n\n{u('tax-deduction-salary-2026')}\n\n#ลดหย่อนภาษี #ภาษี #มนุษย์เงินเดือน"),
 ("health-ins", f"ค่ารักษา รพ.เอกชนแพงขึ้นทุกปี ประกันสังคมอาจไม่พอ ประกันสุขภาพเลือกยังไง ดู IPD/OPD/เหมาจ่าย อะไรก่อนซื้อ\n\n{u('health-insurance-salary-2026')}\n\n#ประกันสุขภาพ #วางแผนการเงิน #มนุษย์เงินเดือน"),
 ("salary50", f"เงินเดือนเท่าไหร่ก็เก็บไม่อยู่? ลองสูตรแบ่งเงิน 50/30/20 — จ่ายให้ตัวเองก่อน ตั้งระบบอัตโนมัติ เริ่มได้แม้เงินเดือนน้อย\n\n{u('salary-budgeting-2026')}\n\n#ออมเงิน #วางแผนการเงิน #50_30_20"),
 ("firstcard", f"บัตรเครดิตใบแรกเลือกผิด เสียประวัติตั้งแต่เริ่ม เด็กจบใหม่/First Jobber ดูเกณฑ์รายได้-ค่าธรรมเนียม-เงินคืนตรงไหนก่อน\n\n{u('first-credit-card-student-2026')}\n\n#บัตรเครดิต #FirstJobber #เด็กจบใหม่"),
 ("fund", f"อยากเริ่มลงทุนแต่กลัวเริ่มไม่ถูก? กองทุนรวมเริ่มเงินน้อยได้ + DCA คืออะไร เริ่มยังไงให้ไม่งง (เริ่มก่อนพักเงินบัญชีออมดอกสูง)\n\n{u('mutual-fund-beginner-2026')}\n\n#ลงทุน #กองทุนรวม #DCA"),
 ("loanlegal", f"จะกู้ออนไลน์ทั้งที อย่าโดนหนี้นอกระบบ เช็กใบอนุญาต ธปท. + สัญญาณแอปเถื่อนที่ต้องหนี ก่อนกรอกข้อมูล\n\n{u('loan-online-legal-2026')}\n\n#สินเชื่อ #กู้เงินออนไลน์ #หนี้นอกระบบ"),
]


def main():
    args = sys.argv[1:]
    n = int(args[args.index("--n") + 1]) if "--n" in args else 7
    try:
        off = int(open(STATE, encoding="utf-8").read().strip())
    except Exception:
        off = 0
    picks = [POOL[(off + i) % len(POOL)] for i in range(n)]
    posts = [{"topic": f"refill-{t}", "content": c} for t, c in picks]
    cfg = {"channel": "threads", "hour_ict": 16, "per_day": 1,
           "note": "auto-refill 1/วัน (ปลอดภัย กัน shadowban) — หมุนเวียนดราฟต์ comply-safe",
           "generated": datetime.datetime.now().isoformat(timespec="seconds"), "posts": posts}
    json.dump(cfg, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(STATE, "w", encoding="utf-8").write(str((off + n) % len(POOL)))
    print("wrote %s | %d posts (1/วัน) · next offset=%d/%d" % (OUT, len(posts), (off + n) % len(POOL), len(POOL)))
    for p in posts:
        print("  -", p["topic"])


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
