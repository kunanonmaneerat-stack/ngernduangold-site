# B3 TikTok media evidence — 2026-08-16

## Verdict

**BLOCKED 6/6. No publication receipt was created. No upload, scheduling, publication, or network action was performed.**

The six canonical files are technically decodable and pass the fresh provider-watermark scan, but they do not satisfy the exact planned TikTok `no-link / no-affiliate` placement. A clean re-render is required. `b3-07` is excluded from this review and remains excluded from reuse.

| Piece | Technical / audio | Fresh 3 fps mark scan | Source voice binding | Full-frame semantic result | Receipt |
|---|---|---|---|---|---|
| b3-01 | PASS | PASS, 0/74 | PASS | **BLOCKED** — link-in-bio CTA, affiliate/license disclosure, leftover base hook | not created |
| b3-02 | PASS | PASS, 0/61 | PASS | **BLOCKED** — link-in-bio CTA, affiliate/license disclosure, leftover base hook | not created |
| b3-03 | PASS | PASS, 0/63 | PASS | **BLOCKED** — link-in-bio CTA, affiliate/license disclosure, leftover base hook | not created |
| b3-04 | PASS | PASS, 0/71 | PASS | **BLOCKED** — visible `ngernduangold.com/links`, prior-reel claim, link/affiliate/license copy | not created |
| b3-05 | PASS | PASS, 0/66 | PASS | **BLOCKED** — dominant hook is a different topic, plus link/affiliate/license copy | not created |
| b3-06 | PASS | PASS, 0/65 | PASS | **BLOCKED** — dominant hook is a different topic, plus link/affiliate/license copy | not created |

## What was checked

- SHA-256 was calculated from each canonical `reels/...mp4`; every canonical file is byte-identical to its named `_vidout` staging render.
- `ffprobe` confirms H.264, 1080×1920, 24 fps, `yuv420p`, AAC mono, and durations from 20.333 to 24.500 seconds.
- Full video decode and audio-only decode both pass for all six files. Each audio stream is non-silent; decoded PCM hashes are unique across the six pieces.
- The source TTS text in `C:/tmp/b3-01_win_tts.ps1` and `C:/tmp/build_batch3.py` matches the authoritative voiceover entries in `automation-log/BATCH3-PRODUCTION-KIT.md`; the canonical files are byte-identical to those render outputs.
- Each clip was visually reviewed at eight full-frame timepoints: 0.5, 3, 6, 9, 12, 15, 18 seconds, and 0.5 seconds before the end. The contact sheets are summaries; the eight 1080×1920 PNGs remain the primary evidence.
- The fresh `tiktok-pipeline/src/qa_watermark.py --fps 3` scan found zero Veo/provider-mark track frames in every file. `@ngernduangold` is intentional first-party branding, not a third-party watermark.

Audio was verified through decode, level, decoded-PCM fingerprint, render-source identity, and exact source-script mapping. No local Thai speech-to-text recognizer was available, so no independent ASR transcript is claimed; this does not change the BLOCKED verdict because the visible semantic/placement defects are conclusive.

## Blocking visual findings

### b3-01, b3-02, b3-03

The intended topic-specific overlays are present, but the old base-video headline `ต้องใช้เงินด่วน แต่ไม่อยากขายรถ?` remains visually dominant. The base CTA says `เช็กลิสต์เต็ม + ตัวช่วยเทียบ — ลิงก์ในไบโอ`. The burned footer also states `ผู้ให้บริการมีใบอนุญาต` and `มีลิงก์พันธมิตร`. Those claims do not match the planned no-link/no-affiliate TikTok placement, and the license claim has no per-provider evidence.

### b3-04

The clip visibly burns `ngernduangold.com/links` and `ลิงก์ในไบโอ`. Copy from the prior reel (`จำนำเล่มแล้ว รถยังขับได้ไหม`) remains underneath the new 15-year-vehicle topic, introducing a different claim. The same affiliate and provider-license footer is present.

### b3-05, b3-06

Both clips retain the large underlying headline `ไม่เคยเป็นหนี้ = สมัครบัตรไม่ผ่าน`, which is materially different from the intended credit-limit and first-card-selection topics. The link-in-bio CTA plus affiliate/provider-license footer also violates the target contract.

## Clean re-render brief

1. Start from clean, uncaptioned source footage. Do not composite on a previously published reel or a file that already contains a hook, CTA, URL, disclosure, or handle.
2. Keep one intentional first-party brand layer only: `@ngernduangold`. Do not include any provider/platform logo or watermark.
3. Use only the exact topic hook, four overlays, CTA, and voiceover from the matching section of `BATCH3-PRODUCTION-KIT.md`.
4. For this TikTok placement, burn no URL, no `ลิงก์ในไบโอ`, no affiliate claim, and no provider-license claim. Use only `ข้อมูลเพื่อการศึกษา ไม่ใช่คำแนะนำทางการเงิน · ผลิตด้วย AI` unless the placement contract changes with separately verified evidence.
5. Preserve 1080×1920 H.264 at 24 fps, AAC mono, and a 20–25 second duration. Prefer a 48 kHz delivery audio track while retaining the exact approved narration.
6. Before any receipt: rerun full video/audio decode, non-silence/loudness checks, decoded-audio and full-file hashes, eight-timepoint full-frame review, fresh 3 fps watermark scan, source-script semantic match, and novelty comparison against the current publication corpus.
7. Create a hash-bound `automation-log/media-qa/...` receipt only when every check passes. Any mismatch must remain BLOCKED.

## Evidence index

- Per-piece machine-readable records: `automation-log/video-production/b3-01_qa.json` through `b3-06_qa.json`.
- Full-frame evidence: `_vidout/media-evidence-b3/b3-01/` through `b3-06/`.
- Focused fail-closed contract: `tools/test_b3_tiktok_media_evidence.py`.
- There are intentionally no `automation-log/media-qa/b3-*-video.json` receipts.
