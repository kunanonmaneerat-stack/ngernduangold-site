# แทรกการอ้างอิง FULL-SURFACE-PLAN เข้า loop-architect (18 ก.ค. 2026)
import io
P = r"C:\Users\nL_ku\Claude\Scheduled\ngernduangold-loop-architect\SKILL.md"
ADD = "\n\n📋 เข็มทิศ surface (เพิ่ม 18 ก.ค.): อ่าน C:\\Users\\nL_ku\\ngernduangold-site\\automation-log\\FULL-SURFACE-PLAN_20260718.md ทุกครั้ง — surface ไหนถึงคิวเปิดใช้ (🔜 ถึงวันแล้ว) ให้ถือเป็น gap อันดับแรกก่อนคิดใหม่ · อัปเดตสถานะในไฟล์แผนเมื่อเปิดใช้แล้ว\n"
s = io.open(P, encoding="utf-8").read()
if "FULL-SURFACE-PLAN" not in s:
    io.open(P, "a", encoding="utf-8").write(ADD)
    print("appended")
else:
    print("already present")
