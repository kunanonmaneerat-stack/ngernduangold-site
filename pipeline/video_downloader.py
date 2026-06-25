"""video_downloader.py — Agent รับวิดีโอจาก Google Flow ลงเครื่อง -> จัดระเบียบ -> ส่งต่อ agent post
สแกนโฟลเดอร์ดาวน์โหลด (Downloads) หาไฟล์วิดีโอใหม่ -> ก๊อปเข้าคลัง
automation-log/video-out/<topic>/NN-<label>.mp4 -> จับคู่ caption/แฮชแท็ก/CTA/slot จาก handoff ล่าสุด
-> เขียน post-ready manifest (cowork-inbox/post-ready-<ts>.md + post-ready.json) ให้ post_agent/owner โพสต์ต่อ
ปลอดภัย: ก๊อปไฟล์ในเครื่องเท่านั้น (ไม่ลบต้นฉบับ ไม่โพสต์เอง ไม่ออกเน็ต) · กัน ingest ซ้ำด้วย fingerprint
ใช้:
  py pipeline/video_downloader.py ingest debt-consolidate "01-hook"   # รับไฟล์ใหม่ล่าสุดเข้า คลัง/หัวข้อ
  py pipeline/video_downloader.py scan                                 # รับทุกไฟล์ใหม่ (untagged -> _unsorted)
  py pipeline/video_downloader.py post_ready                           # เขียน manifest ให้ post agent
  py pipeline/video_downloader.py status
"""
import os, sys, glob, json, shutil, datetime, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AL = os.path.join(ROOT, "automation-log")
INBOX = os.path.join(AL, "cowork-inbox")
LIB = os.path.join(AL, "video-out")
STATE = os.path.join(AL, "video-ingest.json")
DOWNLOADS = os.environ.get("FLOW_DOWNLOAD_DIR", r"C:\Users\nL_ku\Downloads")
VIDEXT = (".mp4", ".webm", ".mov", ".m4v")
MAXAGE_H = 48                      # รับเฉพาะไฟล์ที่ดาวน์โหลดใหม่ใน N ชม.

# slug -> ลำดับหัวข้อในไฟล์ handoff (0-based) + ชื่อย่อไทย
TOPIC_SLUGS = {
    "debt-consolidate": ("หนี้บัตร/รวมหนี้", 0),
    "save-paycheck":    ("เงินเดือนชนเดือน/ออม", 1),
    "title-loan":       ("สินเชื่อทะเบียนรถ", 2),
    "emergency-fund":   ("เงินสำรองฉุกเฉิน", 3),
    "first-card":       ("บัตรเครดิตใบแรก", 4),
    "refinance":        ("รีไฟแนนซ์บ้าน", 5),
    "credit-score":     ("เครดิตบูโร/สกอร์", 6),
}


def _load():
    st = {"seen": [], "items": []}
    if os.path.exists(STATE):
        try:
            st = json.load(open(STATE, encoding="utf-8"))
        except Exception:
            pass
    st.setdefault("seen", []); st.setdefault("items", [])
    return st


def _save(st):
    os.makedirs(AL, exist_ok=True)
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def _fp(p):
    s = os.stat(p)
    return "%s|%d|%d" % (os.path.basename(p), s.st_size, int(s.st_mtime))


def _candidates():
    """ไฟล์วิดีโอใหม่ในโฟลเดอร์ดาวน์โหลด เรียงเก่า->ใหม่"""
    out = []
    if not os.path.isdir(DOWNLOADS):
        return out
    cutoff = datetime.datetime.now().timestamp() - MAXAGE_H * 3600
    for f in glob.glob(os.path.join(DOWNLOADS, "*")):
        if os.path.isfile(f) and f.lower().endswith(VIDEXT):
            try:
                if os.stat(f).st_mtime >= cutoff:
                    out.append(f)
            except Exception:
                pass
    out.sort(key=lambda p: os.stat(p).st_mtime)
    return out


def _next_n(topic_slug):
    st = _load()
    return 1 + sum(1 for it in st["items"] if it.get("topic") == topic_slug)


def _slug(s):
    s = re.sub(r"[^0-9A-Za-z฀-๿]+", "-", (s or "").strip())
    return s.strip("-")[:40] or "clip"


