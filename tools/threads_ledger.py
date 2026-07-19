# Record a Threads video post in post-ledger.jsonl and mark manifest posted.threads.
# Usage: py tools\threads_ledger.py --date 2026-07-17 [--source cowork-zero-touch]
# ASCII-only source; Thai text comes from the manifest at runtime.
import argparse, json, hashlib, re
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(r"C:\Users\nL_ku\ngernduangold-site")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--source", default="cowork-zero-touch")
    args = ap.parse_args()

    man_path = ROOT / ".system_control" / "content_manifest.json"
    man = json.loads(man_path.read_text(encoding="utf-8"))
    items = [x for x in man["items"] if x.get("date") == args.date]
    if not items:
        print("NO_MANIFEST_ITEM")
        return 1
    item = items[0]
    text = (item.get("captions", {}) or {}).get("threads") or ""
    if not text.strip():
        print("EMPTY_THREADS_CAPTION")
        return 1

    # dedup: skip if a threads entry for this date already exists
    led = ROOT / "automation-log" / "post-ledger.jsonl"
    if led.is_file():
        for line in led.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("channel") == "threads" and args.date in json.dumps(e, ensure_ascii=False):
                print("ALREADY_LEDGERED")
                return 0

    norm = re.sub(r"\s+", "", text)
    entry = {
        "type": "video",
        "channel": "threads",
        "text_hash": hashlib.sha1(norm.encode("utf-8")).hexdigest(),
        "text_first80": text[:80],
        "ts": datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds"),
        "source": args.source + "-" + args.date.replace("-", ""),
    }
    with led.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    item.setdefault("posted", {})["threads"] = "posted (" + entry["source"] + ")"
    man_path.write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("LEDGER_OK")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
