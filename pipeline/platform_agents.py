"""platform_agents.py — 5 agent ดูแลรายแพลตฟอร์ม เพื่อ traffic+conversion.

แต่ละแพลตฟอร์ม = persona + playbook เฉพาะ -> ทำคอนเทนต์/แทคติกจากวัตถุดิบที่ผ่านสภา
-> ผ่าน comply_gate -> คืน dict.
(ไม่โพสต์เอง/ไม่ดึง analytics จริง = ตัวคิดคอนเทนต์+กลยุทธ์เฉพาะแพลตฟอร์ม · คนกดโพสต์)
ใช้:  from platform_agents import PLATFORMS, run ; run('tiktok', material)
      py pipeline/platform_agents.py tiktok
"""
import os, sys
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import free_llm, comply_gate

PLATFORMS = {
 'pantip':  ('Pantip', 'ตอบกระทู้ intent สูงแบบ value-first ยาวพอเป็นขั้นตอน ให้ข้อมูลจริงสร้างความน่าเชื่อถือ ปิดท้ายชวนคุยต่อ DM/โปรไฟล์ ไม่มีลิงก์ในคำตอบ เลี่ยงให้ดูเป็นโฆษณา'),
 'fb':      ('Facebook Groups', 'โพสต์ value ลงกลุ่มการเงิน 3-5 บรรทัด เปิดด้วยปัญหาที่คนอิน ปิดด้วยชวนถามต่อ ไม่มีลิงก์ เลี่ยงโดนกลุ่มแบน'),
 'ig':      ('Instagram', 'carousel 5-7 สไลด์ (สไลด์ 1=hook) caption สั้น 5 แฮชแท็กเฉพาะกลุ่ม ลิงก์ bio เท่านั้น'),
 'tiktok':  ('TikTok', 'สคริปต์พูด ≤30 วิ hook 3 วิแรกต้องสะดุด ข้อความบนจอ CTA คอมเมนต์/ทัก DM ไม่พึ่งลิงก์'),
 'yt':      ('YouTube Shorts', 'Shorts ≤45 วิ + ชื่อคลิป SEO ใส่คีย์เวิร์ด hook+1 insight+CTA subscribe/คอมเมนต์'),
 'threads': ('Threads', 'question-hook 1-2 บรรทัดชวนถก ตอบในเธรดด้วยข้อมูลจริง ปิดชวน DM โพสต์ถี่ได้ ไม่มีลิงก์ในโพสต์หลัก'),
}
PERSONA = 'คุณเป็นผู้เชี่ยวชาญโตออร์แกนิกบน {name} สายการเงินไทย value-first คปภ-safe ไม่ขายตรง เป้าหมาย traffic + เปลี่ยนเป็น lead ผ่าน DM/quiz'


def run(key, material):
    name, play = PLATFORMS[key]
    t, m = free_llm.generate(
        'ทำคอนเทนต์+แทคติกสำหรับ ' + name + ' จากวัตถุดิบด้านล่าง ตาม playbook: ' + play +
        '\n[กฎบังคับ] ' + comply_gate.RULE +
        '\nคืน: (ก) คอนเทนต์พร้อมใช้ (ข) 2 แทคติกเพิ่ม reach/conversion เฉพาะแพลตฟอร์มนี้:\n\n' + material,
        system=PERSONA.format(name=name), max_tokens=900, temperature=0.45)
    fixed, ok, issues = comply_gate.gate(t or '')
    return {'platform': name, 'model': m, 'ok': ok, 'issues': issues, 'content': fixed}


if __name__ == '__main__':
    key = sys.argv[1] if len(sys.argv) > 1 else 'tiktok'
    r = run(key, 'เคส: หนี้บัตรเครดิตหลายใบ จ่ายขั้นต่ำยอดไม่ลด อยากรวมหนี้ลดดอก')
    print(r['platform'], '|', r['model'], '| comply', 'PASS' if r['ok'] else r['issues'])
    print((r['content'] or '')[:400])
