#!/usr/bin/env python3
# 07_render.py — render a 9:16 kinetic-text TikTok clip from a render-spec JSON. NO AI credits (PIL+numpy+ffmpeg, free).
# Adapted/generalized from Cowork's render_clip.py (Sarabun + raqm shaping, known production-quality).
# Requires: pip install pillow numpy  ·  fonts/Bold.ttf,Reg.ttf,XBold.ttf (set TIKTOK_FONTS_DIR)  ·  ffmpeg on PATH
#
# spec JSON: {"out":"clip.mp4","w":1080,"h":1920,"fps":20,"dur":21,"brand":["เงินเดือนสมองทอง","ไม่ขายฝัน"],
#   "disclosure":"...","scenes":[{"t0":0,"t1":3.6,"k":"kicker","h":["line","[g]gold[/g] line"],"s":"sub or null","disc":false}]}
import argparse, json, subprocess, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import config as C

NAVY = (15, 23, 42); NAVY2 = (30, 41, 59); GOLD = (224, 201, 166); GOLDA = (197, 168, 128)
OFF = (245, 248, 250); BLUE = (226, 232, 240); MUT = (148, 163, 184)

SAMPLE = {"out": "clip001_credit.mp4", "w": 1080, "h": 1920, "fps": 20, "dur": 21.0,
          "brand": ["เงินเดือนสมองทอง", "ไม่ขายฝัน"],
          "disclosure": "เนื้อหาเพื่อการศึกษา ไม่ใช่คำแนะนำเฉพาะบุคคล · มีลิงก์พันธมิตร · ผลิตด้วย AI",
          "scenes": [
              {"t0": 0.0, "t1": 3.6, "k": "มนุษย์เงินเดือนหลายคนเจอ", "h": ["เงินเดือนก็ถึงเกณฑ์", "[g]แต่บัตรใบแรก…ไม่ผ่าน?[/g]"], "s": None},
              {"t0": 3.6, "t1": 8.9, "k": "เพราะธนาคารไม่ได้ดูแค่รายได้", "h": ["เขาดู [g]ประวัติการจ่าย[/g]", "ที่คุณยังไม่มี"], "s": None},
              {"t0": 8.9, "t1": 14.7, "k": "จุดที่หลายคนเข้าใจผิด", "h": ["ไม่เคยมีหนี้", "= เครดิตบูโร [g]ว่างเปล่า[/g]"], "s": "ธนาคารเลยยังไม่รู้จักนิสัยการเงินของคุณ"},
              {"t0": 14.7, "t1": 21.0, "k": "อยากเทียบตัวเลือกแบบไม่ขายฝัน?", "h": ["ลิงก์อยู่ใน", "[g]โปรไฟล์[/g]"], "s": None, "disc": True},
          ]}

