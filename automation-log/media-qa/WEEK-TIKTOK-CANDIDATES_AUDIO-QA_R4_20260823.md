# Weekly TikTok candidates r4 — audio/media QA closure

- Finalized: `2026-08-23T18:31:48+07:00`
- Pack: `week-content-20260824-30-r4`
- Pack SHA-256: `54D4AE68D9332CFBB6FF827A725C58E7C9A15F21F452E79D5BAF6CD16C55C7B1`
- Binding: all seven r4 files and r4 receipts were completed before the weekly pack was changed from the fail-closed rework state to r4.
- Status: technical media QA PASS; `HUMAN_LISTENING_NOT_RUN`; candidates remain `DRAFT_ONLY` and are not bound to calendar placements.

## Corrective change

All seven videos retain the exact Thai narration and exact on-screen copy, with an original deterministic local ambient bed added across the full clip. The bed is generated from three mathematical sine components per candidate; it does not use an external or copyrighted media asset. The mix uses a 70 Hz high-pass, 850 Hz low-pass, 400 ms edge fades, and narration-controlled sidechain ducking (threshold `0.02`, ratio `12:1`, attack `20 ms`, release `500 ms`, post-duck bed weight `0.42`). Candidate-specific roots are recorded in each receipt.

## Per-file evidence

| Candidate | Final asset | SHA-256 | LUFS-I | True peak dBFS | Longest exact-zero run | >=1.5 s silence events at -50 dBFS | Audited post-narration bed tail |
|---|---|---|---:|---:|---:|---:|---:|
| wk36-sf01 | `reels/week-20260824-30-r4/2026-08-24_wk36-sf01.mp4` | `B017B982657B11ADB1B517B47871B134685D9A12B7EB16FED0F7DD03E1CF7FA9` | -15.85 | -1.43 | 0.000729 s | 0 | 6.8 s; min 100 ms RMS -43.12 dBFS |
| wk36-sf02 | `reels/week-20260824-30-r4/2026-08-25_wk36-sf02.mp4` | `2AE36C105532D0269ECBFD759184F70F040D95DD2D453C79F590DC72D5183303` | -16.19 | -1.36 | 0.001313 s | 0 | 8.9 s; min 100 ms RMS -40.32 dBFS |
| qt-12 | `reels/week-20260824-30-r4/2026-08-26_qt-12.mp4` | `D1146EEBB713BBCE6EA55165F5F9134A403017C10388EED5F1405722D3C4A8AE` | -16.47 | -1.33 | 0.001500 s | 0 | 8.1 s; min 100 ms RMS -43.74 dBFS |
| wk36-sf03 | `reels/week-20260824-30-r4/2026-08-27_wk36-sf03.mp4` | `DCB05243DF877CF027B26E351727564609BF54496D8445AA0FF84BF1069E1B8E` | -16.76 | -1.39 | 0.001042 s | 0 | 7.8 s; min 100 ms RMS -40.16 dBFS |
| wk36-sf04 | `reels/week-20260824-30-r4/2026-08-28_wk36-sf04.mp4` | `D43FE55B112F9E64750353E0D8ABF7B705810B016EB37D7D577413CC3C21A681` | -15.91 | -1.39 | 0.000479 s | 0 | 10.1 s; min 100 ms RMS -40.85 dBFS |
| qt-13 | `reels/week-20260824-30-r4/2026-08-29_qt-13.mp4` | `85171F43E9F5D56390105A711D6AEF118FFF6C761F803AD86700E55D67094415` | -15.95 | -1.48 | 0.000917 s | 0 | 8.6 s; min 100 ms RMS -40.42 dBFS |
| wk36-sf05 | `reels/week-20260824-30-r4/2026-08-30_wk36-sf05.mp4` | `B29CC144348E4DEDEC4597DAA94D52B9C9F47C59F12C9FAFFDE571553623D68A` | -16.35 | -1.34 | 0.000604 s | 0 | 9.2 s; min 100 ms RMS -42.72 dBFS |

## Closure checks

- Full decode, H.264/yuv420p/1080x1920/24 fps, AAC mono 48 kHz, fast-start, and media hash checks: PASS 7/7.
- Loudness: PASS 7/7 against -18 to -14 LUFS integrated and true peak no higher than -1 dBFS.
- Continuous digital silence: PASS 7/7; longest exact-zero run is 0.000479–0.001500 seconds and the -50 dBFS / 1.5 second detector found zero events in every file.
- Post-narration coverage: PASS 7/7; the original 49.0%–66.8% silent-tail regression is replaced with 6.8–10.1 seconds of measured ambient-bed coverage.
- Watermark detector: PASS 7/7, with 0 tracked watermark frames in every 54-frame scan.
- Full-resolution source frames and encoded MP4 contact sheets: visually reviewed PASS; no provider/platform watermark, page logo, handle, URL, tracking mark, or affiliate CTA observed.
- Media publication guard: PASS 7/7 with zero findings after the atomic r4 pack update.
- Renderer unit tests: PASS 11/11.

## Remaining limitation and release fence

No human listening review was performed. The receipts therefore deliberately retain `HUMAN_LISTENING_NOT_RUN`; technical sidechain measurements are not represented as a subjective listening approval. The weekly pack remains `DRAFT_ONLY`, publication authority remains false, exact per-piece owner approval is missing, and the r4 candidates remain unbound to occupied `PLANNED_BLOCKED` calendar placements. No posting, scheduling, reply, like, calendar, policy, authority, ledger, commit, push, deploy, or external-system action was performed.
