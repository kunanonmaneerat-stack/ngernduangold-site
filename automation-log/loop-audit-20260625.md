# ngernduangold loop wiring audit (end-to-end) - 2026-06-25

Producer->consumer audit of L1-L8 (handoff path/format, scripts exist+run, schema, graceful, dry-run).
Method: deterministic scripts + safe dry-runs; fixes via python I/O (NO Edit/Write on Thai files), .bak+assert.
No commit/push. (romanized Thai for ASCII safety)

| loop | handoff | scripts exist/import | dry-run | status |
|---|---|---|---|---|
| L1 content | build_site is SELF-CONTAINED (does NOT read pipeline output). Social pipeline (trend_ingest->script_gen/content_council->comply_gate.gate) feeds SOCIAL posts; build_site is a separate static-site generator with articles authored in build_site.py | all exist + import OK | build_site->site/ no crash; comply_gate units PASS; content_council writes council-<date>.md | OK (decoupled by design - not a broken handoff) |
| L2 social-ops daily | comply_gate(3.5)+content_council(3.6) ARE in real path; post->log_run(routine ngernduangold-social-ops-daily)->telegram --from-log | exist | gate BAD/GOOD/negated PASS | OK |
| L3 measurement | ga4_pull/gsc_pull -> csv -> analyst/reconcile -> weekly-review SKILL | ga4_pull, gsc_pull import OK; reconcile.py EXISTS (ga4-admin, outside repo by design) | imports OK | OK |
| L4 conversion | reconcile (sub_id<->conversion<->payout) -> first-signal -> telegram SIGNAL (only on confirmed AccessTrade conversion) | reconcile exists; first-signal wired | --from-log == --routine match | OK |
| L5 proof-of-run | log_run -> automation-log/YYYY-MM.jsonl + latest.md -> telegram --from-log | exist | ROUNDTRIP PASS: log_run _selftest -> from_log msg contains routine+status+metric, NOT 'cannot verify' (test entry cleaned) | OK |
| L6 monitoring | cc_monitor, agent-auditor, cowork-task-watchdog, credit_tracker, hermes_digest, traffic_monitor | import OK (cc_monitor/credit_tracker/hermes_digest/traffic_monitor) + AST OK | - | OK |
| L7 assets | art_to_stitch->Stitch->CC->cc_monitor; video_downloader->post_dispatcher; threads_refill; pinterest-weekly | art_to_stitch, video_downloader, post_dispatcher, threads_refill all import OK | - | OK |
| L8 SEO/domain | SITE_BASE/canonical/sitemap -> GSC -> gsc_pull AUTO-SWITCH | gsc_pull | _pick_property prefers ngernduangold.com -> sc-domain -> www -> netlify.app (graceful fallback); NOT hardcoded to stale domain | OK (auto-switch ready for .com) |

## cross-cutting (STEP 2)
- 2.1 PowerShell `&&` in git proof-of-run steps: FOUND in 7 SKILLs -> FIXED to `;`.
  Fixed: comment-loop, delivery-heartbeat, delivery-verify, first-signal, link-health (2 lines), pantip-monitor, queue-keeper.
  Preserved correctly: JS paste-event `&&` (browser) and netlify-build `&&` (Linux sh). The 2 still-matching lines are
  warning-NOTE text ("use ; not &&"), not commands.
- 2.2 every `--from-log <R>` == `log_run --routine <R>`: first-signal, social-ops-daily, weekly-review -> ALL MATCH.
- 2.3 script paths referenced in SKILLs: all exist.
- free_llm POOL: 6 providers, all 4-field tuples (label,url,model,env_key), lead = or-nemotron-ultra, no duplicate.

## FIXED this session
- 7 SKILL.md git proof-of-run steps: `&&` -> `;` (PowerShell-safe). python I/O + per-line reversible-assert + .bak;
  JS/netlify `&&` preserved; Thai intact; 0 files damaged. EFFECT: proof-of-run git commit/push will no longer fail
  silently on Windows PowerShell -> run-logs actually reach GitHub for Cowork to see (config != delivered).

## FLAG for owner
1. [LOW-later] canonical -> ngernduangold.com after DNS+SSL of the new domain is live. gsc_pull ALREADY auto-switches
   when the .com GSC property has data; build_site SITE_BASE stays netlify.app for now (correct). No action needed yet.
2. [INFO] L1: build_site is independent of the social-content pipeline (by design). If the intent is for the pipeline
   to generate SITE articles, that wiring does not exist (site articles are currently authored in build_site.py).

## verification
- AST sweep 0 fail; core+asset+monitoring imports OK; comply_gate units PASS; smoke 55/55; L5 roundtrip PASS; gsc auto-switch correct.
- NO commit/push/git add -A. No cron/cadence/post-logic/<=5-cap/article-content/canonical/secret touched.
- python I/O ONLY on Thai files (7 SKILL.md). 0 files damaged (every .bak verified then removed on pass; auto-restore on any fail).