def render(spec):
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    W, H, FPS, DUR = spec["w"], spec["h"], spec["fps"], float(spec["dur"])
    NFR = int(DUR * FPS)
    FB, FR = str(C.FONTS_DIR / "Bold.ttf"), str(C.FONTS_DIR / "Reg.ttf")
    fnt = lambda p, s: ImageFont.truetype(p, s)

    def make_bg():
        y = np.linspace(0, 1, H)[:, None]
        top, mid, bot = np.array(NAVY2), np.array(NAVY), np.array((11, 17, 32))
        col = np.where(y < 0.5, top + (mid - top) * (y / 0.5), mid + (bot - mid) * ((y - 0.5) / 0.5))
        bg = np.tile(col[:, None, :], (1, W, 1))
        yy, xx = np.mgrid[0:H, 0:W]
        dvg = np.sqrt(((xx - W / 2) / (W * 0.65)) ** 2 + ((yy - H / 2) / (H * 0.55)) ** 2)
        v = np.clip(1 - (dvg - 0.6) * 0.9, 0.55, 1)[:, :, None]
        return (bg * v).astype(np.float32)

    bg = make_bg()
    if spec.get("brand"):
        im = Image.fromarray(bg.astype(np.uint8), "RGB"); d = ImageDraw.Draw(im)
        f1, f2 = fnt(FB, 38), fnt(FR, 24); t1 = spec["brand"][0]
        d.text(((W - d.textlength(t1, font=f1)) / 2, 52), t1, font=f1, fill=GOLD)
        if len(spec["brand"]) > 1:
            t2 = spec["brand"][1]; d.text(((W - d.textlength(t2, font=f2)) / 2, 104), t2, font=f2, fill=MUT)
        bg = np.asarray(im).astype(np.float32)
    BG = bg

    def seg_parse(line):
        out, i = [], 0
        while i < len(line):
            if line.startswith("[g]", i):
                j = line.find("[/g]", i); out.append((line[i + 3:j], GOLD)); i = j + 4
            else:
                j = line.find("[g]", i); j = len(line) if j < 0 else j
                out.append((line[i:j], OFF)); i = j
        return out

    def fit(draw, lines, base, maxw):
        s = base
        while s > 40:
            f = fnt(FB, s)
            if all(sum(draw.textlength(t, font=f) for t, _ in seg_parse(ln)) <= maxw for ln in lines):
                return s
            s -= 4
        return s

    def scene_layer(kicker, heads, sub):
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im); maxw = W - 150
        hs = fit(d, heads, 96, maxw); fk, fh, fs = fnt(FB, 40), fnt(FB, hs), fnt(FR, 50)
        lh_h = int(hs * 1.22); lh_s = 64
        blockh = (56 if kicker else 0) + len(heads) * lh_h + ((28 + lh_s) if sub else 0)
        y = (H - blockh) // 2
        if kicker:
            d.text(((W - d.textlength(kicker, font=fk)) / 2, y), kicker, font=fk, fill=GOLDA); y += 56 + 18
        for ln in heads:
            segs = seg_parse(ln); x = (W - sum(d.textlength(t, font=fh) for t, _ in segs)) / 2
            for t, c in segs:
                d.text((x, y), t, font=fh, fill=c); x += d.textlength(t, font=fh)
            y += lh_h
        if sub:
            y += 28; d.text(((W - d.textlength(sub, font=fs)) / 2, y), sub, font=fs, fill=BLUE)
        a = np.asarray(im).astype(np.float32); return a[:, :, :3], a[:, :, 3] / 255.0

    def disc_layer(text):
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im); f = fnt(FR, 24)
        maxw = W - 160; words, lines, cur = text.split(" "), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if d.textlength(t, font=f) <= maxw: cur = t
            else: lines.append(cur); cur = w
        if cur: lines.append(cur)
        y = H - 70 - len(lines) * 32
        for ln in lines:
            d.text(((W - d.textlength(ln, font=f)) / 2, y), ln, font=f, fill=MUT); y += 32
        a = np.asarray(im).astype(np.float32); return a[:, :, :3], a[:, :, 3] / 255.0

    SC = spec["scenes"]
    for sc in SC:
        sc["_rgb"], sc["_a"] = scene_layer(sc.get("k"), sc["h"], sc.get("s"))
    DRGB, DA = disc_layer(spec.get("disclosure", ""))
    ease = lambda x: x * x * (3 - 2 * x)

    ff = subprocess.Popen(["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                           "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", "-crf", "22", spec["out"]],
                          stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for fr in range(NFR):
        t = fr / FPS; out = BG.copy()
        for sc in SC:
            if t < sc["t0"] - 0.01 or t > sc["t1"] + 0.5: continue
            lt = t - sc["t0"]; fin = ease(min(lt / 0.5, 1.0))
            fout = 1.0 if (sc.get("disc") and sc is SC[-1]) else ease(min(max((sc["t1"] - t) / 0.4, 0.0), 1.0))
            al = min(fin, fout)
            if al <= 0: continue
            shift = int((1 - fin) * 42); a = sc["_a"] * al; rgb = sc["_rgb"]
            if shift > 0:
                a = np.roll(a, -shift, axis=0); a[-shift:, :] = 0; rgb = np.roll(rgb, -shift, axis=0)
            am = a[:, :, None]; out = out * (1 - am) + rgb * am
            if sc.get("disc"):
                da = DA[:, :, None] * ease(min(max((t - (sc["t1"] - 1.6)) / 1.0, 0), 1)); out = out * (1 - da) + DRGB * da
        pw = int(W * t / DUR); out[H - 10:H, :pw] = GOLD
        ff.stdin.write(np.clip(out, 0, 255).astype(np.uint8).tobytes())
    ff.stdin.close(); ff.wait()
    return spec["out"], NFR

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--spec", default=None); ap.add_argument("--out", default=None); a = ap.parse_args()
    spec = C.jload(a.spec) if a.spec else SAMPLE
    if a.out: spec["out"] = a.out
    try:
        import numpy, PIL  # noqa
    except ImportError:
        print("ต้องติดตั้งก่อน:  pip install pillow numpy   (ฟรี) + วางฟอนต์ใน tiktok-pipeline/fonts/ (Bold/Reg/XBold .ttf)"); sys.exit(1)
    out, nfr = render(spec)
    print(f"[07_render] done {nfr} frames -> {out}  (FPS={spec['fps']} ultrafast · $0 ไม่ใช้ AI credit)")

if __name__ == "__main__":
    main()
