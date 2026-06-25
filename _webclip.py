# ASCII-ONLY. Web version of the Veo clips: cover the moving AI sparkle watermark (bottom-center, y~1120-1210)
# with a subtle bottom lower-third + our domain. Keeps the footage audio. Source clips untouched (originals stay in media/clips).
import os, subprocess, traceback
try:
    from PIL import Image, ImageDraw, ImageFont

    REPO = r"C:\Users\nL_ku\ngernduangold-site"
    SRC = os.path.join(REPO, "media", "clips")
    OUT = os.path.join(REPO, "media", "clips-web"); os.makedirs(OUT, exist_ok=True)
    FB = os.path.join(REPO, "tiktok-pipeline", "fonts", "Bold.ttf")
    W, H = 720, 1280

    # alpha map (pure PIL, no numpy): 0 above y=1020, soft fade 1020->1092, near-solid 0.96 below
    # -> fully hides the bright sparkle at y~1120-1210
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for y in range(1020, 1092):
        al = int(((y - 1020) / 72.0) * 0.96 * 255)
        d.line([(0, y), (W, y)], fill=(0, 0, 0, al))
    d.rectangle([0, 1092, W, H], fill=(0, 0, 0, int(0.96 * 255)))

    f = ImageFont.truetype(FB, 30)
    t = "ngernduangold.com"
    x = (W - d.textlength(t, font=f)) / 2
    d.text((x + 2, 1206), t, font=f, fill=(0, 0, 0, 150))
    d.text((x, 1204), t, font=f, fill=(214, 188, 144, 240))
    ovl = os.path.join(OUT, "_webscrim.png"); im.save(ovl)

    clips = sorted(c for c in os.listdir(SRC) if c.endswith(".mp4"))
    res = []
    for c in clips:
        outp = os.path.join(OUT, c)
        cmd = ["ffmpeg", "-y", "-i", os.path.join(SRC, c), "-i", ovl, "-filter_complex",
               "[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1[bg];[bg][1:v]overlay=0:0[v]",
               "-map", "[v]", "-map", "0:a:0?", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "21", "-preset", "veryfast",
               "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", outp]
        r = subprocess.run(cmd, capture_output=True, text=True)
        res.append((c, "ok" if r.returncode == 0 else "FAIL"))
    print("=== WEB CLIPS ===")
    for c, st in res: print(st, c)
    print("done", len([1 for _, st in res if st == "ok"]), "/", len(res))
except Exception:
    traceback.print_exc()
