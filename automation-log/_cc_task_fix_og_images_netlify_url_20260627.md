# CC TASK (from Cowork) — OG/cover images still bake OLD netlify.app URL (post-.com-migration leftover)

PRIORITY: polish / medium (NOT blocking — netlify.app still 301s to .com, so links work — but every social share card shows the OLD domain, which undercuts the .com authority play we just fixed in GSC).

## What Cowork found (while posting Digital-PR #1 to Blockdit)
The cover/OG PNGs in the repo have the text "ngernduangold.netlify.app/links" RENDERED INTO the image (pixel-baked), not pulled from a config string. Affected files (all live):
- site/og-default.png  (== cover_banner.png, 1640x664)
- site/og-loan.png     (== cover_banner_loan.png, 1640x664)
These are referenced as og:image across articles -> when a page is shared on FB / LINE / Threads, the card shows the stale netlify.app URL.

NOTE: a plain `grep netlify.app --include=*.py` only hits pipeline/gsc_pull.py (unrelated skip-logic). The URL is inside the PNG pixels, so the generator is elsewhere (a one-off script, an HTML/SVG->PNG step, or a design asset). Find the source, don't just grep the string.

## Do
1. Locate how og-default.png / og-loan.png / cover_banner*.png were produced:
   - search for a generator: `grep -rIl -e "og-default" -e "cover_banner" -e "og-loan" --include=*.py --include=*.html --include=*.svg --include=*.sh .`
   - check _gen_loan_infographics.py and any *infographic*.html / SVG templates for a "/links" or "netlify" footer band.
   - if it was hand-made (no generator), flag back to owner (may need re-export); do NOT fabricate a new design.
2. If a generator/source is found: change the baked URL from `ngernduangold.netlify.app/links` -> `ngernduangold.com` (or `ngernduangold.com/links`). Keep everything else identical (brand, taglines, colors #0F172A/gold).
3. Regenerate the PNGs, keep same filenames + dimensions (1640x664), keep file size reasonable (<100KB).
4. Rebuild site (build_site.py) so site/ copies pick up the new images.
5. Verify: `grep -r "netlify.app" site/*.html` should already be clean (CC fixed earlier); additionally confirm visually the new PNGs no longer show netlify.app (or OCR / open them).
6. Commit + push (owner/CC only). Report back to Cowork: which generator, what changed, before/after.

## Context
- This is a leftover from the netlify.app -> ngernduangold.com primary-domain migration (HTML/canonical were fixed; these baked image assets were missed).
- Cowork worked around it for the Blockdit post by using a clean logo-on-dark cover (no URL) instead — so Digital-PR #1 is fine. This task is to fix the ASSETS for all future shares.
