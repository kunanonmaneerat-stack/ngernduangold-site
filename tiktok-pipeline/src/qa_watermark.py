#!/usr/bin/env python3
# ASCII-ONLY. qa_watermark.py - Veo sparkle watermark detector / QA gate (order 2026-07-09).
#
# WHY: Google Flow (Veo) footage carries a small semi-transparent sparkle watermark that
# DRIFTS around the lower-right zone. A fixed bottom scrim (_hb_batch.py ~30-38%) fails
# because the sparkle floats ABOVE the bar on some frames -> 5 IG reels leaked. This gate
# frame-scans a clip and FAILs if a persistent, slowly-drifting, ISOLATED bright blob is
# found in the risk zone. Text overlays (hooks/end-cards/kinetic reels) do NOT trip it:
# text glyphs come in rows (many neighbors), the sparkle is solitary.
#
# Usage:  python qa_watermark.py FILE.mp4 [FILE2 ...] [--evidence-dir DIR] [--fps 2]
# Exit:   0 = all PASS, 2 = any FAIL (hard-block), 3 = error.
# Output: per file PASS/FAIL + track stats + drift bounds (source-res coords) and, with
#         --evidence-dir, annotated evidence PNGs of detected frames.
# stdlib + pillow + numpy + ffmpeg only ($0).
import os, sys, json, math, shutil, subprocess, tempfile, argparse

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

FFMPEG = shutil.which("ffmpeg") or r"C:\Users\nL_ku\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe"
FFPROBE = shutil.which("ffprobe") or FFMPEG.replace("ffmpeg.exe", "ffprobe.exe")

SCAN_W = 720          # analysis width (frames scaled down for speed)
ZONE_X = 0.40         # risk zone: right 60% ...
ZONE_Y = 0.52         # ... lower 48% (sparkle drifts up to ~mid height of lower half)
NCC_THR = 0.78        # astroid-template NCC threshold (calibrated 2026-07-09: true sparkle ~0.95, clean-content peaks <=0.69)
CLUSTER_R = 150       # spatial cluster radius (covers slow drift path)
FAIL_FRAC = 0.15      # track present in >= this fraction of sampled frames -> FAIL
FAIL_MIN_FRAMES = 4


def _template(size=57, radius=26):
    """Synthetic Veo sparkle: 4-point concave star (astroid |x|^(2/3)+|y|^(2/3)<=r^(2/3)),
    zero-mean unit-norm float array. Synthetic > cropped patch (no background bias)."""
    import numpy as np
    c = size // 2
    yy, xx = np.mgrid[0:size, 0:size]
    r = float(radius) ** (2.0 / 3.0)
    inside = (np.abs(xx - c) ** (2.0 / 3.0) + np.abs(yy - c) ** (2.0 / 3.0)) <= r
    t = inside.astype(np.float64)
    t -= t.mean()
    t /= (np.sqrt((t * t).sum()) + 1e-9)
    return t


_TPL = None


def _ncc_peaks(img, thr, topk=3):
    """Normalized cross-correlation of the sparkle template over the risk zone.
    Returns [(cx,cy,x0,y0,x1,y1,score)] for local maxima >= thr (scan coords)."""
    import numpy as np
    global _TPL
    if _TPL is None:
        _TPL = _template()
    tpl = _TPL
    th, tw = tpl.shape
    a = np.asarray(img.convert("L"), dtype=np.float64)
    h, w = a.shape
    zx, zy = int(w * ZONE_X), int(h * ZONE_Y)
    z = a[zy:, zx:]
    zh, zw = z.shape
    if zh < th or zw < tw:
        return []
    # numerator: cross-correlation with zero-mean template (FFT; template symmetric -> conv==corr)
    fs = (zh + th - 1, zw + tw - 1)
    F = np.fft.rfft2(z, fs)
    T = np.fft.rfft2(tpl[::-1, ::-1], fs)
    num_full = np.fft.irfft2(F * T, fs)
    num = num_full[th - 1:zh, tw - 1:zw]              # valid region, top-left index = patch origin
    # denominator: local std of each patch via integral images (exact, fast)
    ii = np.cumsum(np.cumsum(np.pad(z, ((1, 0), (1, 0))), 0), 1)
    ii2 = np.cumsum(np.cumsum(np.pad(z * z, ((1, 0), (1, 0))), 0), 1)
    S = ii[th:, tw:] - ii[:-th, tw:] - ii[th:, :-tw] + ii[:-th, :-tw]
    S2 = ii2[th:, tw:] - ii2[:-th, tw:] - ii2[th:, :-tw] + ii2[:-th, :-tw]
    n = float(th * tw)
    var = np.maximum(S2 - S * S / n, 1e-6)
    ncc = num / np.sqrt(var)
    # peak picking: greedy top-k with suppression radius
    out = []
    ncc_c = ncc.copy()
    for _ in range(topk):
        idx = int(np.argmax(ncc_c))
        py, px = divmod(idx, ncc_c.shape[1])
        sc = float(ncc_c[py, px])
        if sc < thr:
            break
        cx, cy = px + tw / 2.0 + zx, py + th / 2.0 + zy
        out.append((cx, cy, px + zx, py + zy, px + tw + zx, py + th + zy, sc))
        y0, y1 = max(0, py - th), min(ncc_c.shape[0], py + th)
        x0, x1 = max(0, px - tw), min(ncc_c.shape[1], px + tw)
        ncc_c[y0:y1, x0:x1] = -1
    return out


