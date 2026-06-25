"""make_ig_card.py — สร้างการ์ดภาพ IG (1080x1080) จากข้อความ ฟรี (PIL + ฟอนต์ไทย Windows).
ใช้:  py pipeline/make_ig_card.py
"""
import os
from PIL import Image, ImageDraw, ImageFont

W = H = 1080
BG = (16, 42, 67)
ACC = (46, 196, 182)
WHITE = (240, 244, 248)
SUB = (150, 170, 190)

FB_BOLD = r'C:\Windows\Fonts\leelawuib.ttf'
FREG = r'C:\Windows\Fonts\leelawui.ttf'
TAHOMA = r'C:\Windows\Fonts\tahoma.ttf'


def font(sz, bold=False):
    cands = [FB_BOLD, FREG] if bold else [FREG, TAHOMA]
    for p in cands + [TAHOMA]:
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


img = Image.new('RGB', (W, H), BG)
d = ImageDraw.Draw(img)
d.rectangle([0, 0, W, 18], fill=ACC)

d.text((80, 96), 'ก่อนสมัครบัตร / สินเชื่อ', font=font(44), fill=SUB)
d.text((80, 158), 'เช็ก "โปรไฟล์การเงิน"', font=font(76, True), fill=WHITE)
d.text((80, 250), 'ตัวเองก่อน 3 จุด', font=font(76, True), fill=ACC)

pts = [('1', 'เครดิตบูโร (NCB)', 'ดูว่ามียอดค้าง/ประวัติค้างชำระไหม'),
       ('2', 'ภาระผ่อนต่อรายได้', 'อย่าให้สูงเกินไปเมื่อเทียบรายได้'),
       ('3', 'ความมั่นคงของรายได้/งาน', 'อายุงาน+เอกสารยิ่งชัด ยิ่งช่วย')]
y = 430
for n, t, s in pts:
    d.ellipse([80, y, 150, y + 70], fill=ACC)
    d.text((101, y + 8), n, font=font(40, True), fill=BG)
    d.text((184, y - 2), t, font=font(46, True), fill=WHITE)
    d.text((184, y + 56), s, font=font(33), fill=SUB)
    y += 152

d.text((80, 968), '@ngernduangold', font=font(40, True), fill=ACC)
d.text((80, 1024), 'ข้อมูลเพื่อการศึกษา ไม่ใช่คำแนะนำเฉพาะบุคคล', font=font(28), fill=SUB)

out = r'C:\Users\nL_ku\ngernduangold-site\automation-log\ig-cards\card-profile.png'
os.makedirs(os.path.dirname(out), exist_ok=True)
img.save(out)
print('saved', out)
