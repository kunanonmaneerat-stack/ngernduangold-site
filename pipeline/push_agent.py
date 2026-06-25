"""push_agent.py — เอเจนต์เตรียม-ดีพลอย + ด่านความปลอดภัย (รันบนเครื่อง owner)

ทำงานเป็นชั้น "เตรียมให้พร้อม + กันพลาด" ก่อนขึ้นเว็บจริง:
  1) TRUNCATION GUARD — เช็ก build_site.py ไม่ถูกตัดท้าย (บั๊กที่เคยเกิด!) ก่อนทำอะไร
  2) BUILD — รัน build_site.py สร้าง ./site
  3) VERIFY — 33+ หน้า · affiliate (atth.me) ครบ · quiz/links ครบ · title ไม่ยาวเกิน
  4) STAGE — git add -A + git commit (โลคัล ย้อนได้)
  5) GATE — **ไม่ push อัตโนมัติเงียบ ๆ** · push ต่อเมื่อใส่ --push พร้อม PUSH_APPROVED=1
     เหตุผล: push = ขึ้นเว็บสาธารณะ (กลับยาก) ควรมีคนยืนยันรอบสุดท้าย โดยเฉพาะเพิ่งเจอบั๊กไฟล์ถูกตัด

ใช้:  py pipeline/push_agent.py            # build+guard+verify+commit แล้วหยุด บอกคำสั่ง push
      set PUSH_APPROVED=1 && py pipeline/push_agent.py --push   # อนุมัติ push จริง
"""
import os, sys, subprocess, re
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BSP = os.path.join(ROOT, "build_site.py")
SITE = os.path.join(ROOT, "site")
TAIL_MARK = 'print("quiz.html written")'


def _run(cmd, cwd=ROOT):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, shell=False)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def guard_truncation():
    """กันบั๊กไฟล์ถูกตัดท้าย: ไฟล์ต้องจบด้วย marker + parse ได้ + ยาวสมเหตุผล."""
    src = open(BSP, encoding="utf-8").read()
    lines = [l for l in src.splitlines() if l.strip()]
    problems = []
    if not lines or lines[-1].strip() != TAIL_MARK:
        problems.append(f"ท้ายไฟล์ไม่ใช่ marker (เจอ: {lines[-1][:40] if lines else 'ว่าง'!r}) = อาจถูกตัด")
    if len(lines) < 1000:
        problems.append(f"ไฟล์สั้นผิดปกติ ({len(lines)} บรรทัด)")
    try:
        import ast; ast.parse(src)
    except SyntaxError as e:
        problems.append(f"parse ไม่ผ่าน บรรทัด {e.lineno}: {e.msg}")
    return problems


def verify_build():
    htmls = [f for f in os.listdir(SITE) if f.endswith(".html")] if os.path.isdir(SITE) else []
    issues = []
    if len(htmls) < 30:
        issues.append(f"หน้า HTML น้อยผิดปกติ ({len(htmls)})")
    for must in ("index.html", "quiz.html", "links.html", "debt-consolidation-2026.html"):
        if must not in htmls:
            issues.append("ขาด " + must)
    # affiliate ยังอยู่
    p = os.path.join(SITE, "credit-card-krungsri-2026.html")
    if os.path.exists(p) and "atth.me" not in open(p, encoding="utf-8").read():
        issues.append("affiliate link (atth.me) หาย!")
    return len(htmls), issues


def main(do_push):
    print("=== push_agent: เตรียม-ดีพลอย ===")
    g = guard_truncation()
    if g:
        print("❌ TRUNCATION GUARD ไม่ผ่าน — ไม่ build/deploy:")
        for x in g: print("   -", x)
        print("→ กู้ build_site.py ให้ครบก่อน (เช่น git checkout / splice จาก git HEAD) แล้วรันใหม่")
        return 2
    print("✅ guard ผ่าน (ไฟล์ครบ ไม่ถูกตัด)")

    rc, out = _run([sys.executable, "build_site.py"])
    if rc != 0 or "quiz.html written" not in out:
        print("❌ build ล้มเหลว:\n", out[-400:]); return 3
    n, vissues = verify_build()
    if vissues:
        print("❌ verify ไม่ผ่าน:", "; ".join(vissues)); return 4
    print(f"✅ build+verify ผ่าน ({n} หน้า · affiliate/quiz/links ครบ)")

    _run(["git", "add", "-A"])
    rc, out = _run(["git", "commit", "-m", "deploy: build_site + site (push_agent)"])
    if rc != 0 and "nothing to commit" not in out:
        print("⚠️ commit:", out[-200:])
    else:
        print("✅ staged + committed (โลคัล)")

    if do_push and os.environ.get("PUSH_APPROVED") == "1":
        rc, out = _run(["git", "push"])
        print(("✅ PUSHED — Netlify จะ deploy เอง" if rc == 0 else "❌ push error:\n" + out[-300:]))
        return 0 if rc == 0 else 5
    print("\n⏸️  หยุดก่อน push (ด่านความปลอดภัย) — ทุกอย่างพร้อมขึ้นเว็บแล้ว")
    print("   ขึ้นจริง:  set PUSH_APPROVED=1 && py pipeline/push_agent.py --push")
    print("   หรือสั่ง:  git push   (ด้วยตัวเอง)")
    return 0


if __name__ == "__main__":
    sys.exit(main("--push" in sys.argv))
