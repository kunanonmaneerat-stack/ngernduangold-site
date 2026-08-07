# ASCII-only. Dump exact on-clip text (hook=script[0].onscreen, cta=script[-1].onscreen) for the 4 used scripts.
import json, os
REPO = r"C:\Users\nL_ku\ngernduangold-site"
d = json.load(open(os.path.join(REPO, "tiktok-pipeline", "drafts", "scripts_clean.json"), encoding="utf-8"))
want = {"tt-001", "tt-002", "tt-003", "tt-004"}
out = []
for c in d:
    if c.get("clip_id") not in want:
        continue
    sc = c.get("script", [])
    out.append("### " + c.get("clip_id") + "  topic=" + c.get("topic_th", ""))
    out.append("HOOK(onscreen[0]): " + (sc[0]["onscreen"] if sc else ""))
    out.append("CTA (onscreen[-1]): " + (sc[-1]["onscreen"] if sc else ""))
    out.append("all onscreen lines:")
    for s in sc:
        out.append("   - " + s.get("onscreen", ""))
    out.append("disclosure: " + c.get("disclosure", ""))
    out.append("")
open(os.path.join(REPO, "_vidout", "_used_text.txt"), "w", encoding="utf-8").write("\n".join(out))
print("done", len(out), "lines")
