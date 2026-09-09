# b4-p01 manual QA — 2026-08-16

## Verdict

**PASS for local review. Not deployed, scheduled, uploaded, or published.**

Automated media evidence is recorded separately in `b4-p01_qa.json`. This file closes the two manual checks named there.

## Semantic frame review — PASS

- Reviewed the contact sheet plus full-size hook and end-card frames.
- All five scenes stay on one topic: choosing a first credit card from real spending, fees, conditions, and ability to repay in full.
- Thai text and tone match the narration; no unrelated banner, provider logo, account number, approval claim, rate, fee amount, or fabricated testimonial appears.
- Hook is visible immediately, final CTA points to the matching checklist article, and the educational/AI/affiliate disclosure is visible in the final scene.
- Text remains inside the reviewed safe area and the final scene leaves platform-control clearance at the bottom.

## Landing-page QA — PASS

- Tested the generated page locally in Chrome with tracking disabled (`?notrack=1`).
- One H1 appears before any offer. The answer states the Bank of Thailand ceiling as no more than 3 times monthly income for the stated income band, explains 90,000 baht as a ceiling rather than a guaranteed approval, and does not use the removed 1.5–2 times / 45,000–60,000 claim.
- The video loaded without an error at 1080×1920 for 21.5 seconds; the Thai captions track and topic-specific poster loaded. Intrinsic dimensions plus a 9:16 aspect ratio prevent layout shift.
- The landing page contains zero direct `atth.me` or `rel=sponsored` anchors. Its measured CTA is internal (`salary30000-compare`, `after-options`, `b4-p01`) so the expired/mismatched product redirect is not presented as a current generic Krungsri offer.
- `answer_seen`, `video_start`, and `internal_cta_click` now retain `b4-p01`; the internal link passes a neutral `content_id` parameter so a downstream affiliate click can retain content attribution without resetting the analytics source via an internal UTM.
- The shared outbound interstitial was exercised on a local comparison page without navigating externally. It opens as an accessible dialog, focuses the continue action, closes with Escape, restores the original link focus, and adds `rel=sponsored` only while a real partner destination is present.
- Official Bank of Thailand knowledge and product-comparison sources are visible. Canonical, share URLs, and Breadcrumb JSON-LD use the same extensionless URL.
- Article, FAQ, and Breadcrumb JSON-LD parse successfully in the build gate.

## Reproducible identifiers

- Canonical media: `reels/2026-08-16_b4-p01.mp4`
- SHA-256: `D0A07323742B42FCCF147A067A4654A1438418C7404CD8E4C56F3F76F88A8DAC`
- Thai captions: `reels/2026-08-16_b4-p01.th.vtt`
- Poster: `reels/2026-08-16_b4-p01-poster.png`
- Landing page: `/credit-card-salary-30000-2026`

Google Flow/Veo footage was not generated and no prepared prompt was sent to Google. The current local video is complete without that optional enhancement.
