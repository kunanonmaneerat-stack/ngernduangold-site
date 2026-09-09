# ngernduangold-site

Thai personal-finance website and publishing operations for เงินเดือนสมองทอง.
The business objective is repeatable, verified affiliate revenue from useful,
accurate content. Clicks, drafts, and successful diagnostic runs are separate
from paid revenue and verified publications.

## Project map

- `build_site.py`, root HTML, `components/`: website sources; build output is `site/`.
- `.system_control/policy.json`: channel, product, pause, and publication policy.
- `.system_control/content_calendar.json`: placements and their explicit states.
- `.system_control/improvement_policy.json`: evidence SLA, score definitions, and learning rules.
- `tools/`: content, media, source, privacy, release, and scheduler checks.
- `pipeline/`: measurement readers, revenue reconciliation, and improvement runs.
- `automation-log/`: operational history; private raw evidence and receipts belong in `.local-private/runtime/`.

## Local verification on Windows

Run from the project root. The runtime launcher selects an installed Python with
the dependencies required by media checks.

```powershell
# Inspect the saved evidence against current files and the actual time (read-only).
.\pipeline\python_runtime.cmd -B pipeline\improvement_loop.py status --json

# Rebuild and inspect the local website; these commands do not deploy it.
.\pipeline\python_runtime.cmd -B build_site.py
.\pipeline\python_runtime.cmd -B tools\postdeploy_smoke.py --src site
.\pipeline\python_runtime.cmd -B tools\test_offer_integrity.py

# Regression suite, including publication, media, revenue, and evidence contracts.
.\pipeline\python_runtime.cmd -B -m unittest discover

# After local changes are frozen, collect a new private evidence bundle.
.\pipeline\python_runtime.cmd -B pipeline\improvement_loop.py run --mode local-safe --json
```

`status` does not refresh sources or rewrite old evidence. Its `current_evidence`
reports the historical score separately from the current score. `INPUT_DRIFT`,
`STALE`, `INVALID`, and `UNKNOWN` cannot support a current readiness claim.
Failed validation and expired child evidence cannot acquire a current score.
A fresh control
run can still finish `COMPLETED_WITH_BLOCKERS` because business inputs remain
unavailable. Exit code 2 reports a block; exit code 3 reports a runner failure.

## Reading operational results

The calendar preserves total status counts for compatibility and also exposes
active blocked backlog, expired placements, the next 48 hours, and rolling
seven-day coverage. An expired blocked placement is not an eligible missed post
and cannot be replayed automatically.

Scheduler checks distinguish active jobs from recent disabled history. A disabled
job is not recovered merely because it disappeared from the active count;
completion requires its matching terminal receipt and deliverable. A pause of
Cowork tasks does not exempt enabled Claude Code or Windows tasks.

Affiliate link checks establish URL and product mapping integrity. They do not
prove the merchant campaign is still accepting conversions. Revenue requires
fresh reconciled source evidence; missing or stale evidence means unavailable.

## Release and data handling

Netlify is connected to Git; eligible pushes can publish the site. Build and test
locally before a separately authorized release. Review `netlify.toml`, policy,
and release evidence before changing the public site. Keep source-review,
watermark/audio QA, account identity, and publication claims tied to the exact
content and file hashes. Preserve existing worktree changes during maintenance.
