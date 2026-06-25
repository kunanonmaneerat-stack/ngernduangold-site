# ASCII-ONLY. Hybrid Reel: Flow footage + brand/hook/CTA + scrim that hides the AI watermark.
# Usage: python3 _hb_build.py <footage.mp4> <caption.txt> <outname.mp4>   (defaults to debt)
import os, sys, subprocess, traceback
try:
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np

    REPO = r"C:\Users\nL_ku\ngernduangold-site"
    OUTD = os.path.join(REPO, "_vidout"); os.makedirs(OUTD, exist_ok=True)
    FB = os.path.join(REPO, "tiktok-pipeline", "fonts", "Bold.ttf")
    FR = os.path.join(REPO, "tiktok-pipeline", "fonts", "Reg.ttf")

    foot = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "media", "clips", "debt-consolidation-2026.mp4")
    cap = sys.argv[2] if len(sys.argv) > 2 else os.path.join(REPO, "tiktok-pipeline", "captions", "vid_debt.txt")
    outname = sys.argv[3] if len(sys.argv) > 3 else "hybrid_debt.mp4"
    OVL = os.path.join(OUTD, outname + ".ovl.png")
    OUTV = os.path.join(OUTD, outname)
    W, H = 1080, 1920
    GOLD = (210, 184, 140); WHITE = (250, 250, 252); MUT = (190, 200, 214)

    lines = [l.strip() for l in open(cap, encoding="utf-8").read().splitlines() if l.strip()]
    nohash = [l for l in lines if not l.startswith("#")]
    hook = nohash[0].rstrip(":")
    cta = next((l for l in nohash if "\U0001f449" in l), None) or (nohash[2] if len(nohash) > 2 else nohash[-1])
    cta = cta.replace("\U0001f449", "").strip()
    disc = next((l for l in nohash if "AI" in l), "")
    HANDLE = "@ngernduangold"

    dummy = ImageDraw.Draw(Image.new("RGBA", (W, H)))

    def wrap(draw, text, font, maxw):
        out, cur = [], ""
        for w in text.split(" "):
            t = (cur + " " + w).strip()
            if draw.textlength(t, font=font) <= maxw: cur = t
            else:
                if cur: out.append(cur)
                cur = w
        if cur: out.append(cur)
        return out

    def fit(draw, text, path, start, maxw, maxlines):
        s = start
        while s >= 46:
            f = ImageFont.truetype(path, s); ls = wrap(draw, text, f, maxw)
            if len(ls) <= maxlines: return f, ls, s
            s -= 4
        f = ImageFont.truetype(path, s); return f, wrap(draw, text, f, maxw), s

    fhook, hlines, hs = fit(dummy, hook, FB, 84, W - 150, 3)
    lh = int(hs * 1.20); hblock = len(hlines) * lh
    hy0 = 440

    # scrim alpha map: bottom (watermark cover) + top fade (handle) + band behind hook
    yy = np.arange(H)[:, None].astype(np.float32)
    al = np.clip(((yy - H * 0.60) / (H * 0.30)) * 0.95, 0, 0.90)
    al = np.where(yy > H * 0.60, al, 0).astype(np.float32)
    al = np.maximum(al, np.where(yy < H * 0.13, np.clip(0.55 * (1 - yy / (H * 0.13)), 0, 0.55), 0))
    hb0, hb1 = hy0 - 40, hy0 + hblock + 24
    band = np.where((yy > hb0) & (yy < hb1), 0.46, 0)
    al = np.maximum(al, band)
    al = np.repeat(al, W, axis=1)
    scrim = np.zeros((H, W, 4), np.uint8); scrim[:, :, 3] = (al * 255).astype(np.uint8)
    im = Image.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, 0)), Image.fromarray(scrim, "RGBA"))
    d = ImageDraw.Draw(im)

    def ctext(y, s, font, fill):
        x = (W - d.textlength(s, font=font)) / 2
        d.text((x + 3, y + 3), s, font=font, fill=(0, 0, 0, 170))
        d.text((x, y), s, font=font, fill=fill)

    fbrand = ImageFont.truetype(FB, 40)
    ctext(72, HANDLE, fbrand, GOLD)
    y = hy0
    for ln in hlines:
        ctext(y, ln, fhook, WHITE); y += lh

    fcta, clines, cs = fit(dummy, cta, FB, 50, W - 170, 2)
    y = 1560
    for ln in clines:
        ctext(y, ln, fcta, GOLD); y += int(cs * 1.25)

    if disc:
        fdisc = ImageFont.truetype(FR, 26); dl = wrap(d, disc, fdisc, W - 130); y = 1828 - len(dl) * 32
        for ln in dl:
            ctext(y, ln, fdisc, MUT); y += 32

    im.save(OVL)
    cmd = ["ffmpeg", "-y", "-i", foot, "-i", OVL, "-filter_complex",
           "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[bg];[bg][1:v]overlay=0:0[v]",
           "-map", "[v]", "-an", "-t", "10", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "veryfast", OUTV]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print("rc", r.returncode, "->", outname, "exists", os.path.exists(OUTV), flush=True)
    if r.returncode != 0: print((r.stderr or "")[-700:], flush=True)
except Exception:
    traceback.print_exc()
