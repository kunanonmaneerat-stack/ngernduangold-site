# Weekly TikTok and quote candidates r5 — corrective QA closure

- Finalized: `2026-08-23T19:09:28+07:00`
- Evidence resealed after provenance enforcement: `2026-08-23T21:20:00+07:00`
- Pack: `week-content-20260824-30-r5`
- Pack SHA-256: `0ACD60E0D44F689841C8AAF2C7AF1ADAADA6A5E03CCCAF87C3B626BE84A21A28`
- Binding: all seven r5 videos, four r5 quote images, and their eleven r5 receipts were complete before the weekly pack was changed atomically from the fail-closed rework state to r5.
- Status: technical media QA PASS; `HUMAN_LISTENING_NOT_RUN`; the pack remains `DRAFT_ONLY` and is not bound to calendar placements or publication authority.
- Evidence preservation: no r4 asset or r4 receipt was overwritten; r4 remains superseded audit evidence.

## Corrective change

The stationary r4 ambient bed was removed entirely. Every r5 video contains one audio input only: exact Thai narration synthesized by the local Microsoft Pattara `th-TH` voice. The final MP4 audio packet hash is an exact match to the staged voice-only AAC packet hash in each receipt. There are no ambient, music, or foreign-audio inputs. Video duration is bound to narration with an audited post-narration tail no longer than 1.0 second. The disclosure card begins before narration ends and remains visible for at least 2.0 seconds.

Final copy corrections were applied before rendering: qt-12 uses the complete financial-picture framing and contains neither `หนี้` nor `ภาระ`; qt-13 uses `แค่ดูแลมันทุกเดือน`; wk36-sf01 ends with `เลือกหนึ่งช่องมาดูให้ชัดก่อน`; wk36-sf04 uses `ลองจดรายการรายจ่ายไว้`; and wk36-sf05 uses `เก็บ 1 พฤติกรรม ลด 1 รายจ่าย และทดลองเปลี่ยน 1 วิธีใช้เงิน`, with Thai number words in narration.

## Video evidence

| Candidate | Final asset | SHA-256 | Duration / frames | Tail after speech | Longest exact-zero run | >=1.5 s events at -50 dBFS | LUFS-I / true peak | End disclosure start / dwell |
|---|---|---|---:|---:|---:|---:|---:|---:|
| wk36-sf01 | `reels/week-20260824-30-r5/2026-08-24_wk36-sf01.mp4` | `ADB59197D732993C69435D15456B9C227F8A8072EF2133E9933D8DE376D88CEC` | 12.125 s / 291 | 0.710937 s | 0.687896 s | 0 | -16.18 / -1.34 dBFS | 9.708333 / 2.416667 s |
| wk36-sf02 | `reels/week-20260824-30-r5/2026-08-25_wk36-sf02.mp4` | `BF204A23D83820DABF941D62C4D4F93EA79753A42AB24A150D800BAC9790A61B` | 8.125 s / 195 | 0.718896 s | 0.693146 s | 0 | -16.77 / -1.48 dBFS | 6.125 / 2.000 s |
| qt-12 | `reels/week-20260824-30-r5/2026-08-26_qt-12.mp4` | `5302D53836218A0F1664F6058B58B73368382E2AF041F00EE98C38D1556DA1FA` | 12.417 s / 298 | 0.695646 s | 0.670937 s | 0 | -17.10 / -1.39 dBFS | 9.958333 / 2.458333 s |
| wk36-sf03 | `reels/week-20260824-30-r5/2026-08-27_wk36-sf03.mp4` | `E8B87B3D1A97A0517068F90FD12237439F97E31EC08AA12E279E52312F3723D0` | 8.250 s / 198 | 0.743250 s | 0.694167 s | 0 | -17.79 / -1.45 dBFS | 5.833333 / 2.416667 s |
| wk36-sf04 | `reels/week-20260824-30-r5/2026-08-28_wk36-sf04.mp4` | `CEA93EA3E6E7944FE7E4BC9D1E5104121DE250329A5AB33C4FFBFB8C06AEF11C` | 8.000 s / 192 | 0.883792 s | 0.751833 s | 0 | -16.66 / -1.38 dBFS | 6.000 / 2.000 s |
| qt-13 | `reels/week-20260824-30-r5/2026-08-29_qt-13.mp4` | `01299233BA32AAA1400076C5575D9DEEEE649D287C14EB0589B64972CBDBC12C` | 9.875 s / 237 | 0.736958 s | 0.704521 s | 0 | -16.54 / -1.45 dBFS | 7.500 / 2.375 s |
| wk36-sf05 | `reels/week-20260824-30-r5/2026-08-30_wk36-sf05.mp4` | `CB733BDA1E5322ED90DE9DC48CF9BDD253417D5167FC547E05402F398940D1B1` | 10.333 s / 248 | 0.726896 s | 0.692896 s | 0 | -16.38 / -1.25 dBFS | 7.875 / 2.458333 s |

