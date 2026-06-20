#!/usr/bin/env python3
# 06_burn_disclosure.py  (OPT-IN · default = ไม่รัน — caption disclosure พอแล้ว)
# Burn a 1-line disclosure bar on the LAST N seconds of a clip (belt-and-suspenders).
# Thai needs complex-text shaping -> render PNG via PIL (raqm) then ffmpeg overlay (audio copy, ultrafast).
# Requires: pip install pillow  ·  fonts/Reg.ttf (set TIKTOK_FONTS_DIR)
import argparse, json, subprocess, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import config as C

DISC = "เนื้อหาเพื่อการศึกษา · ไม่การันตีผล/อนุมัติ/เคลม · มีลิงก์พันธมิตร · ผลิตด้วย AI"

def main():
    ap = argparse.ArgumentParser(description="opt-in disclosure burn (default not part of pipeline)")
    ap.add_argument("clip"); ap.add_argument("--out"); ap.add_argument("--secs", type=float, default=3.0); ap.add_argument("--text", default=DISC)
    a = ap.parse_args()
    src = pathlib.Path(a.clip) if pathlib.Path(a.clip).exists() else C.CLIPS_DIR / a.clip
    if not src.exists():
        print(f"ไม่พบคลิป {src} — ตั้ง TIKTOK_CLIPS_DIR หรือใส่ path เต็ม"); sys.exit(1)
    out = pathlib.Path(a.out) if a.out else src.with_name(src.stem + "_disc.mp4")
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("ต้องติดตั้งก่อน:  pip install pillow"); sys.exit(1)

    pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=width,height", "-show_entries", "format=duration", "-of", "json", str(src)],
                        capture_output=True, text=True)
    j = json.loads(pr.stdout); W = j["streams"][0]["width"]; H = j["streams"][0]["height"]; DUR = float(j["format"]["duration"])

    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    f = ImageFont.truetype(str(C.FONTS_DIR / "Reg.ttf"), max(20, int(H * 0.018)))
    words = a.text.split(" "); lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= W - 120:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    lh = int(H * 0.026); bh = len(lines) * lh + 24
    d.rectangle([0, H - bh, W, H], fill=(15, 23, 42, 185))
    y = H - bh + 12
    for ln in lines:
        wl = d.textlength(ln, font=f); d.text(((W - wl) / 2, y), ln, font=f, fill=(226, 232, 240, 235)); y += lh
    png = out.with_suffix(".disc.png"); im.save(png)

    t0 = max(DUR - a.secs, 0)
    subprocess.run(["ffmpeg", "-y", "-i", str(src), "-i", str(png),
                    "-filter_complex", f"[0:v][1:v]overlay=0:0:enable='gte(t,{t0:.2f})'",
                    "-c:a", "copy", "-preset", "ultrafast", "-crf", "22", str(out)], check=True)
    png.unlink(missing_ok=True)
    print(f"[06_burn] burned last {a.secs}s -> {out}")

if __name__ == "__main__":
    main()
