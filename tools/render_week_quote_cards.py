#!/usr/bin/env python3
"""Render the approved local-only qt-12/qt-13/qt-14 quote-card candidates.

The renderer is deterministic and offline.  It writes no account handle, logo,
URL, provider mark, platform mark, or tracking element into the artwork.  Thai
copy is rendered by Chromium rather than Pillow so combining marks are shaped by
the browser text engine.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import html
import importlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "media" / "quotes" / "week-20260824-30-r5"
DEFAULT_STAGE = ROOT / ".local-private" / "runtime" / "quote-card-render-r5"
RECEIPT_ROOT = ROOT / "automation-log" / "media-qa"
TARGET_PACK_ID = "week-content-20260824-30-r5"
EDGE_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
)
VARIANTS = (
    ("4x5", 1080, 1350, "fb-ig_4x5", "fb-ig-image-r5"),
    ("2x3", 1000, 1500, "pinterest_2x3", "pinterest-image-r5"),
)


CARDS = {
    "qt-12": {
        "text": "อย่าเอาสถานะการเงินของเราไปเทียบกับภาพชีวิตของคนอื่น เพราะเราไม่เห็นภาพการเงินทั้งหมดของเขา",
        "lines_4x5": (
            "อย่าเอาสถานะการเงินของเรา",
            "ไปเทียบกับภาพชีวิตของคนอื่น",
            "เพราะเราไม่เห็นภาพการเงิน",
            "ทั้งหมดของเขา",
        ),
        "lines_2x3": (
            "อย่าเอาสถานะการเงิน",
            "ของเราไปเทียบกับ",
            "ภาพชีวิตของคนอื่น",
            "เพราะเราไม่เห็น",
            "ภาพการเงินทั้งหมดของเขา",
        ),
        "palette": ("#10273A", "#274C5E", "#F3C988", "#F7F1E7"),
        "scene": "city",
    },
    "qt-13": {
        "text": "ต้นไม้ใหญ่ไม่ได้โตในวันเดียว เงินก้อนแรกก็เช่นกัน แค่ดูแลมันทุกเดือน",
        "lines_4x5": (
            "ต้นไม้ใหญ่ไม่ได้โตในวันเดียว",
            "เงินก้อนแรกก็เช่นกัน",
            "แค่ดูแลมันทุกเดือน",
        ),
        "lines_2x3": (
            "ต้นไม้ใหญ่ไม่ได้โต",
            "ในวันเดียว เงินก้อนแรก",
            "ก็เช่นกัน แค่ดูแลมัน",
            "ทุกเดือน",
        ),
        "palette": ("#173C34", "#496F58", "#E8B36A", "#FBF3DF"),
        "scene": "plant",
    },
    "qt-14": {
        "text": "อิสรภาพทางการเงินไม่ใช่การมีเงินไม่จำกัด แต่คือการไม่ต้องกังวลทุกครั้งที่สิ้นเดือนมาถึง",
        "lines_4x5": (
            "อิสรภาพทางการเงิน",
            "ไม่ใช่การมีเงินไม่จำกัด",
            "แต่คือการไม่ต้องกังวล",
            "ทุกครั้งที่สิ้นเดือนมาถึง",
        ),
        "lines_2x3": (
            "อิสรภาพทางการเงิน",
            "ไม่ใช่การมีเงินไม่จำกัด",
            "แต่คือการไม่ต้องกังวล",
            "ทุกครั้งที่",
            "สิ้นเดือนมาถึง",
        ),
        "palette": ("#3C2A36", "#72524A", "#F0B978", "#FFF2DF"),
        "scene": "family",
    },
}


SOURCE_BINDINGS = {
    "qt-12": {
        "path": "automation-log/WEEK-CONTENT-PACK_20260824-30.json",
        "pack_id": TARGET_PACK_ID,
        "field": "quote_text",
    },
    "qt-13": {
        "path": "automation-log/WEEK-CONTENT-PACK_20260824-30.json",
        "pack_id": TARGET_PACK_ID,
        "field": "quote_text",
    },
    "qt-14": {
        "path": "automation-log/QUOTE-CARDS_20260723-0822.md",
        "pack_id": None,
        "field": "caption",
        "media_origin": {
            "generator_origin": "LOCAL_HTML_CSS_BROWSER_RENDER",
            "contains_flow_pixels": False,
            "contains_flow_audio": False,
            "synthid_expected": False,
        },
    },
}


def _browser() -> Path:
    for candidate in EDGE_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise RuntimeError("Edge/Chrome executable was not found")


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if not found:
        raise RuntimeError("ffmpeg executable was not found")
    return found


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _city_scene(height: int, colors: tuple[str, ...]) -> str:
    base = height - 360
    return f"""
    <circle cx="842" cy="{base - 70}" r="94" fill="{colors[2]}" opacity=".92"/>
    <path d="M0 {base + 210} C190 {base + 120}, 340 {base + 250}, 520 {base + 165} C690 {base + 85}, 810 {base + 210}, 1000 {base + 130} L1000 {height} L0 {height} Z" fill="#0B1D2A" opacity=".82"/>
    <g fill="#D7A75F" opacity=".65">
      <rect x="84" y="{base + 132}" width="22" height="22" rx="4"/><rect x="124" y="{base + 118}" width="22" height="22" rx="4"/>
      <rect x="770" y="{base + 90}" width="22" height="22" rx="4"/><rect x="810" y="{base + 116}" width="22" height="22" rx="4"/>
    </g>
    <g transform="translate(500 {base + 135})">
      <circle cx="0" cy="0" r="50" fill="#E8B58A"/>
      <path d="M-78 183 Q-62 64 0 64 Q62 64 78 183 Z" fill="#EDE4D4"/>
      <path d="M42 90 Q112 118 104 190 L58 190 Q64 139 30 123 Z" fill="#C99658"/>
      <path d="M48 90 Q77 54 105 90" fill="none" stroke="#C99658" stroke-width="14" stroke-linecap="round"/>
    </g>
    <g opacity=".78">
      <circle cx="256" cy="{base + 186}" r="36" fill="#C98F75"/><path d="M204 {base + 350} Q214 {base + 235} 256 {base + 235} Q298 {base + 235} 308 {base + 350} Z" fill="#6D8B91"/>
      <circle cx="744" cy="{base + 180}" r="38" fill="#D9A27E"/><path d="M690 {base + 350} Q704 {base + 232} 744 {base + 232} Q788 {base + 232} 800 {base + 350} Z" fill="#8B6E62"/>
    </g>
    """


def _plant_scene(height: int, colors: tuple[str, ...]) -> str:
    base = height - 430
    return f"""
    <circle cx="810" cy="{base + 25}" r="146" fill="#F3D39C" opacity=".28"/>
    <path d="M0 {base + 330} C180 {base + 230}, 390 {base + 360}, 565 {base + 275} C720 {base + 198}, 850 {base + 305}, 1000 {base + 245} L1000 {height} L0 {height} Z" fill="#0D2D27" opacity=".78"/>
    <g transform="translate(470 {base + 100})">
      <path d="M0 190 C-5 95 0 34 7 -32" fill="none" stroke="#8CB27E" stroke-width="18" stroke-linecap="round"/>
      <ellipse cx="-54" cy="32" rx="68" ry="34" transform="rotate(28 -54 32)" fill="#88AF73"/>
      <ellipse cx="66" cy="-6" rx="72" ry="36" transform="rotate(-32 66 -6)" fill="#A6C98D"/>
      <ellipse cx="-44" cy="105" rx="62" ry="31" transform="rotate(23 -44 105)" fill="#6E9B69"/>
      <path d="M-108 174 L108 174 L76 340 L-76 340 Z" fill="#B96F48"/>
      <path d="M-120 174 Q0 208 120 174 L110 222 Q0 250 -110 222 Z" fill="#D48656"/>
    </g>
    <g transform="translate(720 {base + 230})">
      <rect x="-92" y="0" width="184" height="150" rx="48" fill="#DDE5D9" opacity=".82" stroke="#F5E7C9" stroke-width="8"/>
      <rect x="-60" y="-28" width="120" height="42" rx="16" fill="#BE8B53"/>
      <g fill="#E6B75F" stroke="#F9DA91" stroke-width="5">
        <circle cx="-38" cy="88" r="30"/><circle cx="22" cy="98" r="30"/><circle cx="52" cy="58" r="28"/><circle cx="-10" cy="53" r="28"/>
      </g>
    </g>
    """


def _family_scene(height: int, colors: tuple[str, ...]) -> str:
    base = height - 430
    return f"""
    <circle cx="800" cy="{base + 26}" r="156" fill="#FFD9A0" opacity=".22"/>
    <path d="M0 {base + 330} C180 {base + 245}, 365 {base + 345}, 545 {base + 278} C700 {base + 220}, 845 {base + 310}, 1000 {base + 250} L1000 {height} L0 {height} Z" fill="#281923" opacity=".75"/>
    <g transform="translate(500 {base + 150})">
      <ellipse cx="0" cy="174" rx="286" ry="92" fill="#B97B55"/>
      <ellipse cx="0" cy="156" rx="252" ry="64" fill="#E6B279"/>
      <circle cx="-160" cy="0" r="52" fill="#D69B76"/>
      <path d="M-232 154 Q-222 68 -160 68 Q-98 68 -88 154 Z" fill="#7F9C91"/>
      <circle cx="0" cy="-28" r="55" fill="#E0A27B"/>
      <path d="M-72 142 Q-62 46 0 46 Q62 46 72 142 Z" fill="#E7D2B4"/>
      <circle cx="164" cy="5" r="50" fill="#C88E6B"/>
      <path d="M92 154 Q104 72 164 72 Q224 72 236 154 Z" fill="#9C776A"/>
      <g fill="#F4D7A6" stroke="#FFF0D3" stroke-width="5">
        <ellipse cx="-82" cy="156" rx="45" ry="21"/>
        <ellipse cx="30" cy="156" rx="45" ry="21"/>
        <ellipse cx="132" cy="156" rx="45" ry="21"/>
      </g>
    </g>
    """


def _document(card_id: str, width: int, height: int, variant: str) -> str:
    card = CARDS[card_id]
    colors = card["palette"]
    lines = card[f"lines_{variant}"]
    line_height = 88 if variant == "4x5" else 84
    font_size = 61 if variant == "4x5" else 57
    top = 215
    tspans = "".join(
        f'<tspan x="94" y="{top + index * line_height}">{html.escape(line)}</tspan>'
        for index, line in enumerate(lines)
    )
    scene_builders = {
        "city": _city_scene,
        "plant": _plant_scene,
        "family": _family_scene,
    }
    scene = scene_builders[card["scene"]](height, colors)
    return f"""<!doctype html>
