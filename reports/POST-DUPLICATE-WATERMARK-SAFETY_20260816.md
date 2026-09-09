# Post, duplicate, and watermark safety — 2026-08-16

## Release decision

**PUBLISH BLOCKED.** Content creation and local QA may continue, but no automated
publisher may open a composer, upload, schedule, deploy, or push until every
publication gate is explicitly authorized. The current future video schedule is
empty, privacy review is blocked, official-source reviews are pending, and channel
publication authorization is false.

This is intentional fail-closed behaviour, not a content-production pause.

## What was audited

- Five upcoming text libraries: 60 content IDs / 104 channel-specific bodies.
  IDs and dates are unique. No same-channel pair exceeded the near-duplicate gate.
- Future text versus every historical ledger body that retained a full normalized
  value: no collision. The highest observed similarity was 0.2652, far below 0.90.
- Active canonical video set: 24/24 passed a fresh 3 fps Veo-mark scan and a
  five-timepoint visual review. No visible third-party/provider/platform mark was
  found.
- Active publish-like still set after quarantine: 29 images. No visible external
  provider mark was found.
- B4 pilot video and poster: exact SHA-bound QA receipts pass. The video and decoded
  audio do not exactly duplicate the canonical corpus; the creative is documented as
  a sequel angle rather than a repost.

## Problems found and contained

- `qt-02.png` and `qt-02_post.jpg` contained a visible Gemini sparkle. They were
  moved to `media/quarantine/watermarked/stills/` and cannot pass the publication
  root guard. Historical ledger evidence shows they were posted to Facebook and
  Instagram on 2026-07-25; that historical exposure cannot be undone by a local
  repository change.
- Seven raw Veo clips, seven web versions, and seven generated-site copies contained
  provider marks. All 21 copies were moved under
  `media/quarantine/watermarked/`; active source and site clip directories no longer
  contain them.
- The site was rebuilt. Generated HTML now contains zero legacy `/clips/*.mp4`
  embeds, so quarantining the media does not leave broken legacy video references.
- `2026-07-19_eb03` is a confirmed duplicate of `2026-07-17_eb02` (near-identical
  captions, identical decoded audio, 99.36% sampled visual similarity). The manifest
  now marks it `BLOCKED_DUPLICATE` and records its source identity.
- Historical TikTok `titleloan` was used twice 25 days apart. Permanent exact
  content identity now blocks this class of repost regardless of age.

## Enforced controls

1. Exact normalized text is blocked forever on the same channel. Near-text review
   remains a 30-day gate. Cross-channel adaptation remains allowed.
2. Exact canonical clip identity is blocked forever on the same channel, including
   B3/B4 dated filenames. Check and append are protected by one ledger-adjacent lock.
3. Manifest evidence accepts only positive, platform-scoped canonical claims.
   `not posted`, `failed: not published`, `unscheduled`, an extra note key, a date
   mentioned only in prose, or the wrong/missing content ID cannot produce a green
   status.
4. Images/videos require a QA receipt bound to the exact path and SHA-256. The
   receipt must include a current corpus novelty review and full-frame visual review;
   video also requires a fresh automated scan.
5. Live YouTube upload requires explicit date and actor, current/future Bangkok date,
   `Scheduled`, `publication_eligibility=ALLOWED|READY`, an exact schedule/content
   ID/asset match, owner approval, role/policy/privacy/source gates, exact QA receipt,
   and a final byte hash immediately before upload.
6. Scheduled publisher/deploy/git mutation prompts are blocked or tombstoned. The
   automation scanner fails on executable uploader, browser-publish, deploy, or
   remote-git instructions while allowing explicit prohibitions.

## Qualification on “no watermark of any kind”

The defensible result is: **no visible external/provider/platform watermark was
found in the active publish set that was reviewed.** Intentional first-party brand
text such as `@ngernduangold` or the “เงินเดือนสมองทอง” masthead remains part of the
creative design. Google-origin media may also carry invisible SynthID, which a visual
scan cannot disprove. A literal zero-watermark rule including invisible provenance
would require excluding all Google-AI-derived media and using only original,
locally-rendered, or licensed non-AI assets.

## Known evidence limits

- The historical ledger has 176 rows but no historical `content_id` field coverage.
  Thirty-three old text rows retained only prefixes, not full normalized bodies, so
  a 100% semantic reconstruction of old captions is impossible.
- Automated watermark detection recognizes the known Veo sparkle pattern; it is not
  a universal logo, OCR, acoustic-logo, or invisible-provenance detector. Full-frame
  human/vision review and the exact hash receipt therefore remain mandatory.
- Writers that bypass the canonical ledger or publication guard are unauthorized and
  are caught by the automation-policy scan; they must not be re-enabled as alternate
  publisher routes.

## Final verification snapshot

- Daily media gate: PASS; 23 manifest references, 24/24 canonical videos freshly
  scanned with zero tracked mark frames, 1/1 canonical poster passed the hash-bound
  guard, zero quarantine files scanned, zero findings.
- All repository Python regression scripts: 31/31 PASS.
- Python syntax compilation: 177 files PASS.
- Automation policy guard: PASS.
- Manifest contract: 23 items, zero errors.
- Site smoke test: 71/71 pages PASS; 141 affiliate buttons structurally valid.
- Full preflight remains intentionally blocked: privacy guard FAIL and 21 official
  source reviews pending. It also reports seven warnings; these do not authorize
  publication.

## External actions

No social post, upload, schedule, deploy, commit, push, checkout click, or affiliate
click was performed during this safety work.