def ingest(topic_slug="_unsorted", label="clip", all_new=False):
    """ก๊อปไฟล์วิดีโอใหม่จาก Downloads เข้าคลัง (ล่าสุด 1 ไฟล์ หรือทั้งหมดถ้า all_new)"""
    st = _load()
    cands = [p for p in _candidates() if _fp(p) not in st["seen"]]
    if not cands:
        print("[video_downloader] ไม่พบไฟล์วิดีโอใหม่ใน", DOWNLOADS)
        return []
    picks = cands if all_new else [cands[-1]]
    done = []
    for src in picks:
        ts = TOPIC_SLUGS.get(topic_slug, (topic_slug, 0))[0]
        d = os.path.join(LIB, topic_slug)
        os.makedirs(d, exist_ok=True)
        n = _next_n(topic_slug)
        ext = os.path.splitext(src)[1].lower()
        dest = os.path.join(d, "%02d-%s%s" % (n, _slug(label), ext))
        try:
            shutil.copy2(src, dest)
        except Exception as e:
            print("[video_downloader] ก๊อปไม่สำเร็จ:", str(e)[:80]); continue
        st["seen"].append(_fp(src))
        st["items"].append({"topic": topic_slug, "topic_th": ts, "label": label,
                            "src": os.path.basename(src), "dest": dest,
                            "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
        done.append(dest)
        print("[video_downloader] +", dest, "<-", os.path.basename(src))
    _save(st)
    return done


def _handoff_meta():
    """ดึง caption/แฮชแท็ก ต่อหัวข้อ จากไฟล์ social-handoff ล่าสุด (เรียงตามหัวข้อ)"""
    fs = sorted(glob.glob(os.path.join(INBOX, "social-handoff-tiktok-*.md")))
    meta = []
    if not fs:
        return meta
    t = open(fs[-1], encoding="utf-8").read()
    blocks = re.split(r"\n##\s*หัวข้อ:\s*", t)
    for b in blocks[1:]:
        head = b.splitlines()[0].strip()
        cap = re.search(r"แคปชัน\*{0,2}:?\s*(.+)", b)
        tag = re.search(r"แฮชแท็ก\*{0,2}:?\s*(.+)", b)
        meta.append({"head": head,
                     "caption": (cap.group(1).strip() if cap else ""),
                     "hashtags": (tag.group(1).strip() if tag else "")})
    return meta


def _slots():
    try:
        import post_timing
        a = post_timing.analyze()
        return a.get("top_hours", {}).get("tiktok") or a.get("slots", {}).get("tiktok") or []
    except Exception:
        return []


def post_ready():
    st = _load()
    meta = _handoff_meta()
    slots = _slots()
    slot_str = ", ".join("%02d:00" % h for h in slots[:4]) if slots else "19:00, 21:00, 22:00"
    lines = ["# 📤 Post-Ready — วิดีโอพร้อมโพสต์ (video_downloader -> post agent) " +
             datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
             "> ไฟล์อยู่ในเครื่องแล้ว · ก่อนโพสต์: ใส่ข้อความบนจอ(ไทย)+เสียงพากย์ตามตาราง shot ในไฟล์ handoff",
             "> โพสต์เป็นสิทธิ์เจ้าของ (คนกดโพสต์เอง) · ปิดท้ายทุกคลิป CTA: คอมเมนต์ \"เช็กสิทธิ์\"", ""]
    jrows = []
    if not st["items"]:
        lines.append("_(ยังไม่มีวิดีโอในคลัง — รัน ingest หลังดาวน์โหลดจาก Flow)_")
    for i, it in enumerate(st["items"], 1):
        _, idx = TOPIC_SLUGS.get(it["topic"], (it["topic"], None))
        m = meta[idx] if (isinstance(idx, int) and idx < len(meta)) else {}
        cap = m.get("caption", ""); tag = m.get("hashtags", "")
        lines += ["## %d) %s · %s" % (i, it["topic_th"], it["label"]),
                  "- ไฟล์: `%s`" % it["dest"],
                  "- แพลตฟอร์ม: TikTok / Reels / Shorts (แนวตั้ง 9:16)",
                  "- แคปชัน: %s" % (cap or "(ดูในไฟล์ handoff)"),
                  "- แฮชแท็ก: %s" % (tag or "#fyp #การเงินส่วนบุคคล"),
                  "- CTA: คอมเมนต์ \"เช็กสิทธิ์\" -> auto-DM ส่ง /quiz",
                  "- เวลาโพสต์ดีสุด (GA4/heuristic): %s" % slot_str, ""]
        jrows.append({"file": it["dest"], "topic": it["topic_th"], "label": it["label"],
                      "caption": cap, "hashtags": tag, "slots": slots,
                      "cta": "คอมเมนต์ เช็กสิทธิ์"})
    os.makedirs(INBOX, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    open(os.path.join(INBOX, "post-ready-" + ts + ".md"), "w", encoding="utf-8").write("\n".join(lines))
    json.dump({"updated": ts, "items": jrows},
              open(os.path.join(AL, "post-ready.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("[video_downloader] post-ready -> %d วิดีโอ · slots: %s" % (len(st["items"]), slot_str))
    return jrows


def status():
    st = _load()
    print("[video_downloader] คลัง video-out: %d วิดีโอ · Downloads dir: %s" % (len(st["items"]), DOWNLOADS))
    for it in st["items"]:
        print("  -", it["topic_th"], "·", it["label"], "->", it["dest"])
    newc = [p for p in _candidates() if _fp(p) not in st["seen"]]
    print("  ไฟล์ใหม่รอ ingest ใน Downloads:", len(newc))
    return st


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "ingest":
        topic = sys.argv[2] if len(sys.argv) > 2 else "_unsorted"
        label = sys.argv[3] if len(sys.argv) > 3 else "clip"
        if ingest(topic, label):
            post_ready()
    elif cmd == "scan":
        if ingest("_unsorted", "clip", all_new=True):
            post_ready()
    elif cmd == "post_ready":
        post_ready()
    else:
        status()