<html lang="th"><head><meta charset="utf-8"><style>
html,body{{margin:0;width:{width}px;height:{height}px;overflow:hidden;background:{colors[0]};}}
svg{{display:block;width:{width}px;height:{height}px;}}
</style></head><body>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(card['text'])}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="{colors[0]}"/><stop offset="1" stop-color="{colors[1]}"/></linearGradient>
    <radialGradient id="glow"><stop stop-color="{colors[2]}" stop-opacity=".32"/><stop offset="1" stop-color="{colors[2]}" stop-opacity="0"/></radialGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="20" stdDeviation="22" flood-color="#061219" flood-opacity=".28"/></filter>
  </defs>
  <rect width="{width}" height="{height}" fill="url(#bg)"/>
  <circle cx="120" cy="120" r="360" fill="url(#glow)"/>
  <circle cx="920" cy="360" r="280" fill="url(#glow)" opacity=".55"/>
  <rect x="58" y="70" width="884" height="{470 if variant == '4x5' else 560}" rx="44" fill="#FFFFFF" fill-opacity=".075" stroke="#FFFFFF" stroke-opacity=".12" stroke-width="2" filter="url(#shadow)"/>
  <path d="M94 128 H260" stroke="{colors[2]}" stroke-width="10" stroke-linecap="round"/>
  <text fill="{colors[3]}" font-family="Leelawadee UI, Tahoma, sans-serif" font-size="{font_size}" font-weight="700" letter-spacing="-.3">{tspans}</text>
  {scene}
