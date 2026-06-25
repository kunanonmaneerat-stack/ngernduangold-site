# ASCII-ONLY. Batch-render hybrid Reels (footage + short on-screen hook/CTA from scripts_clean.json + watermark-cover scrim).
# Thai text comes ONLY from JSON data (never literals). One run = all clips.
import os, json, subprocess, traceback
try:
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np

    REPO = r"C:\Users\nL_ku\ngernduangold-site"
    OUTD = os.path.join(REPO, "_vidout"); os.makedirs(OUTD, exist_ok=True)
    CLIPS = os.path.join(REPO, "media", "clips")
    FBOLD = os.path.join(REPO, "tiktok-pipeline", "fonts", "Bold.ttf")
    FREG = os.path.join(REPO, "tiktok-pipeline", "fonts", "Reg.ttf")
    SCRIPTS = json.load(open(os.path.join(REPO, "tiktok-pipeline", "drafts", "scripts_clean.json"), encoding="utf-8"))
    W, H = 1080, 1920
    GOLD = (210, 184, 140); WHITE = (250, 250, 252); MUT = (190, 200, 214)
    HANDLE = "@ngernduangold"

    # footage filename (no ext) -> slug/topic keywords (ASCII) to match a script
    FOOT_MAP = [
        ("debt-consolidation-2026", ["debt", "payoff", "consolidat"]),
        ("credit-bureau-check-2026", ["bureau", "credit-score", "score", "rejected"]),
        ("emergency-fund-2026", ["emergency", "fund", "save", "saving"]),
        ("first-credit-card-student-2026", ["salary-15000", "first", "student", "salary-card", "credit-card-salary"]),
        ("refinance-home-2026", ["refinance", "home-loan", "mortgage"]),
        ("salary-budgeting-2026", ["budget", "salary", "503020", "50-30-20"]),
        ("title-loan-2026", ["title-loan", "car-for-cash", "cash"]),
    ]

    def find_script(keywords, used):
        for c in SCRIPTS:
            if c.get("clip_id") in used:
                continue
            blob = (c.get("article_slug", "") + " " + c.get("clip_id", "")).lower()
            if any(k in blob for k in keywords):
                return c
        return None

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

    def fit(text, path, start, maxw, maxlines, floor=44):
        s = start
        while s >= floor:
            f = ImageFont.truetype(path, s); ls = wrap(dummy, text, f, maxw)
            if len(ls) <= maxlines and all(dummy.textlength(x, font=f) <= maxw for x in ls): return f, ls, s
            s -= 4
        f = ImageFont.truetype(path, floor); return f, wrap(dummy, text, f, maxw), floor

    def build_overlay(hook, cta, disc, path_png):
        fhook, hlines, hs = fit(hook, FBOLD, 86, W - 140, 3)
        lh = int(hs * 1.20); hblock = len(hlines) * lh; hy0 = 430
        yy = np.arange(H)[:, None].astype(np.float32)
        al = np.where(yy > H * 0.60, np.clip(((yy - H * 0.60) / (H * 0.30)) * 0.95, 0, 0.90), 0).astype(np.float32)
        al = np.maximum(al, np.where(yy < H * 0.13, np.clip(0.55 * (1 - yy / (H * 0.13)), 0, 0.55), 0))
        al = np.maximum(al, np.where((yy > hy0 - 40) & (yy < hy0 + hblock + 24), 0.46, 0))
        al = np.repeat(al, W, axis=1)
        scrim = np.zeros((H, W, 4), np.uint8); scrim[:, :, 3] = (al * 255).astype(np.uint8)
        im = Image.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, 0)), Image.fromarray(scrim, "RGBA"))
        d = ImageDraw.Draw(im)

        def ctext(y, s, font, fill):
            x = (W - d.textlength(s, font=font)) / 2
            d.text((x + 3, y + 3), s, font=font, fill=(0, 0, 0, 175)); d.text((x, y), s, font=font, fill=fill)

        ctext(72, HANDLE, ImageFont.truetype(FBOLD, 40), GOLD)
        y = hy0
        for ln in hlines: ctext(y, ln, fhook, WHITE); y += lh
        fcta, clines, cs = fit(cta, FBOLD, 50, W - 170, 2)
        y = 1560
        for ln in clines: ctext(y, ln, fcta, GOLD); y += int(cs * 1.25)
        if disc:
            fdisc = ImageFont.truetype(FREG, 25); dl = wrap(d, disc, fdisc, W - 120); y = 1832 - len(dl) * 30
            for ln in dl: ctext(y, ln, fdisc, MUT); y += 30
        im.save(path_png)

    used, manifest = [], []
    for fname, kws in FOOT_MAP:
        foot = os.path.join(CLIPS, fname + ".mp4")
        if not os.path.exists(foot):
            manifest.append((fname, "NO-FOOTAGE", "")); continue
        sc = find_script(kws, used)
        if not sc:
            manifest.append((fname, "NO-SCRIPT-MATCH", "")); continue
        used.append(sc.get("clip_id"))
        scenes = sc.get("script", [])
        hook = sc.get("topic_th") or (scenes[0]["onscreen"] if scenes else "")
        cta = scenes[-1]["onscreen"] if scenes else "ลิงก์ในไบโอ"
        disc = sc.get("disclosure", "")
        out = "reel_" + fname + ".mp4"
        ovl = os.path.join(OUTD, out + ".ovl.png")
        build_overlay(hook, cta, disc, ovl)
        cmd = ["ffmpeg", "-y", "-i", foot, "-i", ovl, "-filter_complex",
               "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[bg];[bg][1:v]overlay=0:0[v]",
               "-map", "[v]", "-map", "0:a:0?", "-t", "10", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "veryfast", "-c:a", "aac", "-b:a", "128k",
               os.path.join(OUTD, out)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        manifest.append((fname, sc.get("clip_id") + " ok=" + str(r.returncode == 0), out))

    print("=== BATCH MANIFEST ===")
    for m in manifest: print(m[0], "->", m[1], "->", m[2])
    print("rendered:", len([m for m in manifest if m[2]]))
except Exception:
    traceback.print_exc()
