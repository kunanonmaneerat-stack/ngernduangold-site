#!/usr/bin/env python3
"""Render and audit the seven local-only TikTok candidates for 2026-08-24..30.

The visual track is built offline from deterministic HTML/SVG frames rendered by
the installed browser.  Narration is synthesized locally with the installed
Windows Thai voice from the exact ``voiceover`` field in the weekly content
pack.  The renderer never adds a page identity, handle, URL, tracking marker,
provider mark, platform mark, affiliate call-to-action, or stock footage.

Receipts are deliberately a second step.  ``--write-receipts`` must only be run
after a reviewer has inspected the generated full-resolution scene frames.
"""

from __future__ import annotations

import argparse
from array import array
from datetime import datetime
import hashlib
import html
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = ROOT / "automation-log" / "WEEK-CONTENT-PACK_20260824-30.json"
OUTPUT_ROOT = ROOT / "reels" / "week-20260824-30-r5"
STAGE_ROOT = ROOT / ".local-private" / "runtime" / "week-tiktok-render-r5"
EVIDENCE_ROOT = (
    ROOT / "automation-log" / "media-qa" / "evidence" / "week-20260824-30-r5"
)
RECEIPT_ROOT = ROOT / "automation-log" / "media-qa"
RENDER_MANIFEST = STAGE_ROOT / "render-manifest.json"
TTS_SCRIPT = ROOT / "tiktok-pipeline" / "src" / "08_tts_windows.ps1"
FINALIZER = ROOT / "tiktok-pipeline" / "src" / "09_finalize_video.py"
FPS = 24
WIDTH = 1080
HEIGHT = 1920
VOICE_LANGUAGE = "th-TH"
VOICE_NAME = "Microsoft Pattara"
VOICE_RATE = 0.78
TARGET_PACK_ID = "week-content-20260824-30-r5"
EXPECTED_IDS = (
    "wk36-sf01",
    "wk36-sf02",
    "qt-12",
    "wk36-sf03",
    "wk36-sf04",
    "qt-13",
    "wk36-sf05",
)

MAX_DIGITAL_SILENCE_SECONDS = 1.5
SILENCE_THRESHOLD_DBFS = -50.0
TAIL_SILENCE_TARGET_SECONDS = 0.75
TAIL_SILENCE_MAX_SECONDS = 1.0
MIN_SCENE_DWELL_SECONDS = 1.5
MIN_END_CARD_DWELL_SECONDS = 2.0
AUDIO_LUFS_TARGET = -14.5

BROWSERS = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
)

DESIGNS = {
    "wk36-sf01": {"bg": "#10293A", "mid": "#1E5663", "accent": "#F2C47C", "icon": "notebook"},
    "wk36-sf02": {"bg": "#22233D", "mid": "#55456B", "accent": "#F4BD8A", "icon": "pause"},
    "qt-12": {"bg": "#142C3E", "mid": "#436470", "accent": "#F0C681", "icon": "compare"},
    "wk36-sf03": {"bg": "#26344A", "mid": "#496477", "accent": "#F0B978", "icon": "value"},
    "wk36-sf04": {"bg": "#173A39", "mid": "#39706A", "accent": "#E8C17B", "icon": "track"},
    "qt-13": {"bg": "#173C34", "mid": "#4F745B", "accent": "#E9B66B", "icon": "plant"},
    "wk36-sf05": {"bg": "#1D2944", "mid": "#536786", "accent": "#F0C477", "icon": "plan"},
}

