# components/stitch/

Scanned, comply-gate-PASSING Stitch/AI-exported HTML components land here.

Workflow (see automation-log/_stitch_execution_pack_20260627.md):
1. Generate a component in Stitch using the prompts in the execution pack. Every rate / % / fee /
   amount / approval-time / date MUST be a {{placeholder}}; NO testimonials / reviews / names / stars.
2. Scan it:  python3 tools/comply_gate_stitch.py components/stitch/<file>.html
   - exit 0 = OK to ship; exit 1 = has a FAIL (turn numbers into {{placeholders}}, remove fake reviews).
3. Only PASSING files belong here. The build ENFORCES this:
   - build_site.py calls gate_stitch() at build start -> scans this dir -> ABORTS the build on any FAIL
     (so Netlify and the weekly auditor can never publish a component with hardcoded finance numbers
     or fake reviews).
   - run_daily.cmd / run_weekly.cmd also scan this dir and log a FAIL loudly.
4. build_site.py fills {{placeholders}} ONLY from the verified data dict already used for the target
   page (numbers come from the existing verified source, never typed into the template).

Expected files (TASK 3, after owner runs Stitch):
  atf_hero.html, sticky_cta.html, compare_cards.html, trust_block.html
