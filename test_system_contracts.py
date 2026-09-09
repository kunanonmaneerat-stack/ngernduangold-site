#!/usr/bin/env python3
"""Root-level discovery entry point for the publication safety contracts.

`python -m unittest discover` previously found no tests because the operational
test modules live below ``tools/``.  Keep this file deliberately small: it
exposes the high-risk publication, media, calendar, and permanent-dedup suites
without changing any runtime behavior.
"""
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parent

UNITTEST_MODULES = (
    "pipeline.test_analytics_decision_safety",
    "pipeline.test_revenue_ledger",
    "tools.test_generative_media_origin_gate",
    "tools.test_week_content_r5_novelty_guard",
    "tools.test_content_calendar_guard",
    "tools.test_publisher_attempt_reconciliation",
    "tools.test_week_candidate_manifest_guard",
    "tools.test_batch_exit_contract",
    "tools.test_daily_media_gate",
    "tools.test_import_accesstrade_csv",
    "tools.test_instagram_publisher_safety",
    "tools.test_yt_upload_batch2_safety",
    "tools.test_current_evidence_status",
    "tools.test_agent_gap_check_readonly",
    "tools.test_own_product_fulfillment",
    "tools.test_preflight_fulfillment_contract",
    "tools.test_editorial_draft_gate",
)

SCRIPT_CONTRACTS = {
    "media_publish_guard": "tools/test_media_publish_guard.py",
    "post_ledger_completeness": "tools/test_post_ledger_completeness.py",
    "publication_authority": "tools/test_publication_authority.py",
    "improvement_loop": "pipeline/test_improvement_loop.py",
    "official_news_monitor": "pipeline/test_official_news_monitor.py",
    "content_source_gate": "tools/test_content_source_gate.py",
}


class ScriptContractTests(unittest.TestCase):
    """Make non-unittest safety suites visible to root discovery."""


def _script_test(relative_path):
    def run(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / relative_path)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
        )
        self.assertEqual(
            0,
            completed.returncode,
            "safety script failed: %s\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (relative_path, completed.stdout[-12000:], completed.stderr[-12000:]),
        )
    return run


for _name, _path in SCRIPT_CONTRACTS.items():
    setattr(ScriptContractTests, "test_script_" + _name, _script_test(_path))


def load_tests(loader, tests, pattern):
    suite = loader.loadTestsFromTestCase(ScriptContractTests)
    for module_name in UNITTEST_MODULES:
        # Let unittest turn an import/dependency failure into one explicit
        # _FailedTest and continue loading the remaining safety modules.  The
        # previous direct import aborted discovery at the first missing package,
        # so a single optional media dependency left every later contract
        # completely unexecuted while reporting only one opaque loader error.
        loaded = loader.loadTestsFromName(module_name)
        if loaded.countTestCases() == 0:
            raise AssertionError("configured unittest module exposed zero tests: " + module_name)
        suite.addTests(loaded)
    return suite
