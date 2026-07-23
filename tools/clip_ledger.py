# Append a confirmed daily-clip post to automation-log/post-ledger.jsonl (append-only).
# Fixes 23-Jul bug: dispatcher/UI flows confirmed clips but never wrote the ledger,
# so dup-check/quota-check drifted until Cowork backfilled by hand (commit ec9f63f).
# Usage (CLI):  py tools\clip_ledger.py --channel facebook --date 2026-07-23 [--source cc-dispatcher] [--text "..."] [--dry-run]
# Usage (lib):  from clip_ledger import append_row; append_row("youtube", "2026-07-24")
# ASCII-only source; Thai text comes from the manifest at runtime. UTF-8 no-BOM, never rewrites the file.
import argparse, json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(r"C:\Users\nL_ku\ngernduangold-site")
LEDGER = ROOT / "automation-log" / "post-ledger.jsonl"
MANIFEST = ROOT / ".system_control" / "content_manifest.json"
CHANNELS = ("facebook", "youtube", "instagram")
# manifest caption keys per channel (fallback order)
_CAP_KEYS = {"facebook": ("fb", "facebook"), "youtube": ("youtube", "yt"), "instagram": ("ig", "instagram")}


def _clip_text(item, channel):
    for key in ("topic", "title"):
        v = item.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    caps = item.get("captions") or {}
    for key in _CAP_KEYS.get(channel, ()) + ("tiktok", "threads"):
        v = caps.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip().splitlines()[0]
    return ""


def append_row(channel, date, source="cc-dispatcher", text=None, ledger=None, dry_run=False):
    """Append one {"type":"video",...} row. Returns OK / DUP_SKIP / DRY_OK. Append-only by design."""
    if channel not in CHANNELS:
        raise ValueError("channel must be one of %s" % (CHANNELS,))
    led = Path(ledger) if ledger else LEDGER

    clip_id = date
    if text is None:
        try:
            man = json.loads(MANIFEST.read_text(encoding="utf-8"))
            items = [x for x in man.get("items", []) if x.get("date") == date]
            if items:
                item = items[0]
                clip_id = item.get("id") or (date + "_" + str(item.get("slug") or "").strip("_")).rstrip("_")
                text = _clip_text(item, channel)
        except (OSError, json.JSONDecodeError):
            pass
    text = (text or "").strip() or ("clip " + date)

    # dedup: an existing video row for this channel+date (in clip_id or ts) means already ledgered
    if led.is_file():
        for line in led.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("type") == "video" and e.get("channel") == channel and (
                date in str(e.get("clip_id", "")) or str(e.get("ts", "")).startswith(date)
            ):
                return "DUP_SKIP"

    row = {
        "type": "video",
        "channel": channel,
        "clip_id": clip_id,
        "text_first80": text[:80],
        "ts": datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds"),
        "source": source,
    }
    if dry_run:
        print(json.dumps(row, ensure_ascii=False))
        return "DRY_OK"
    with led.open("a", encoding="utf-8") as f:  # append-only: never truncates, never rewrites
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return "OK"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True, choices=CHANNELS)
    ap.add_argument("--date", default=datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d"))
    ap.add_argument("--source", default="cc-dispatcher")
    ap.add_argument("--text", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    print("LEDGER_" + append_row(a.channel, a.date, source=a.source, text=a.text, ledger=a.ledger, dry_run=a.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