FORBIDDEN_VISIBLE = (
    "เงินเดือนสมองทอง",
    "@ngernduangold",
    "ngernduangold",
    "http://",
    "https://",
    "www.",
    "utm_",
    "ลิงก์",
    "affiliate",
    "พันธมิตร",
    "TikTok",
    "Facebook",
    "Instagram",
    "Pantip",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def stable_json_sha256(value: object) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest().upper()


def _replace_required(value: str, old: str, new: str, label: str) -> str:
    """Apply an idempotent approved copy change and fail on unknown source text."""
    if new in value and old not in value:
        return value
    if old not in value:
        raise ValueError(f"approved r5 copy source drifted for {label}")
    return value.replace(old, new)


def _set_exact(value: object, old: object, new: object, label: str) -> object:
    if value not in (old, new):
        raise ValueError(f"approved r5 exact copy source drifted for {label}")
    return new


def apply_r5_copy_updates(source_pack: dict) -> dict:
    """Project the independently reviewed r5 copy without mutating the live pack."""
    pack = json.loads(json.dumps(source_pack, ensure_ascii=False))
    by_id = {day.get("candidate_id"): day for day in pack.get("days") or []}
    if set(by_id) != set(EXPECTED_IDS):
        raise ValueError("cannot apply r5 copy updates to an unexpected candidate set")

    sf01 = by_id["wk36-sf01"]["tiktok_draft"]
    sf01["voiceover"] = _replace_required(
        sf01["voiceover"],
        "แค่เลือกดูให้ชัดหนึ่งช่องก่อน",
        "แค่เลือกหนึ่งช่องมาดูให้ชัดก่อน",
        "wk36-sf01 voiceover",
    )

    qt12 = by_id["qt-12"]
    old_quote = (
        "อย่าเปรียบเทียบกระเป๋าเงินของเรากับวิถีชีวิตของคนอื่น "
        "เพราะเราไม่เห็นหนี้ของเขา"
    )
    new_quote = (
        "อย่าเอาสถานะการเงินของเราไปเทียบกับภาพชีวิตของคนอื่น "
        "เพราะเราไม่เห็นภาพการเงินทั้งหมดของเขา"
    )
    for key in ("quote_text", "threads_text", "facebook_text"):
        qt12[key] = _replace_required(qt12[key], old_quote, new_quote, f"qt-12 {key}")
    qt12["image_spec"]["exact_overlay_text"] = _replace_required(
        qt12["image_spec"]["exact_overlay_text"],
        old_quote,
        new_quote,
        "qt-12 image overlay",
    )
    qt12_draft = qt12["tiktok_draft"]
    qt12_draft["hook"] = _set_exact(
        qt12_draft["hook"],
        "เราเห็นวิถีชีวิตของคนอื่น แต่ไม่เห็นภาระทั้งหมด",
        "อย่าเอาสถานะการเงินของเราไปเทียบกับภาพชีวิตของคนอื่น",
        "qt-12 hook",
    )
    qt12_draft["voiceover"] = _set_exact(
        qt12_draft["voiceover"],
        (
            "อย่าใช้ภาพที่เห็นภายนอกมาตัดสินกระเป๋าเงินของเรา เพราะเราไม่เห็น"
            "ภาระทั้งหมดของเขา กลับมาดูเป้าหมายของเราเอง"
        ),
        new_quote + " กลับมาดูเป้าหมายของเราเอง",
        "qt-12 voiceover",
    )
    qt12_draft["onscreen_text"] = _set_exact(
        qt12_draft["onscreen_text"],
        ["เห็นวิถีชีวิต", "ไม่เห็นภาระทั้งหมด", "กลับมาดูเป้าหมายเรา"],
        [
            "สถานะการเงินของเรา",
            "ภาพชีวิตของคนอื่น",
            "ไม่เห็นภาพการเงินทั้งหมด",
            "กลับมาดูเป้าหมายเรา",
        ],
        "qt-12 onscreen text",
    )

    qt13 = by_id["qt-13"]
    old_qt13 = "แค่รดน้ำมันทุกเดือน"
    new_qt13 = "แค่ดูแลมันทุกเดือน"
    for key in ("quote_text", "threads_text", "facebook_text"):
        qt13[key] = _replace_required(qt13[key], old_qt13, new_qt13, f"qt-13 {key}")
    qt13["image_spec"]["exact_overlay_text"] = _replace_required(
        qt13["image_spec"]["exact_overlay_text"],
        old_qt13,
        new_qt13,
        "qt-13 image overlay",
    )

    sf04 = by_id["wk36-sf04"]
    sf04["threads_text"] = _replace_required(
        sf04["threads_text"],
        "วันนี้ลองจดชื่อรายจ่ายทุกครั้งที่เงินออก",
        "ทุกครั้งที่เงินออก ลองจดรายการรายจ่ายไว้",
        "wk36-sf04 Threads",
    )
    sf04["facebook_text"] = _replace_required(
        sf04["facebook_text"],
        "วันนี้ลองจดชื่อรายจ่ายทุกครั้งที่เงินออก",
        "ทุกครั้งที่เงินออก ลองจดรายการรายจ่ายไว้",
        "wk36-sf04 Facebook",
    )
    sf04_draft = sf04["tiktok_draft"]
    sf04_draft["voiceover"] = _set_exact(
        sf04_draft["voiceover"],
        (
            "ทุกครั้งที่เงินออก ลองจดชื่อรายจ่ายไว้ก่อน โดยยังไม่ต้องตัดสินตัวเอง "
            "เป้าหมายแรกคือเห็นภาพ"
        ),
        (
            "ทุกครั้งที่เงินออก ลองจดรายการรายจ่ายไว้ โดยยังไม่ต้องตัดสินตัวเอง "
            "เป้าหมายแรกคือเห็นภาพ"
        ),
        "wk36-sf04 voiceover",
    )
    sf04_draft["onscreen_text"] = _set_exact(
        sf04_draft["onscreen_text"],
        ["เงินออกเมื่อไร", "จดชื่อไว้", "เห็นภาพก่อน"],
        ["เงินออกเมื่อไร", "จดรายการไว้", "เห็นภาพก่อน"],
        "wk36-sf04 onscreen text",
    )

    sf05 = by_id["wk36-sf05"]
    sf05["threads_text"] = _replace_required(
        sf05["threads_text"],
        "อาทิตย์หน้าเลือกไว้ 3 อย่าง: เก็บไว้ 1 ลดลง 1 และทดลองเปลี่ยน 1",
        "เก็บ 1 พฤติกรรม ลด 1 รายจ่าย และทดลองเปลี่ยน 1 วิธีใช้เงิน",
        "wk36-sf05 Threads",
    )
    sf05["facebook_text"] = _replace_required(
        sf05["facebook_text"],
        (
            "- เก็บพฤติกรรมที่มีคุณค่าไว้ 1 อย่าง\n"
            "- ลดสิ่งที่ให้คุณค่าน้อยลง 1 อย่าง\n"
            "- ทดลองเปลี่ยนวิธีใช้เงิน 1 อย่าง"
        ),
        "- เก็บ 1 พฤติกรรม\n- ลด 1 รายจ่าย\n- ทดลองเปลี่ยน 1 วิธีใช้เงิน",
        "wk36-sf05 Facebook",
    )
    sf05_draft = sf05["tiktok_draft"]
    sf05_draft["voiceover"] = _set_exact(
        sf05_draft["voiceover"],
        (
            "เลือกเก็บไว้หนึ่งอย่าง ลดลงหนึ่งอย่าง และทดลองเปลี่ยนหนึ่งอย่าง "
            "เขียนให้ชัด แล้วเริ่มจากสิ่งที่ทำได้จริง"
        ),
        (
            "เก็บหนึ่งพฤติกรรม ลดหนึ่งรายจ่าย และทดลองเปลี่ยนหนึ่งวิธีใช้เงิน "
            "เขียนให้ชัด แล้วเริ่มจากสิ่งที่ทำได้จริง"
        ),
        "wk36-sf05 voiceover",
    )
    sf05_draft["onscreen_text"] = _set_exact(
        sf05_draft["onscreen_text"],
        ["เก็บ 1", "ลด 1", "ทดลอง 1"],
        ["เก็บ 1 พฤติกรรม", "ลด 1 รายจ่าย", "ทดลอง 1 วิธีใช้เงิน"],
        "wk36-sf05 onscreen text",
    )

    pack["pack_id"] = TARGET_PACK_ID
    return pack


def _run(command: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout or "command failed").strip()[-2000:]
        raise RuntimeError(f"command failed ({result.returncode}): {detail}")
    return result


def _browser() -> Path:
    for candidate in BROWSERS:
        if candidate.is_file():
            return candidate
    raise RuntimeError("Edge/Chrome executable was not found")


def _binary(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f"{name} executable was not found")
    return found


def _content_payload(draft: dict) -> dict:
    """The immutable creative payload; excludes mutable production status fields."""
    return {
        "duration_target_seconds": draft["duration_target_seconds"],
        "hook": draft["hook"],
        "voiceover": draft["voiceover"],
        "shots": draft["shots"],
        "onscreen_text": draft["onscreen_text"],
        "end_card": draft["end_card"],
    }


def load_candidates(
    pack_path: Path = PACK_PATH, *, project_r5_copy: bool = True
) -> tuple[dict, list[dict]]:
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    if project_r5_copy:
        pack = apply_r5_copy_updates(pack)
    if pack.get("state") != "DRAFT_ONLY":
        raise ValueError("weekly pack must remain DRAFT_ONLY")
    if pack.get("public_identity") != "เงินเดือนสมองทอง":
        raise ValueError("unexpected public identity in weekly pack")
    rules = pack.get("content_rules") or {}
    if rules.get("body_url") is not False or rules.get("affiliate_cta") is not False:
        raise ValueError("weekly pack no-URL/no-affiliate contract drifted")
    if rules.get("provider_or_platform_watermark_allowed") is not False:
        raise ValueError("weekly pack watermark contract drifted")
    if rules.get("logo_or_handle_overlay_allowed") is not False:
        raise ValueError("weekly pack identity-overlay contract drifted")
    if rules.get("ai_disclosure_required") is not True:
        raise ValueError("weekly pack AI-disclosure contract drifted")

    days = pack.get("days") or []
    ids = tuple(day.get("candidate_id") for day in days)
    if ids != EXPECTED_IDS:
        raise ValueError(f"unexpected candidate order/set: {ids!r}")
    seen_text = set()
    for day in days:
        validate_candidate(day, seen_text)
    return pack, days


def validate_candidate(day: dict, seen_text: set[str] | None = None) -> None:
    candidate_id = str(day.get("candidate_id") or "")
    if candidate_id not in DESIGNS:
        raise ValueError(f"missing deterministic design for {candidate_id!r}")
    draft = day.get("tiktok_draft")
    if not isinstance(draft, dict):
        raise ValueError(f"{candidate_id}: tiktok_draft missing")
    required = (
        "duration_target_seconds",
        "hook",
        "voiceover",
        "shots",
        "onscreen_text",
        "end_card",
    )
    missing = [key for key in required if key not in draft]
    if missing:
        raise ValueError(f"{candidate_id}: missing {', '.join(missing)}")
    duration = float(draft["duration_target_seconds"])
    if not 15 <= duration <= 25:
        raise ValueError(f"{candidate_id}: duration outside 15-25 seconds")
    if not isinstance(draft["onscreen_text"], list) or not draft["onscreen_text"]:
        raise ValueError(f"{candidate_id}: onscreen_text must be non-empty")
    if not isinstance(draft["shots"], list) or not draft["shots"]:
        raise ValueError(f"{candidate_id}: shots must be non-empty")
    if draft["end_card"] != "ข้อมูลเพื่อการศึกษา · ผลิตด้วย AI":
        raise ValueError(f"{candidate_id}: exact AI disclosure drifted")

    visible = scene_texts(day)
    voiceover = str(draft["voiceover"]).strip()
    if not voiceover:
        raise ValueError(f"{candidate_id}: voiceover is blank")
    combined = "\n".join(visible + [voiceover])
    for forbidden in FORBIDDEN_VISIBLE:
        if forbidden.casefold() in combined.casefold():
            raise ValueError(f"{candidate_id}: forbidden visible/audio token {forbidden!r}")
    if "@" in combined or re.search(r"\b(?:[a-z0-9-]+\.)+(?:com|net|org|co|th)\b", combined, re.I):
        raise ValueError(f"{candidate_id}: handle or URL-like token found")
    if seen_text is not None:
        signature = "\n".join(visible)
        if signature in seen_text:
            raise ValueError(f"{candidate_id}: duplicate visible-copy sequence")
        seen_text.add(signature)


def scene_texts(day: dict) -> list[str]:
    draft = day["tiktok_draft"]
    return [
        str(draft["hook"]).strip(),
        *(str(item).strip() for item in draft["onscreen_text"]),
        str(draft["end_card"]).strip(),
    ]


def scene_frame_counts(duration_seconds: float, scene_count: int) -> list[int]:
    total = round(float(duration_seconds) * FPS)
    if scene_count < 2:
        raise ValueError("at least two scenes are required")
    normal_minimum = math.ceil(MIN_SCENE_DWELL_SECONDS * FPS)
    end_minimum = math.ceil(MIN_END_CARD_DWELL_SECONDS * FPS)
    frames = [normal_minimum] * (scene_count - 1) + [end_minimum]
    remaining = total - sum(frames)
    if remaining < 0:
        raise ValueError(
            "planned voice-bound duration is too short for readable scene dwell"
        )
    for index in range(remaining):
        frames[index % scene_count] += 1
    if min(frames[:-1]) < normal_minimum or frames[-1] < end_minimum:
        raise AssertionError("minimum scene dwell allocation drift")
    if sum(frames) != total:
        raise AssertionError("scene frame allocation drift")
    return frames


def _icon(kind: str, accent: str, index: int) -> str:
    pale = "#F8F3E9"
    muted = "#AFC5C9"
    if kind == "notebook":
        return f"""
        <g transform="translate(185 85) rotate({-2 + index})">
          <rect x="0" y="0" width="710" height="470" rx="42" fill="{pale}" opacity=".96"/>
          <path d="M236 42V430M474 42V430" stroke="#79959C" stroke-width="9" opacity=".55"/>
          <path d="M72 102H188M72 164H188M310 102H426M310 164H426M548 102H650M548 164H650" stroke="#55727B" stroke-width="13" stroke-linecap="round" opacity=".66"/>
          <circle cx="{118 + (index % 3) * 238}" cy="300" r="54" fill="none" stroke="{accent}" stroke-width="18"/>
          <path d="M-28 56H28M-28 130H28M-28 204H28M-28 278H28M-28 352H28" stroke="{accent}" stroke-width="13" stroke-linecap="round"/>
        </g>"""
    if kind == "pause":
        return f"""
        <g transform="translate(330 60)">
          <rect x="0" y="0" width="420" height="590" rx="66" fill="{pale}" opacity=".96"/>
          <rect x="38" y="76" width="344" height="394" rx="30" fill="#E5DDEB"/>
          <path d="M90 168H330M90 238H286M90 308H314" stroke="#655A78" stroke-width="16" stroke-linecap="round" opacity=".76"/>
          <circle cx="210" cy="526" r="24" fill="{accent}"/>
          <path d="M328 44A104 104 0 1 0 414 198A83 83 0 1 1 328 44Z" fill="{accent}" transform="translate(130 -40)"/>
          <path d="M-74 452H86" stroke="{accent}" stroke-width="24" stroke-linecap="round"/>
          <path d="M-20 390V514" stroke="{accent}" stroke-width="24" stroke-linecap="round"/>
        </g>"""
    if kind == "compare":
        return f"""
        <g transform="translate(110 90)">
          <g opacity=".58"><circle cx="150" cy="120" r="66" fill="#D8A480"/><path d="M48 430Q62 220 150 220Q238 220 252 430Z" fill="{muted}"/></g>
          <g><circle cx="430" cy="90" r="72" fill="#E6B58C"/><path d="M312 445Q330 200 430 200Q530 200 548 445Z" fill="{pale}"/><path d="M486 242Q628 294 604 448H512Q528 340 458 306Z" fill="{accent}"/><path d="M490 250Q546 174 610 250" fill="none" stroke="{accent}" stroke-width="22" stroke-linecap="round"/></g>
          <g opacity=".58"><circle cx="730" cy="130" r="66" fill="#C99074"/><path d="M628 430Q642 230 730 230Q818 230 832 430Z" fill="#8A7791"/></g>
          <path d="M330 500H536" stroke="{accent}" stroke-width="18" stroke-linecap="round"/>
        </g>"""
    if kind == "value":
        return f"""
        <g transform="translate(240 58)">
          <path d="M0 0H600V560L550 524L500 560L450 524L400 560L350 524L300 560L250 524L200 560L150 524L100 560L50 524L0 560Z" fill="{pale}" opacity=".96"/>
          <path d="M84 112H420M84 190H498M84 268H372" stroke="#708B96" stroke-width="18" stroke-linecap="round" opacity=".7"/>
          <path d="M458 326C398 256 286 338 458 482C630 338 518 256 458 326Z" fill="{accent}"/>
          <path d="M80 414H246" stroke="#708B96" stroke-width="18" stroke-linecap="round" opacity=".62"/>
        </g>"""
    if kind == "track":
        return f"""
        <g transform="translate(165 80)">
          <rect x="0" y="70" width="750" height="430" rx="64" fill="{pale}" opacity=".95"/>
          <rect x="430" y="176" width="350" height="180" rx="52" fill="#D7E1D8" stroke="{accent}" stroke-width="12"/>
          <circle cx="540" cy="266" r="34" fill="{accent}"/>
          <path d="M92 170H344M92 244H304M92 318H364" stroke="#587C78" stroke-width="17" stroke-linecap="round"/>
          <g fill="{accent}" stroke="#F8D99E" stroke-width="8"><circle cx="146" cy="34" r="48"/><circle cx="254" cy="34" r="48"/><circle cx="362" cy="34" r="48"/></g>
          <path d="M112 412L164 462L270 360" fill="none" stroke="#4B8A72" stroke-width="25" stroke-linecap="round" stroke-linejoin="round"/>
        </g>"""
    if kind == "plant":
        return f"""
        <g transform="translate(160 38)">
          <path d="M348 434C340 304 344 180 366 58" fill="none" stroke="#9FC184" stroke-width="22" stroke-linecap="round"/>
          <ellipse cx="276" cy="170" rx="102" ry="52" transform="rotate(28 276 170)" fill="#8EB177"/>
          <ellipse cx="456" cy="112" rx="110" ry="55" transform="rotate(-31 456 112)" fill="#AED090"/>
          <ellipse cx="290" cy="290" rx="94" ry="48" transform="rotate(24 290 290)" fill="#729C6D"/>
          <path d="M190 388H514L464 618H240Z" fill="#BD724B"/>
          <path d="M170 388Q352 442 534 388L516 452Q352 500 188 452Z" fill="#D88A58"/>
          <rect x="556" y="330" width="236" height="248" rx="66" fill="{pale}" opacity=".86" stroke="{accent}" stroke-width="10"/>
          <rect x="602" y="286" width="144" height="58" rx="20" fill="#B5844F"/>
          <g fill="{accent}" stroke="#F8D898" stroke-width="7"><circle cx="624" cy="500" r="42"/><circle cx="706" cy="508" r="42"/><circle cx="668" cy="430" r="40"/></g>
        </g>"""
    if kind == "plan":
        return f"""
        <g transform="translate(170 55)">
          <rect x="0" y="0" width="740" height="570" rx="56" fill="{pale}" opacity=".96"/>
          <path d="M106 148H630M106 286H630M106 424H630" stroke="#718AA0" stroke-width="14" stroke-linecap="round" opacity=".56"/>
          <circle cx="116" cy="148" r="52" fill="{accent}"/><circle cx="116" cy="286" r="52" fill="#83A98F"/><circle cx="116" cy="424" r="52" fill="#A58AB5"/>
          <path d="M94 148L110 165L142 126M94 286L110 303L142 264M94 424L110 441L142 402" fill="none" stroke="#FFFFFF" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M208 148H592M208 286H540M208 424H612" stroke="#536B7B" stroke-width="20" stroke-linecap="round"/>
        </g>"""
    raise ValueError(f"unknown icon kind {kind!r}")


def _font_size(text: str, final: bool) -> int:
    length = len(text)
    if final:
        return 58
    if length <= 16:
        return 104
    if length <= 28:
        return 88
    if length <= 42:
        return 78
    if length <= 58:
        return 68
    return 60


def scene_document(day: dict, text: str, index: int, count: int) -> str:
    candidate_id = day["candidate_id"]
    design = DESIGNS[candidate_id]
    final = index == count - 1
    dots = "".join(
        f'<span class="dot{" active" if dot == index else ""}"></span>'
        for dot in range(count)
    )
    icon = _icon(design["icon"], design["accent"], index)
    disclosure = "" if final else html.escape(day["tiktok_draft"]["end_card"])
    return f"""<!doctype html>
<html lang="th"><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}} html,body{{margin:0;width:{WIDTH}px;height:{HEIGHT}px;overflow:hidden}}
body{{font-family:"Leelawadee UI",Tahoma,sans-serif;color:#F9F6EE;background:{design['bg']}}}
.canvas{{position:relative;width:{WIDTH}px;height:{HEIGHT}px;overflow:hidden;background:
radial-gradient(circle at {18 + index * 11}% {13 + index * 7}%,{design['accent']}44 0,transparent 31%),
linear-gradient(155deg,{design['bg']} 0%,{design['mid']} 62%,{design['bg']} 100%)}}
.orb{{position:absolute;border-radius:999px;border:2px solid #FFFFFF18}}
.o1{{width:520px;height:520px;left:-210px;top:1020px}} .o2{{width:360px;height:360px;right:-130px;top:210px}}
.rule{{position:absolute;left:108px;top:196px;width:172px;height:13px;border-radius:20px;background:{design['accent']}}}
.copy{{position:absolute;left:104px;right:104px;top:266px;min-height:520px;display:flex;align-items:center;
font-size:{_font_size(text, final)}px;font-weight:700;line-height:1.28;letter-spacing:-.55px;text-wrap:balance;overflow-wrap:anywhere;
text-shadow:0 14px 40px #06141C55}}
.visual{{position:absolute;left:0;right:0;top:912px;height:670px}}
.visual svg{{width:100%;height:100%;display:block;filter:drop-shadow(0 26px 30px #07121B42)}}
.disclosure{{position:absolute;left:110px;right:174px;bottom:166px;font-size:30px;line-height:1.35;color:#E7EDF0;opacity:.83}}
.progress{{position:absolute;left:110px;bottom:108px;display:flex;gap:16px}}
.dot{{width:26px;height:8px;border-radius:8px;background:#FFFFFF3D}} .dot.active{{width:72px;background:{design['accent']}}}
</style></head><body><main class="canvas">
<div class="orb o1"></div><div class="orb o2"></div><div class="rule"></div>
<div class="copy">{html.escape(text)}</div>
<div class="visual"><svg viewBox="0 0 1080 670" aria-hidden="true">{icon}</svg></div>
<div class="disclosure">{disclosure}</div><div class="progress">{dots}</div>
</main></body></html>"""


def _wait_for_file(path: Path, timeout_seconds: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    previous_size = -1
    while time.monotonic() < deadline:
        try:
            size = path.stat().st_size
        except OSError:
            size = -1
        if size > 0 and size == previous_size:
            return
        previous_size = size
        time.sleep(0.25)
    raise RuntimeError(f"browser screenshot was not written: {path}")


def _render_scene_frames(day: dict, browser: Path, profile: Path) -> list[Path]:
    candidate_id = day["candidate_id"]
    evidence_dir = EVIDENCE_ROOT / candidate_id
    stage_dir = STAGE_ROOT / candidate_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stage_dir.mkdir(parents=True, exist_ok=True)
    texts = scene_texts(day)
    frames = []
    for index, text in enumerate(texts):
        source = stage_dir / f"scene-{index + 1:02d}.html"
        destination = evidence_dir / f"scene-{index + 1:02d}.png"
        source.write_text(scene_document(day, text, index, len(texts)), encoding="utf-8")
        destination.unlink(missing_ok=True)
        _run(
            [
                str(browser),
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--force-device-scale-factor=1",
                f"--user-data-dir={profile}",
                f"--window-size={WIDTH},{HEIGHT}",
                f"--screenshot={destination}",
                source.as_uri(),
            ],
            timeout=60,
        )
        _wait_for_file(destination)
        frames.append(destination)
    _contact_sheet(frames, evidence_dir / "contact-sheet.png")
    return frames


def _contact_sheet(frames: list[Path], destination: Path) -> None:
    from PIL import Image

    thumb_w, thumb_h, columns = 360, 640, 3
    rows = (len(frames) + columns - 1) // columns
    canvas = Image.new("RGB", (thumb_w * columns, thumb_h * rows), "#0B1420")
    for index, frame in enumerate(frames):
        with Image.open(frame) as image:
            thumb = image.convert("RGB").resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        canvas.paste(thumb, ((index % columns) * thumb_w, (index // columns) * thumb_h))
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, optimize=True)


def _render_silent_video(frames: list[Path], frame_counts: list[int], destination: Path) -> None:
    ffmpeg = _binary("ffmpeg")
    inputs = []
    filters = []
    labels = []
    for index, (frame, count) in enumerate(zip(frames, frame_counts)):
        inputs.extend(["-i", str(frame)])
        labels.append(f"[v{index}]")
        filters.append(
            f"[{index}:v]scale={WIDTH}:{HEIGHT},"
            "zoompan=z='min(zoom+0.00042,1.038)':"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={count}:s={WIDTH}x{HEIGHT}:fps={FPS},setsar=1[v{index}]"
        )
    filters.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0,format=yuv420p[v]")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            *inputs,
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[v]",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "19",
            "-r",
            str(FPS),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-metadata",
            "title=",
            "-metadata",
            "artist=",
            "-metadata",
            "comment=",
            str(destination),
        ],
        timeout=300,
    )


def _probe_duration(path: Path) -> float:
    result = _run(
        [
            _binary("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    return float(result.stdout.strip())


def _encoded_contact_sheet(video: Path, destination: Path) -> None:
    """Sample the encoded MP4 itself so visual QA is not source-frame-only."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            _binary("ffmpeg"),
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-vf",
            "fps=1/3,scale=360:640,tile=3x2",
            "-frames:v",
            "1",
            str(destination),
        ],
        timeout=120,
    )


def _synthesize_voice(day: dict, destination: Path) -> dict:
    stage_dir = destination.parent
    text_file = stage_dir / "voiceover.txt"
    voiceover = day["tiktok_draft"]["voiceover"]
    text_file.write_text(voiceover + "\n", encoding="utf-8")
    destination.unlink(missing_ok=True)
    result = _run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(TTS_SCRIPT),
            "-TextFile",
            str(text_file),
            "-OutFile",
            str(destination),
            "-VoiceLanguage",
            VOICE_LANGUAGE,
            "-SpeakingRate",
            str(VOICE_RATE),
        ],
        timeout=120,
    )
    if VOICE_NAME not in result.stdout:
        raise RuntimeError(f"unexpected Thai voice selected: {result.stdout.strip()}")
    if text_file.read_text(encoding="utf-8").strip() != voiceover:
        raise RuntimeError("voiceover source text changed before synthesis")
    duration = _probe_duration(destination)
    if duration <= 0.5:
        raise RuntimeError(f"{day['candidate_id']}: narration is unexpectedly short")
    samples = _decode_pcm(destination)
    activity = _activity_bounds(samples)
    return {
        "engine": "Windows.Media.SpeechSynthesis local runtime",
        "voice": VOICE_NAME,
        "language": VOICE_LANGUAGE,
        "speaking_rate": VOICE_RATE,
        "source_text_sha256": hashlib.sha256(voiceover.encode("utf-8")).hexdigest().upper(),
        "source_text_exact_match": "PASS",
        "source_audio_path": destination.relative_to(ROOT).as_posix(),
        "source_audio_sha256": sha256_file(destination),
        "audio_duration_seconds": round(duration, 3),
        "activity_threshold_dbfs": SILENCE_THRESHOLD_DBFS,
        "first_active_sample_seconds": activity["first_active_sample_seconds"],
        "last_active_sample_seconds": activity["last_active_sample_seconds"],
        "human_listening_status": "NOT_PERFORMED",
    }


def _decode_pcm(path: Path, sample_rate: int = 48000) -> array:
    result = subprocess.run(
        [
            _binary("ffmpeg"),
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-f",
            "s16le",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "pipe:1",
        ],
        check=False,
        capture_output=True,
        timeout=180,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace")[-1200:]
        raise RuntimeError("PCM decode failed: " + detail)
    samples = array("h")
    samples.frombytes(result.stdout)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        raise RuntimeError("PCM decode returned no samples")
    return samples


def _activity_bounds(samples: array, sample_rate: int = 48000) -> dict:
    threshold = 32768.0 * 10.0 ** (SILENCE_THRESHOLD_DBFS / 20.0)
    active = [index for index, value in enumerate(samples) if abs(value) >= threshold]
    if not active:
        raise RuntimeError("narration has no samples above the activity threshold")
    return {
        "first_active_sample_seconds": round(active[0] / sample_rate, 6),
        "last_active_sample_seconds": round((active[-1] + 1) / sample_rate, 6),
    }


def _plan_timing(narration: dict, scene_count: int) -> dict:
    narration_end = float(narration["last_active_sample_seconds"])
    minimum_frames = (
        math.ceil(MIN_SCENE_DWELL_SECONDS * FPS) * (scene_count - 1)
        + math.ceil(MIN_END_CARD_DWELL_SECONDS * FPS)
    )
    desired_frames = math.ceil(
        (narration_end + TAIL_SILENCE_TARGET_SECONDS) * FPS
    )
    total_frames = max(minimum_frames, desired_frames)
    duration = total_frames / FPS
    tail = duration - narration_end
    if tail > TAIL_SILENCE_MAX_SECONDS:
        raise RuntimeError(
            f"voice-bound visual minimum leaves {tail:.3f}s after narration; "
            f"maximum is {TAIL_SILENCE_MAX_SECONDS:.3f}s"
        )
    counts = scene_frame_counts(duration, scene_count)
    end_card_start = (total_frames - counts[-1]) / FPS
    if end_card_start > narration_end:
        raise RuntimeError("AI disclosure would begin after narration ends")
    source_duration = float(narration["audio_duration_seconds"])
    trim_end = min(source_duration, narration_end + 0.18)
    if trim_end > duration:
        raise RuntimeError("voice preservation trim exceeds planned video duration")
    return {
        "status": "PASS",
        "policy": "VOICE_BOUND_NO_AMBIENT_R5",
        "fps": FPS,
        "total_frames": total_frames,
        "duration_seconds": round(duration, 6),
        "scene_frame_counts": counts,
        "scene_dwell_seconds": [round(value / FPS, 6) for value in counts],
        "minimum_scene_dwell_seconds": MIN_SCENE_DWELL_SECONDS,
        "end_card_start_seconds": round(end_card_start, 6),
        "end_card_dwell_seconds": round(counts[-1] / FPS, 6),
        "minimum_end_card_dwell_seconds": MIN_END_CARD_DWELL_SECONDS,
        "narration_last_active_seconds": round(narration_end, 6),
        "planned_tail_after_narration_seconds": round(tail, 6),
        "maximum_tail_after_narration_seconds": TAIL_SILENCE_MAX_SECONDS,
        "voice_source_trim_end_seconds": round(trim_end, 6),
    }


def _audio_packet_hash(path: Path) -> str:
    result = _run(
        [
            _binary("ffmpeg"),
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-c:a",
            "copy",
            "-f",
            "hash",
            "-hash",
            "sha256",
            "-",
        ]
    )
    match = re.search(r"SHA256=([0-9a-fA-F]{64})", result.stdout)
    if not match:
        raise RuntimeError("could not hash encoded audio packets")
    return match.group(1).upper()


def _make_voice_track(
    voice: Path, destination: Path, timing: dict, narration: dict
) -> dict:
    """Encode one exact local TTS source; no second input or generated bed exists."""
    target = float(timing["duration_seconds"])
    trim_end = float(timing["voice_source_trim_end_seconds"])
    filter_chain = (
        "aresample=48000,pan=mono|c0=c0,"
        f"atrim=end={trim_end:.6f},apad,atrim=duration={target:.6f},"
        f"loudnorm=I={AUDIO_LUFS_TARGET}:TP=-1.5:LRA=11,"
        f"atrim=duration={target:.6f}"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    _run(
        [
            _binary("ffmpeg"),
            "-y",
            "-v",
            "error",
            "-i",
            str(voice),
            "-map",
            "0:a:0",
            "-af",
            filter_chain,
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-ac",
            "1",
            "-metadata",
            "title=",
            "-metadata",
            "artist=",
            "-metadata",
            "comment=",
            str(destination),
        ],
        timeout=300,
    )
    return {
        "status": "PASS_SINGLE_LOCAL_TTS_SOURCE_NO_MIX",
        "audio_input_count": 1,
        "source_kind": "LOCAL_WINDOWS_TTS_EXACT_TEXT",
        "source_audio": narration["source_audio_path"],
        "source_audio_sha256": narration["source_audio_sha256"],
        "source_text_sha256": narration["source_text_sha256"],
        "ambient_or_music_sources": [],
        "foreign_audio_sources": [],
        "filter_chain": filter_chain,
        "voice_track": destination.relative_to(ROOT).as_posix(),
        "voice_track_sha256": sha256_file(destination),
        "voice_track_audio_packet_sha256": _audio_packet_hash(destination),
        "human_listening_status": "NOT_PERFORMED",
    }


def _digital_silence_audit(
    path: Path,
    sample_rate: int = 48000,
    expected_narration_end_seconds: float | None = None,
) -> dict:
    """Fail on long silence while requiring a short, actually silent voice tail."""
    samples = _decode_pcm(path, sample_rate)

    current = longest = nonzero = 0
    for value in samples:
        if value == 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
            nonzero += 1
    longest_seconds = longest / float(sample_rate)
    if longest_seconds > MAX_DIGITAL_SILENCE_SECONDS:
        raise RuntimeError(
            f"continuous digital silence {longest_seconds:.3f}s exceeds "
            f"{MAX_DIGITAL_SILENCE_SECONDS:.3f}s"
        )

    activity = _activity_bounds(samples, sample_rate)
    last_active = float(activity["last_active_sample_seconds"])
    decoded_duration = len(samples) / float(sample_rate)
    tail_seconds = decoded_duration - last_active
    if tail_seconds > TAIL_SILENCE_MAX_SECONDS:
        raise RuntimeError(
            f"post-narration silence {tail_seconds:.3f}s exceeds "
            f"{TAIL_SILENCE_MAX_SECONDS:.3f}s"
        )
    if tail_seconds >= MAX_DIGITAL_SILENCE_SECONDS:
        raise RuntimeError("post-narration silence reached the hard maximum")
    if expected_narration_end_seconds is not None:
        delta = abs(last_active - float(expected_narration_end_seconds))
        if delta > 0.12:
            raise RuntimeError(
                f"encoded narration end drifted {delta:.3f}s from the local TTS source"
            )

    block_size = max(1, sample_rate // 10)
    block_dbfs = []
    for start in range(0, len(samples), block_size):
        block = samples[start : start + block_size]
        if not block:
            continue
        rms = math.sqrt(sum(float(value) * float(value) for value in block) / len(block))
        dbfs = -120.0 if rms <= 0 else 20.0 * math.log10(rms / 32768.0)
        block_dbfs.append(dbfs)
    null_target = "NUL" if sys.platform.startswith("win") else "/dev/null"
    threshold = subprocess.run(
        [
            _binary("ffmpeg"),
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-af",
            f"silencedetect=noise={SILENCE_THRESHOLD_DBFS}dB:d={MAX_DIGITAL_SILENCE_SECONDS}",
            "-f",
            "null",
            null_target,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    if threshold.returncode:
        raise RuntimeError("threshold silence audit failed: " + threshold.stderr[-1200:])
    events = re.findall(r"silence_start:\s*([0-9.]+)", threshold.stderr)
    if events:
        raise RuntimeError(
            f"threshold silence >= {MAX_DIGITAL_SILENCE_SECONDS:.1f}s detected at "
            + ", ".join(events)
        )
    tail_start_block = math.ceil((last_active + 0.10) * 10)
    tail_blocks = block_dbfs[tail_start_block:]
    tail_maximum = max(tail_blocks) if tail_blocks else -120.0
    if tail_maximum >= SILENCE_THRESHOLD_DBFS:
        raise RuntimeError(
            f"post-speech tail contains non-silent audio at {tail_maximum:.2f} dBFS"
        )

    report = {
        "status": "PASS",
        "sample_rate": sample_rate,
        "decoded_samples": len(samples),
        "longest_exact_zero_run_seconds": round(longest_seconds, 6),
        "maximum_allowed_continuous_silence_seconds": MAX_DIGITAL_SILENCE_SECONDS,
        "nonzero_sample_fraction": round(nonzero / float(len(samples)), 6),
        "threshold_dbfs": SILENCE_THRESHOLD_DBFS,
        "threshold_silence_events_at_or_above_limit": 0,
        "final_audio_duration_seconds": round(decoded_duration, 6),
        "last_active_sample_seconds": round(last_active, 6),
        "post_narration_tail": {
            "status": "PASS_INTENTIONAL_SILENCE_NO_AMBIENT_OR_MUSIC",
            "duration_seconds": round(tail_seconds, 6),
            "maximum_allowed_seconds": TAIL_SILENCE_MAX_SECONDS,
            "maximum_100ms_rms_dbfs_after_100ms_release": round(tail_maximum, 2),
        },
    }
    return report


def _count_video_frames(path: Path) -> int:
    result = _run(
        [
            _binary("ffprobe"),
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        timeout=300,
    )
    try:
        return int(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError("video frame count is unreadable") from exc


def _finalize(
    silent: Path,
    voice: Path,
    final: Path,
    timing: dict,
    narration: dict,
    candidate_id: str,
) -> dict:
    """Mux one local TTS track only and run strict timing/media validators."""
    target = float(timing["duration_seconds"])
    temp = final.with_name(final.stem + f".tmp-{os.getpid()}" + final.suffix)
    temp.unlink(missing_ok=True)
    final.parent.mkdir(parents=True, exist_ok=True)
    voice_track = voice.parent / f"{candidate_id}_voice-only.m4a"
    audio_lineage = _make_voice_track(voice, voice_track, timing, narration)
    _run(
        [
            _binary("ffmpeg"),
            "-y",
            "-v",
            "error",
            "-i",
            str(silent),
            "-i",
            str(voice_track),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            "-metadata",
            "title=",
            "-metadata",
            "artist=",
            "-metadata",
            "comment=",
            str(temp),
        ],
        timeout=600,
    )
    spec = importlib.util.spec_from_file_location("week_video_finalizer", FINALIZER)
    if spec is None or spec.loader is None:
        temp.unlink(missing_ok=True)
        raise RuntimeError("strict video finalizer validator cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        report = module.validate_final(temp, target - 0.12, target + 0.12)
        final_packet_hash = _audio_packet_hash(temp)
        if final_packet_hash != audio_lineage["voice_track_audio_packet_sha256"]:
            raise RuntimeError("final audio packets differ from the single voice-only track")
        audio_lineage["final_audio_packet_sha256"] = final_packet_hash
        audio_lineage["packet_binding"] = "PASS_EXACT_PACKET_COPY"
        report["audio_lineage"] = audio_lineage
        report["continuous_silence_audit"] = _digital_silence_audit(
            temp,
            expected_narration_end_seconds=narration["last_active_sample_seconds"],
        )
        actual_frames = _count_video_frames(temp)
        if actual_frames != int(timing["total_frames"]):
            raise RuntimeError(
                f"decoded frame count {actual_frames} differs from planned "
                f"{timing['total_frames']}"
            )
        report["timing"] = {**timing, "actual_decoded_frame_count": actual_frames}
        report["file"] = final.relative_to(ROOT).as_posix()
        os.replace(temp, final)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    if report.get("sha256") != sha256_file(final):
        raise RuntimeError("strict validator SHA-256 does not match final video")
    return report


def render_all(pack_path: Path = PACK_PATH) -> dict:
    pack, days = load_candidates(pack_path)
    source_pack = json.loads(pack_path.read_text(encoding="utf-8"))
    browser = _browser()
    _binary("ffmpeg")
    _binary("ffprobe")
    if not TTS_SCRIPT.is_file() or not FINALIZER.is_file():
        raise RuntimeError("local TTS/finalizer dependency is missing")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    STAGE_ROOT.mkdir(parents=True, exist_ok=True)
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    profile = STAGE_ROOT / "browser-profile"
    profile.mkdir(parents=True, exist_ok=True)

    prepared = []
    for day in days:
        candidate_id = day["candidate_id"]
        stage_dir = STAGE_ROOT / candidate_id
        stage_dir.mkdir(parents=True, exist_ok=True)
        voice = stage_dir / f"{candidate_id}_voice.wav"
        narration = _synthesize_voice(day, voice)
        timing = _plan_timing(narration, len(scene_texts(day)))
        prepared.append((day, stage_dir, voice, narration, timing))
        print(
            f"PREFLIGHT {candidate_id} narration_end="
            f"{narration['last_active_sample_seconds']:.3f}s target="
            f"{timing['duration_seconds']:.3f}s tail="
            f"{timing['planned_tail_after_narration_seconds']:.3f}s"
        )

    results = []
    seen_hashes = set()
    for day, stage_dir, voice, narration, timing in prepared:
        candidate_id = day["candidate_id"]
        frames = _render_scene_frames(day, browser, profile)
        counts = timing["scene_frame_counts"]
        silent = stage_dir / f"{candidate_id}_silent.mp4"
        final = OUTPUT_ROOT / f"{day['date']}_{candidate_id}.mp4"
        _render_silent_video(frames, counts, silent)
        technical = _finalize(
            silent,
            voice,
            final,
            timing,
            narration,
            candidate_id,
        )
        encoded_sheet = EVIDENCE_ROOT / candidate_id / "encoded-contact-sheet.jpg"
        _encoded_contact_sheet(final, encoded_sheet)
        actual_hash = sha256_file(final)
        if actual_hash in seen_hashes:
            raise RuntimeError(f"duplicate rendered media hash: {candidate_id}")
        seen_hashes.add(actual_hash)
        if (technical.get("watermark") or {}).get("verdict") != "PASS":
            raise RuntimeError(f"{candidate_id}: automated watermark scan did not PASS")
        results.append(
            {
                "candidate_id": candidate_id,
                "date": day["date"],
                "asset": final.relative_to(ROOT).as_posix(),
                "sha256": actual_hash,
                "content_payload_sha256": stable_json_sha256(
                    _content_payload(day["tiktok_draft"])
                ),
                "scene_texts": scene_texts(day),
                "scene_frame_counts": counts,
                "scene_evidence": [path.relative_to(ROOT).as_posix() for path in frames],
                "contact_sheet": (
                    EVIDENCE_ROOT / candidate_id / "contact-sheet.png"
                ).relative_to(ROOT).as_posix(),
                "encoded_contact_sheet": encoded_sheet.relative_to(ROOT).as_posix(),
                "narration": narration,
                "technical": technical,
            }
        )
        print(f"RENDERED {candidate_id} {actual_hash} {final}")

    manifest = {
        "schema_version": 1,
        "status": "RENDERED_PENDING_VISUAL_REVIEW",
        "pack_id": TARGET_PACK_ID,
        "render_source_pack_id": source_pack.get("pack_id"),
        "copy_projection": "INDEPENDENT_COPY_QA_FINAL_2026-08-23",
        "renderer": "tools/render_week_tiktok_candidates.py",
        "visual_mode": "deterministic-local-vector-kinetic-typography",
        "narration_mode": (
            "single local Windows Thai TTS exact-source-text track; no ambient, "
            "music, second input, or foreign audio"
        ),
        "candidates": results,
    }
    RENDER_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def _prior_media_state() -> tuple[str, list[tuple[str, Path]]]:
    sys.path.insert(0, str(ROOT / "tools"))
    import media_publish_guard

    fingerprint = media_publish_guard.publication_corpus_fingerprint(ROOT)
    if not fingerprint:
        raise RuntimeError("publication comparison corpus is missing or unreadable")
    prior = []
    for content_id, path in media_publish_guard._prior_media(ROOT):
        if path.is_file():
            prior.append((content_id, path))
    return fingerprint, prior


def write_receipts(reviewer: str) -> list[Path]:
    if not reviewer.strip():
        raise ValueError("a non-empty visual reviewer is required")
    if not RENDER_MANIFEST.is_file():
        raise ValueError("render manifest is missing; render before visual approval")
    manifest = json.loads(RENDER_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("status") not in (
        "RENDERED_PENDING_VISUAL_REVIEW",
        "VISUAL_REVIEWED_RECEIPTS_WRITTEN",
    ):
        raise ValueError("render manifest is not awaiting visual review")
    if manifest.get("pack_id") != TARGET_PACK_ID:
        raise ValueError("render manifest is not bound to the r5 target pack")
    _, days = load_candidates(PACK_PATH)
    by_id = {day["candidate_id"]: day for day in days}
    fingerprint, prior = _prior_media_state()
    prior_hashes = {
        sha256_file(path): (content_id or path.name)
        for content_id, path in prior
        if path.is_file()
    }
    reviewed_at = datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).isoformat()
    receipts = []
    for item in manifest.get("candidates") or []:
        candidate_id = item["candidate_id"]
        day = by_id.get(candidate_id)
        if day is None:
            raise ValueError(f"render manifest contains unknown candidate {candidate_id}")
        asset = (ROOT / item["asset"]).resolve()
        if not asset.is_file() or sha256_file(asset) != item["sha256"]:
            raise ValueError(f"{candidate_id}: rendered asset changed before review receipt")
        current_payload = stable_json_sha256(_content_payload(day["tiktok_draft"]))
        if current_payload != item["content_payload_sha256"]:
            raise ValueError(f"{candidate_id}: source copy changed after rendering")
        if item["sha256"] in prior_hashes:
            raise ValueError(
                f"{candidate_id}: exact duplicate of prior media {prior_hashes[item['sha256']]}"
            )
        encoded_sheet = item.get("encoded_contact_sheet") or (
            EVIDENCE_ROOT / candidate_id / "encoded-contact-sheet.jpg"
        ).relative_to(ROOT).as_posix()
        item["encoded_contact_sheet"] = encoded_sheet
        evidence = [item["contact_sheet"], encoded_sheet, *item["scene_evidence"]]
        for raw in evidence:
            path = (ROOT / raw).resolve()
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError(f"{candidate_id}: visual evidence missing: {raw}")
        automated = item["technical"]["watermark"]
        if automated.get("verdict") != "PASS":
            raise ValueError(f"{candidate_id}: recorded watermark scan is not PASS")
        receipt = {
            "schema_version": 1,
            "asset": item["asset"],
            "sha256": item["sha256"],
            "media_type": "video",
            "reviewed_at": reviewed_at,
            "media_origin": day["tiktok_draft"]["candidate_asset"]["media_origin"],
            "source_binding": {
                "weekly_pack": PACK_PATH.relative_to(ROOT).as_posix(),
                "weekly_pack_id": TARGET_PACK_ID,
                "render_source_pack_id": manifest.get("render_source_pack_id"),
                "candidate_id": candidate_id,
                "content_payload_sha256": item["content_payload_sha256"],
                "exact_visible_copy": item["scene_texts"],
                "scene_frame_counts": item["scene_frame_counts"],
                "scene_evidence_sha256": {
                    raw: sha256_file((ROOT / raw).resolve()) for raw in evidence
                },
                "visual_mode": "deterministic local HTML/SVG plus centered kinetic zoom",
                "narration": item["narration"],
                "audio_lineage": item["technical"]["audio_lineage"],
            },
            "technical_qa": item["technical"],
            "manual_check_resolution": {
                "semantic_frame_review": "PASS_FULL_RESOLUTION_SOURCE_AND_ENCODED_SAMPLES",
                "landing_page_qa": "NOT_APPLICABLE_NO_OUTBOUND_URL_OR_LINK_CTA",
                "audio_listening": "NOT_PERFORMED_RECORDED_AS_LIMITATION",
                "audio_mix": "PASS_SINGLE_LOCAL_TTS_SOURCE_NO_AMBIENT_OR_MUSIC",
            },
            "novelty_review": {
                "status": "PASS",
                "content_id": candidate_id,
                "reviewer": "Codex deterministic hash and source-bound creative comparison",
                "corpus_fingerprint": fingerprint,
                "compared_assets": len(prior),
                "scope": (
                    "Current manifest and published-media corpus; exact SHA-256 is unique; "
                    "candidate is an r5 timing/copy revision using an original local "
                    "vector composition and exact projected weekly-pack copy"
                ),
            },
            "watermark": {
                "visual_review": {
                    "status": "PASS",
                    "reviewer": reviewer.strip(),
                    "scope": (
                        "All full-resolution scene frames and contact sheet reviewed; no provider/platform "
                        "watermark, page logo, account handle, URL, tracking mark, affiliate CTA, or hidden footer identity"
                    ),
                    "evidence": evidence,
                },
                "automated_scan": {
                    "status": "PASS",
                    "detector": "tiktok-pipeline/src/qa_watermark.py",
                    "fps": 3.0,
                    "frames": automated.get("frames"),
                    "track_frames": automated.get("track_frames"),
                    "track_frac": automated.get("track_frac"),
                },
            },
        }
        destination = RECEIPT_ROOT / f"{candidate_id}-tiktok-video-r5.json"
        destination.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        receipts.append(destination)
        print(f"RECEIPT {candidate_id} {destination}")
    manifest["status"] = "VISUAL_REVIEWED_RECEIPTS_WRITTEN"
    manifest["reviewed_at"] = reviewed_at
    manifest["visual_reviewer"] = reviewer.strip()
    manifest["receipts"] = [path.relative_to(ROOT).as_posix() for path in receipts]
    RENDER_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return receipts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-receipts",
        action="store_true",
        help="write PASS receipts after an actual full-frame visual review",
    )
    parser.add_argument(
        "--visual-reviewer",
        default="",
        help="reviewer description required with --write-receipts",
    )
    args = parser.parse_args()
    if args.write_receipts:
        write_receipts(args.visual_reviewer)
    else:
        render_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