def scan(path, fps=2.0, evidence_dir=None):
    """Frame-scan one mp4. Returns dict verdict."""
    from PIL import Image, ImageDraw
    if not os.path.exists(path):
        return {"file": path, "verdict": "ERROR", "error": "not found"}
    try:
        sw = subprocess.check_output([FFPROBE, "-v", "error", "-select_streams", "v:0",
                                      "-show_entries", "stream=width", "-of", "csv=p=0", path]).decode().strip()
        src_w = int(sw.split(",")[0])
    except Exception:
        src_w = SCAN_W
    scale = src_w / float(SCAN_W)
    tmp = tempfile.mkdtemp(prefix="wmqa_")
    try:
        r = subprocess.run([FFMPEG, "-y", "-i", path, "-vf", "fps=%s,scale=%d:-2" % (fps, SCAN_W),
                            os.path.join(tmp, "f%04d.png"), "-loglevel", "error"],
                           capture_output=True, text=True)
        frames = sorted(f for f in os.listdir(tmp) if f.endswith(".png"))
        if r.returncode != 0 or not frames:
            return {"file": path, "verdict": "ERROR", "error": (r.stderr or "no frames")[-200:]}
        per = []
        for fn in frames:
            im = Image.open(os.path.join(tmp, fn))
            per.append((fn, _ncc_peaks(im, NCC_THR)))
        # spatial-recurrence clustering: the sparkle TWINKLES (fades in/out) so strict
        # frame-chains break; but its drift path stays compact. Cluster all candidates
        # by position and count DISTINCT frames hitting the densest cluster.
        clusters = []  # each: {"pts":[(i,c)...], "cx":..., "cy":...}
        for i, (fn, cands) in enumerate(per):
            for c in cands:
                home = None
                for cl in clusters:
                    if math.hypot(c[0] - cl["cx"], c[1] - cl["cy"]) <= CLUSTER_R:
                        home = cl
                        break
                if home is None:
                    clusters.append({"pts": [(i, c)], "cx": c[0], "cy": c[1]})
                else:
                    home["pts"].append((i, c))
                    k = len(home["pts"])
                    home["cx"] += (c[0] - home["cx"]) / k
                    home["cy"] += (c[1] - home["cy"]) / k
        n = len(per)
        best = []
        if clusters:
            dense = max(clusters, key=lambda cl: len({i for i, _ in cl["pts"]}))
            seen_f = set()
            for i, c in dense["pts"]:
                if i not in seen_f:
                    seen_f.add(i)
                    best.append((i, c))
        frac = len(best) / float(n) if n else 0.0
        fail = len(best) >= FAIL_MIN_FRAMES and frac >= FAIL_FRAC
        res = {"file": path, "verdict": "FAIL" if fail else "PASS",
               "frames": n, "track_frames": len(best), "track_frac": round(frac, 2)}
        if best:
            xs0 = [c[2] for _, c in best]; ys0 = [c[3] for _, c in best]
            xs1 = [c[4] for _, c in best]; ys1 = [c[5] for _, c in best]
            res["drift_bounds_src"] = {  # source-resolution coords, for crop/cover planning
                "x0": int(min(xs0) * scale), "y0": int(min(ys0) * scale),
                "x1": int(max(xs1) * scale), "y1": int(max(ys1) * scale)}
        if fail and evidence_dir:
            os.makedirs(evidence_dir, exist_ok=True)
            base = os.path.splitext(os.path.basename(path))[0]
            for i, c in best[:3] + best[-1:]:
                fn, _ = per[i][0], per[i][1]
                im = Image.open(os.path.join(tmp, per[i][0])).convert("RGB")
                d = ImageDraw.Draw(im)
                d.rectangle([c[2] - 6, c[3] - 6, c[4] + 6, c[5] + 6], outline=(255, 0, 0), width=3)
                ev = os.path.join(evidence_dir, "%s_f%03d.png" % (base, i))
                im.save(ev)
            res["evidence"] = evidence_dir
        return res
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="Veo sparkle watermark QA gate (exit 2 = FAIL/block)")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--evidence-dir", default=None)
    ap.add_argument("--fps", type=float, default=2.0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    import glob as _g
    files = []
    for pat in a.files:   # Windows cmd does not expand wildcards -> glob here
        m = _g.glob(pat)
        files.extend(m if m else [pat])
    results = [scan(f, a.fps, a.evidence_dir) for f in files]
    anyfail = False
    for r in results:
        if a.json:
            print(json.dumps(r, ensure_ascii=False))
        else:
            extra = ""
            if r.get("drift_bounds_src"):
                b = r["drift_bounds_src"]
                extra = " drift[src x%d-%d y%d-%d]" % (b["x0"], b["x1"], b["y0"], b["y1"])
            print("%-7s %s (track %s/%s frames)%s" % (r["verdict"], r["file"],
                  r.get("track_frames", "?"), r.get("frames", "?"), extra))
        if r["verdict"] == "FAIL":
            anyfail = True
        if r["verdict"] == "ERROR":
            anyfail = True
    sys.exit(2 if anyfail else 0)


if __name__ == "__main__":
    main()
