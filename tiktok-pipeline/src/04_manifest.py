#!/usr/bin/env python3
# 04_manifest.py — scripts_clean (PASS only) -> production-manifest.json + UPLOAD-CHECKLIST.md (no LLM).
import argparse, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import config as C

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.parse_args()
    clean = C.jload(C.DRAFTS / "scripts_clean.json"); amap = C.jload(C.ROOT / "article_map.json")
    utm = amap["utm"]
    manifest = []
    for c in clean:
        if not c.get("compliance_pass"):
            continue
        manifest.append({
            "clip_id": c["clip_id"], "topic_th": c["topic_th"], "hook_variants": c.get("hook_variants", []),
            "script": c.get("script", []), "length_sec": c.get("length_sec", 45),
            "article_slug": c["article_slug"], "bio_utm": c["article_slug"] + utm,
            "music_mood": c.get("music_mood", "calm-corporate"), "visual_style": c.get("visual_style", "kinetic-text-navy-gold"),
            "compliance_pass": True, "disclosure": c.get("disclosure", ""),
            "number_warnings": c.get("number_warnings", []), "suggested_post_time": "19:30"})
    (C.READY / "clips").mkdir(exist_ok=True)
    C.jsave(C.READY / "production-manifest.json", manifest)

    lines = ["# ✅ UPLOAD CHECKLIST — เจ้าของอัปมือจากแอป TikTok", "",
             f"_{len(manifest)} คลิปพร้อมผลิต · อ่าน production-manifest.json คู่กัน_", "",
             "## ทุกครั้งก่อนอัป",
             "- [ ] เปิด **แอป TikTok บนมือถือ** (ไม่ใช่เว็บ / ไม่ใช่ scheduler / **ไม่ผ่าน Postiz**)",
             "- [ ] วิดีโอจริงอยู่ใน `ready-for-cowork/clips/<clip_id>.mp4` (Cowork generate + ผ่าน virality gate แล้ว)",
             "- [ ] ก็อปแคปชันจาก manifest (มี disclosure แล้ว) — **ห้ามแก้ใส่ลิงก์** (route ผ่าน bio เท่านั้น)",
             "- [ ] เวลาแนะนำ **19:00–21:00** · **1 คลิป/วัน** (ความถี่ต่ำ — อย่ายิงรัวจนโดน spam-flag)",
             "- [ ] ตอบคอมเมนต์เองช่วงแรก (native engagement ช่วยปลด throttle)", "",
             "## bio",
             "- [ ] หลัง warm-up วันที่ 8 → ใส่ลิงก์ `ngernduangold.com/links` ใน bio (UTM tiktok ติดอัตโนมัติ)", "",
             "## คลิปรอบนี้"]
    for m in manifest:
        nw = f" · ⚠️เช็กตัวเลข {len(m['number_warnings'])}" if m.get("number_warnings") else ""
        lines.append(f"- **{m['clip_id']}** · {m['topic_th']} · ~{m['length_sec']}s · bio→{m['article_slug']}{nw}")
    lines += ["", "## 4-week kill-criterion (Opus)",
              "- เฝ้า 4 สัปดาห์: วิวเฉลี่ย + GA4 `affiliate_click` จาก session source=tiktok",
              "- ถ้าวิวเฉลี่ย < ~200 **และ** affiliate_click ไม่ขยับ → ปล่อยช่องวิดีโอ คงเว็บ+Pantip (อย่าจมเวลาต่อ)"]
    pathlib.Path(C.READY / "UPLOAD-CHECKLIST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[04_manifest] {len(manifest)} คลิป → ready-for-cowork/production-manifest.json + UPLOAD-CHECKLIST.md")
    # Task F: chain caption refresh if a clip registry exists (best-effort, won't break manifest)
    if (C.ROOT / "clip_registry.json").exists():
        import subprocess
        try:
            subprocess.run([sys.executable, str(C.ROOT / "src" / "05_captions.py"), "--dry-run"], check=False)
        except Exception:
            pass

if __name__ == "__main__":
    main()
