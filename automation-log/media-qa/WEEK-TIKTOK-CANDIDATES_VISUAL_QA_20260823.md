# Weekly TikTok candidate media QA — 2026-08-23

Scope: seven local-only candidates in `WEEK-CONTENT-PACK_20260824-30.json`.
These assets remain `DRAFT_ONLY`; this review does not bind them to calendar
placements and does not authorize publication.

## Result

- Visual review: PASS for all full-resolution source frames and encoded MP4
  sample-frame contact sheets.
- Fresh media publication guard: PASS 7/7, zero findings.
- Watermark detector: PASS 7/7, zero tracked watermark frames.
- Exact visible copy: hook, on-screen phrases, and
  `ข้อมูลเพื่อการศึกษา · ผลิตด้วย AI` are source-bound to the weekly pack.
- Outward identity: no page logo, page name, account handle, URL, tracking mark,
  affiliate CTA, provider mark, or platform mark is visible.
- Video: H.264, yuv420p, 1080x1920, 24 fps, faststart and full decode PASS.
- Audio: local Microsoft Pattara (`th-TH`) from the exact weekly-pack voiceover,
  AAC mono 48 kHz; technical decode and loudness PASS.

| Candidate | Duration | Integrated loudness | True peak | SHA-256 |
| --- | ---: | ---: | ---: | --- |
| wk36-sf01 | 18.00 s | -16.24 LUFS | -1.37 dBFS | `061E47AE8C9F535E79656C8DA2254DC13AD29E28BB35A5CFF23FB6D92ABE7A91` |
| wk36-sf02 | 17.00 s | -16.44 LUFS | -1.46 dBFS | `DC3B34D752AADEBB0D554A18043C426EF3C03DFE66373D665A310CB001810418` |
| qt-12 | 18.00 s | -17.12 LUFS | -1.29 dBFS | `BCB2F58939C4CC8721EA19B32EC875993DF5E549719D172305FD48039F46CD90` |
| wk36-sf03 | 16.00 s | -17.58 LUFS | -1.42 dBFS | `15BC9DA3DD793801A5152178E9AAC27B01A712C0AD18C9C31F969CC7FA682BB4` |
| wk36-sf04 | 18.00 s | -16.29 LUFS | -1.42 dBFS | `76B04F882C147170EE59B001FE4CFB8E562E29C4C21A1483ACAE6235A9EE1812` |
| qt-13 | 18.00 s | -16.43 LUFS | -1.45 dBFS | `C1A4F054983A62B2BEFC7C63BE8C5F9878AD70682CAB924D7B1B1C3EC6178830` |
| wk36-sf05 | 18.00 s | -16.84 LUFS | -1.48 dBFS | `042D10382430B41EE083904FEE9E934FE43C8D323B28EB2F3BF36B77799C9FA4` |

## Evidence and limitation

Each candidate receipt under `automation-log/media-qa/` is bound to the exact
asset hash, the immutable creative payload, all source scene frames, and a
contact sheet sampled from the encoded MP4. The Windows Thai voice was not
human-listened during this run; receipts and the weekly pack therefore record
`HUMAN_LISTENING_NOT_RUN` instead of claiming an unperformed listening review.
This limitation does not negate visual, decode, loudness, source-text, or
watermark QA, but it remains relevant before any future publication approval.
