"""content_creators.py — 6 agent ผู้สร้างคอนเทนต์รายแพลตฟอร์ม (FB/IG/TikTok/Threads/Pantip/YouTube)
เน้นเอาต์พุตพร้อมโพสต์จริง · ฝัง learning จริง (comment-CTA, ฮุกไม่ซ้ำ, แฮชแท็ก, กัน hallucinate)
ผลิตดราฟต์ -> คืน dict (ไม่โพสต์เอง) · ผ่าน comply_gate
ใช้:  py pipeline/content_creators.py ig "หนี้บัตรหลายใบ จ่ายขั้นต่ำไม่ลด"
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import free_llm, comply_gate

QUIZ = "ngernduangold.com/quiz"
KW = "เช็กสิทธิ์"

CREATORS = {
 'fb': ('Facebook',
   "เขียนโพสต์ Facebook พร้อมโพสต์ 1 ชิ้น: บรรทัดแรก=ฮุกจุดเจ็บ/คำถาม (ห้ามขึ้นต้นซ้ำเดิม) · "
   "เนื้อ 3-6 บรรทัดให้คุณค่าจริง เว้นบรรทัด · ปิดด้วย CTA คอมเมนต์ '" + KW + "' เดี๋ยวส่งตัวช่วยให้ทาง DM · "
   "ท้ายโน้ต owner: ใส่ลิงก์ " + QUIZ + " ในคอมเมนต์แรก (ไม่ใส่ลิงก์ในตัวโพสต์) · 3-5 แฮชแท็ก"),
 'ig': ('Instagram Reel',
   "เขียนชุด Instagram Reel: HOOK (ข้อความขึ้นจอ 3 วิแรก สั้นกระแทกใจ) · SCRIPT 3-4 beats ~15-20 วิ · "
   "ON-SCREEN TEXT ต่อ beat · CAPTION 1-2 บรรทัด + CTA คอมเมนต์ '" + KW + "' เดี๋ยวส่งให้ทาง DM · "
   "HASHTAGS 8 ตัวตรงกลุ่มการเงินไทย · ห้ามใช้แคปชัน/ฮุกซ้ำเดิม"),
 'tiktok': ('TikTok',
   "เขียนสคริปต์ TikTok ไม่เกิน 30 วิ: HOOK 3 วิแรก (พูด+ข้อความบนจอ) สะดุดหยุดนิ้ว · BODY 2-3 ประโยค insight จริง · "
   "CTA คอมเมนต์ '" + KW + "' รับตัวช่วยทาง DM · ON-SCREEN TEXT รายช็อต + แนะนำแนวเพลงเทรนด์ · 5 แฮชแท็ก (#fyp+การเงิน)"),
 'threads': ('Threads',
   "เขียนชุด Threads: โพสต์หลัก=question-hook 1-2 บรรทัดชวนถก · รีพลายต่อเธรด 2-3 โพสต์ให้ข้อมูลจริงเป็นขั้น · "
   "ปิด: ใครอยากได้ตัวช่วย คอมเมนต์ '" + KW + "' หรือทัก DM · ไม่ใส่ลิงก์ในโพสต์หลัก"),
 'pantip': ('Pantip',
   "เขียนกระทู้ Pantip value-first พร้อมตั้ง (ห้องสินธร): ชื่อกระทู้ติดหูมีคีย์เวิร์ด · "
   "เนื้อ เล่าปัญหาที่คนอิน + มีการคำนวณ/ตัวอย่างตัวเลขเป็นช่วง + ขั้นตอนทำตามได้ + ข้อควรระวัง · "
   "ปิดด้วยคำถามชวนคุย · ห้ามมีลิงก์ในเนื้อ (อ้างได้แค่ ทำ quiz/ตัวเทียบไว้ในโปรไฟล์) · 3-4 แท็กท้าย"),
 'yt': ('YouTube Shorts',
   "เขียนชุด YouTube Shorts: SCRIPT ไม่เกิน 45 วิ (hook+1 insight+CTA คอมเมนต์ '" + KW + "'+กดติดตาม) · "
   "TITLE แบบ SEO มีคีย์เวิร์ด · DESCRIPTION 2-3 บรรทัด + ลิงก์ " + QUIZ + " (desc ใส่ลิงก์ได้) · 5 TAGS"),
}
PERSONA = ("คุณเป็นครีเอเตอร์คอนเทนต์การเงินไทยมืออาชีพบน {name} เป้าหมาย คอนเทนต์พร้อมโพสต์ทันที "
           "ดึง reach + เปลี่ยนเป็น lead ผ่าน comment->DM->quiz · value-first ไม่ขายตรง · คปภ-safe")


def create(key, topic, extra=""):
    name, spec = CREATORS[key]
    prompt = ("เขียนคอนเทนต์ตัวจริงที่พร้อมก๊อปวางโพสต์ทันที สำหรับหัวข้อ: " + topic +
              (("\nบริบท: " + extra) if extra else "") +
              "\n\nสเปกฟอร์แมต:\n" + spec +
              "\n\n[กฎความถูกต้อง] " + comply_gate.RULE +
              "\n[ห้าม hallucinate] ห้ามแต่ง/ระบุ ชื่อธนาคาร ชื่อผลิตภัณฑ์ เกณฑ์รายเจ้า หรือตัวเลขเฉพาะเจาะจง "
              "ที่อาจไม่จริง/ไม่อัปเดต (เช่น KTC ไม่ใช่ของกสิกร, บางแบรนด์เลิกให้บริการแล้ว) — พูดภาพรวม "
              "(หลายธนาคาร/บางผลิตภัณฑ์) ตัวเลขเป็นช่วงกว้าง แล้วบอกให้ผู้อ่านเช็กรายชื่อ/เงื่อนไขล่าสุดที่หน้าทางการเอง"
              "\n\n[สำคัญที่สุด] พิมพ์เฉพาะตัวคอนเทนต์จริง — ห้ามมีคำนำ ห้ามอธิบายว่ากำลังจะทำอะไร "
              "ห้ามเขียนโครงสร้าง/ขั้นตอน ห้ามขึ้นต้น เรามาสร้าง/ตอนนี้ เริ่มบรรทัดแรกด้วยตัวคอนเทนต์เลย "
              "(ฮุก/ชื่อกระทู้/แคปชัน) เขียนเต็มจบพร้อมโพสต์")
    t, m = free_llm.generate(prompt, system=PERSONA.format(name=name),
                             max_tokens=1100, temperature=0.5)
    fixed, ok, issues = comply_gate.gate(t or "")
    return {'platform': name, 'key': key, 'model': m, 'ok': ok,
            'issues': issues, 'content': fixed}


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    k = sys.argv[1] if len(sys.argv) > 1 else 'ig'
    topic = sys.argv[2] if len(sys.argv) > 2 else 'หนี้บัตรเครดิตหลายใบ จ่ายขั้นต่ำยอดไม่ลด อยากรวมหนี้ลดดอก'
    r = create(k, topic)
    print(r['platform'], '|', r['model'], '| comply', 'PASS' if r['ok'] else r['issues'])
    print('---')
    print(r['content'] or '(empty)')