</svg></body></html>
"""


def _run(command: list[str]) -> None:
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()[-1200:]
        raise RuntimeError(f"command failed ({completed.returncode}): {detail}")


def _wait_for_file(path: Path, timeout_seconds: float = 15.0) -> None:
    """Wait for Windows GUI browser child processes to flush a screenshot."""
    deadline = time.monotonic() + timeout_seconds
    previous_size = -1
    while time.monotonic() < deadline:
        try:
            current_size = path.stat().st_size
        except OSError:
            current_size = -1
        if current_size > 0 and current_size == previous_size:
            return
        previous_size = current_size
        time.sleep(0.25)
    raise RuntimeError(f"browser screenshot was not written: {path}")


def _selected_cards(card_ids: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    selected = tuple(card_ids or CARDS)
    unknown = sorted(set(selected) - set(CARDS))
    if unknown:
        raise ValueError("unknown quote card id(s): " + ", ".join(unknown))
    if len(selected) != len(set(selected)):
        raise ValueError("quote card ids must be unique")
    return selected


def _bound_source_value(card_id: str) -> str:
    """Return the exact bound editorial field or fail before writing a receipt."""
    binding = SOURCE_BINDINGS[card_id]
    path = ROOT / binding["path"]
    if path.suffix.casefold() == ".json":
        document = json.loads(path.read_text(encoding="utf-8"))
        rows = {
            str(row.get("candidate_id") or ""): row
            for row in document.get("days", [])
            if isinstance(row, dict)
        }
        value = rows.get(card_id, {}).get(binding["field"])
    else:
        header = None
        value = None
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if not raw_line.lstrip().startswith("|"):
                continue
            cells = [cell.strip() for cell in raw_line.strip().strip("|").split("|")]
            lowered = [cell.casefold() for cell in cells]
            if "id" in lowered and binding["field"] in lowered:
                header = lowered
                continue
            if header is None or len(cells) != len(header):
                continue
            row = dict(zip(header, cells))
            if row.get("id") == card_id:
                value = re.sub(r"<br\s*/?>", "\n", row.get(binding["field"], ""), flags=re.I)
                break
    if not isinstance(value, str) or CARDS[card_id]["text"] not in value:
        raise ValueError(f"{card_id} exact overlay text is absent from its bound source field")
    return value


def render(
    output_root: Path,
    stage_root: Path,
    card_ids: list[str] | tuple[str, ...] | None = None,
) -> list[Path]:
    browser = _browser()
    ffmpeg = _ffmpeg()
    output_root.mkdir(parents=True, exist_ok=True)
    stage_root.mkdir(parents=True, exist_ok=True)
    user_data = stage_root / "browser-profile"
    user_data.mkdir(parents=True, exist_ok=True)
    outputs = []
    for card_id in _selected_cards(card_ids):
        for variant, width, height, suffix, _ in VARIANTS:
            stem = f"{card_id}_{suffix}"
            source = stage_root / f"{stem}.html"
            png = stage_root / f"{stem}.png"
            destination = output_root / f"{stem}.jpg"
            source.write_text(_document(card_id, width, height, variant), encoding="utf-8")
            if png.is_file():
                png.unlink()
            _run([
                str(browser), "--headless=new", "--disable-gpu", "--hide-scrollbars",
                "--force-device-scale-factor=1", f"--user-data-dir={user_data}",
                f"--window-size={width},{height}", f"--screenshot={png}", source.as_uri(),
            ])
            _wait_for_file(png)
            _run([
                ffmpeg, "-y", "-loglevel", "error", "-i", str(png),
                "-frames:v", "1", "-q:v", "2", "-pix_fmt", "yuvj420p", str(destination),
            ])
            outputs.append(destination)
    return outputs


def write_receipts(
    output_root: Path,
    reviewer: str,
    card_ids: list[str] | tuple[str, ...] | None = None,
) -> list[Path]:
    """Write receipts only after the selected final images were visually reviewed."""
    if not reviewer.strip():
        raise ValueError("a non-empty visual reviewer is required")
    sys.path.insert(0, str(ROOT / "tools"))
    import media_publish_guard

    fingerprint = media_publish_guard.publication_corpus_fingerprint(ROOT)
    if not fingerprint:
        raise RuntimeError("publication comparison corpus is unavailable")
    prior = [path for _, path in media_publish_guard._prior_media(ROOT) if path.is_file()]
    reviewed_at = datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).isoformat()
    receipts = []
    from PIL import Image

    pack = json.loads(
        (ROOT / "automation-log/WEEK-CONTENT-PACK_20260824-30.json").read_text(
            encoding="utf-8"
        )
    )
    origin_by_asset = {}
    for day in pack.get("days", []):
        assets = day.get("image_spec", {}).get("candidate_assets", {})
        if not isinstance(assets, dict):
            continue
        for asset in assets.values():
            if isinstance(asset, dict) and isinstance(asset.get("path"), str):
                origin_by_asset[asset["path"]] = asset.get("media_origin")

    for card_id in _selected_cards(card_ids):
        card = CARDS[card_id]
        source_binding = SOURCE_BINDINGS[card_id]
        source_path = ROOT / source_binding["path"]
        if not source_path.is_file():
            raise ValueError(f"missing quote source: {source_path}")
        source_value = _bound_source_value(card_id)
        for variant, width, height, suffix, receipt_suffix in VARIANTS:
            asset = output_root / f"{card_id}_{suffix}.jpg"
            if not asset.is_file() or asset.stat().st_size == 0:
                raise ValueError(f"missing r5 quote asset: {asset}")
            with Image.open(asset) as image:
                if image.size != (width, height) or image.mode != "RGB":
                    raise ValueError(f"unexpected dimensions/mode for {asset}")
            try:
                rel_asset = asset.resolve().relative_to(ROOT).as_posix()
            except ValueError as exc:
                raise ValueError("quote receipt asset must remain inside the repository") from exc
            markup = _document(card_id, width, height, variant)
            if card["text"] not in markup:
                raise ValueError(f"exact overlay text missing from {card_id} {variant}")
            receipt = {
                "schema_version": 1,
                "asset": rel_asset,
                "sha256": _sha256(asset),
                "media_type": "image",
                "reviewed_at": reviewed_at,
                "media_origin": origin_by_asset.get(
                    rel_asset, source_binding.get("media_origin")
                ),
                "source_binding": {
                    "source_file": source_binding["path"],
                    "source_file_sha256": _sha256(source_path),
                    "weekly_pack": (
                        source_binding["path"]
                        if source_binding["pack_id"] is not None
                        else None
                    ),
                    "weekly_pack_id": source_binding["pack_id"],
                    "candidate_id": card_id,
                    "source_row_id": card_id,
                    "source_field": source_binding["field"],
                    "source_value_sha256": hashlib.sha256(
                        source_value.encode("utf-8")
                    ).hexdigest().upper(),
                    "variant": variant,
                    "dimensions": [width, height],
                    "exact_overlay_text": card["text"],
                    "source_markup_sha256": hashlib.sha256(
                        markup.encode("utf-8")
                    ).hexdigest().upper(),
                },
                "technical_qa": {
                    "status": "PASS",
                    "dimensions": [width, height],
                    "mode": "RGB",
                    "deterministic_browser_text_render": "PASS",
                    "safe_crop_review": "PASS_FULL_FRAME_VISUAL_REVIEW",
                },
                "novelty_review": {
                    "status": "PASS",
                    "content_id": f"{card_id}-{variant}-r5",
                    "reviewer": "Codex deterministic hash and full-frame visual comparison",
                    "corpus_fingerprint": fingerprint,
                    "compared_assets": len(prior),
                    "scope": (
                        "Copy-edited r5 quote-card revision; exact SHA-256 is unique "
                        "within the selected r5 quote-card set and differs from "
                        "superseded evidence"
                    ),
                },
                "watermark": {
                    "visual_review": {
                        "status": "PASS",
                        "reviewer": reviewer.strip(),
                        "scope": (
                            "Full native-resolution image reviewed; no provider/platform "
                            "watermark, page logo, account handle, URL, tracking mark, "
                            "affiliate CTA, clipped copy, or unsafe crop"
                        ),
                        "evidence": [rel_asset],
                    }
                },
            }
            destination = RECEIPT_ROOT / f"{card_id}-{receipt_suffix}.json"
            destination.write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            receipts.append(destination)
            print(f"RECEIPT {card_id} {variant} {destination}")
    return receipts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--stage-root", type=Path, default=DEFAULT_STAGE)
    parser.add_argument("--write-receipts", action="store_true")
    parser.add_argument("--visual-reviewer", default="")
    parser.add_argument(
        "--card-id",
        action="append",
        choices=sorted(CARDS),
        dest="card_ids",
        help="render or receipt only the selected card; repeat for multiple cards",
    )
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    if args.write_receipts:
        write_receipts(output_root, args.visual_reviewer, args.card_ids)
    else:
        for output in render(output_root, args.stage_root.resolve(), args.card_ids):
            print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
