# Google Flow decision — 2026-08-23

## Decision

Google Flow is available to the page as an ideation/storyboard tool, but no
Flow-generated pixel or audio may enter a final publishable asset while the
project requires **no watermark of any kind**.

## Evidence

- Authenticated Flow UI observed Google AI Pro, 1,050 credits, and visible
  watermarking set to Off. This is a point-in-time account observation, not an
  entitlement guarantee or a no-watermark certificate.
- Google states that Flow outputs include invisible SynthID even when a visible
  watermark is not shown:
  - https://support.google.com/flow/answer/16353333?hl=en
  - https://support.google.com/flow/answer/16935308?hl=en
- The current weekly pack contains 11 final candidate assets with explicit
  local-origin attestations: `contains_flow_pixels=false`,
  `contains_flow_audio=false`, and `synthid_expected=false`.
- `tools/generative_media_origin_gate.py` rejects missing/unknown provenance,
  any Flow pixels/audio, and any asset where SynthID is present, expected, or
  unknown.

## Allowed use

- Written scene concepts, shot lists, pacing experiments, and storyboard ideas.
- Temporary Flow outputs may be used only as non-publishable internal reference,
  never copied, cropped, traced, composited, or remixed into final media.
- Do not put personal, confidential, account, or customer data into prompts.

## Final-media route

Final assets must be rendered from the approved local HTML/SVG/CSS, FFmpeg,
browser-render, and local Windows TTS pipeline, with hash-bound receipts,
visible-watermark QA, explicit origin attestation, and the normal publication
gates. Unknown origin is `BLOCKED`.

## Actions not taken

No Flow generation was started, no credits were consumed, and no external media
was published, scheduled, or deployed in this audit.