## Quote-image evidence

| Candidate/channel | Final asset | SHA-256 | Receipt |
|---|---|---|---|
| qt-12 Facebook/Instagram 4:5 | `media/quotes/week-20260824-30-r5/qt-12_fb-ig_4x5.jpg` | `01A3FA967DAEF32206C0E11EBC3D6D0A681977F6E13106CCE60A70AB0744E6B0` | `automation-log/media-qa/qt-12-fb-ig-image-r5.json` |
| qt-12 Pinterest 2:3 | `media/quotes/week-20260824-30-r5/qt-12_pinterest_2x3.jpg` | `337F6A1F0D708DD119F36854B22094888EFB7566555BE520CC85164320F22B49` | `automation-log/media-qa/qt-12-pinterest-image-r5.json` |
| qt-13 Facebook/Instagram 4:5 | `media/quotes/week-20260824-30-r5/qt-13_fb-ig_4x5.jpg` | `F0E64962659977273CC8398638348091A7BF1208CE1A578DAAD92DADB63929AE` | `automation-log/media-qa/qt-13-fb-ig-image-r5.json` |
| qt-13 Pinterest 2:3 | `media/quotes/week-20260824-30-r5/qt-13_pinterest_2x3.jpg` | `9B773CAEF625CA022CEED1B5DDFFABA8C8DD59E9E937DAAC82E08832671BDA1A` | `automation-log/media-qa/qt-13-pinterest-image-r5.json` |

## Closure checks

- Full decode, H.264/yuv420p/1080x1920/24 fps, AAC mono 48 kHz, exact frame count, fast-start, and asset/receipt hash binding: PASS 7/7.
- Voice-only lineage: PASS 7/7; one local TTS input, empty ambient/music and foreign-audio source lists, and exact final/staged audio packet binding.
- Loudness: PASS 7/7 against -18 to -14 LUFS integrated and true peak no higher than -1 dBFS.
- Silence: PASS 7/7; the -50 dBFS / 1.5 second detector found zero events, and all measured speech tails are 0.695646–0.883792 seconds.
- Timing: PASS 7/7; exact duration/frame count, each ordinary scene at least 1.5 seconds, and each end disclosure visible 2.0–2.458333 seconds while overlapping the last narration segment.
- Watermark scan and full-resolution visual review: PASS 11/11; no provider/platform watermark, page logo, handle, URL, tracking mark, affiliate CTA, or outward page identity observed.
- Final-origin enforcement: PASS 11/11; every receipt matches the frozen pack origin attestation, contains no Flow pixels/audio, and does not expect SynthID. Unknown origin remains blocked.
- Media publication guard after atomic pack update: PASS 11/11 with zero findings.
- Renderer, quote-card, and independent r5 guard tests after atomic pack update: PASS 16/16.

## Remaining limitation and release fence

No human listening review was performed, so no claim is made about subjective voice naturalness. Each receipt and the pack retain `HUMAN_LISTENING_NOT_RUN`. All candidates remain local-only `DRAFT_ONLY`; publication authority is false, exact per-piece owner approval is missing, and calendar/dedup blockers remain. No posting, scheduling, reply, like, calendar, policy, authority, ledger, commit, push, deploy, or external-system action was performed.
