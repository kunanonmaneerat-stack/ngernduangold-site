#!/usr/bin/env python3
"""Isolated regressions for observable fulfillment and bounded local artifacts.

All fixtures are temporary. No platform, production file or payment endpoint is
touched; a PASS here means the local guard is consistent, not verified revenue.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import preflight as P


class FulfillmentContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fulfillment_contract_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        (self.root / "site").mkdir()
        self.page = self.root / "site" / "offer.html"
        self.page.write_text('<a data-buy="kit">Buy</a>', encoding="utf-8")
        self.policy = self.root / "policy.json"

    def run_guard(self, deliverable, *, page="site/offer.html", authorized=True):
        self.policy.write_text(json.dumps({"products": {"items": [{
            "id": "kit", "sold_on": page, "deliverable": deliverable,
            "promotion_authorized": authorized, "status": "DELIVERABLE_READY",
        }]}}), encoding="utf-8")
        outcomes = []
        with patch.object(P, "REPO", str(self.root)), \
                patch.object(P, "POLICY", str(self.policy)), \
                patch.object(P, "add", side_effect=lambda *row: outcomes.append(row)):
            P.check_deliverables()
        self.assertEqual(1, len(outcomes))
        return outcomes[0][1:]

    def artifact(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * (P.MIN_DELIVERABLE_BYTES + 1))
        return path

    def test_relative_local_artifact_is_accepted(self):
        self.artifact(self.root / "files" / "kit.pdf")
        self.assertEqual("PASS", self.run_guard("files/kit.pdf")[0])

    def test_existing_public_purchase_cannot_hide_behind_missing_sold_on(self):
        status, detail = self.run_guard(None, page="site/deleted.html")
        self.assertEqual("FAIL", status)
        self.assertIn("nothing to hand over", detail)

    def test_retired_missing_page_without_public_intent_is_out_of_scope(self):
        self.page.write_text("Retired", encoding="utf-8")
        self.assertEqual("PASS", self.run_guard(None, page="site/deleted.html")[0])

    def test_relative_artifact_outside_project_is_rejected(self):
        self.artifact(self.root.parent / "outside.pdf")
        self.assertEqual("FAIL", self.run_guard("../outside.pdf")[0])

    def test_absolute_artifact_is_rejected_even_inside_project(self):
        artifact = self.artifact(self.root / "files" / "kit.pdf")
        self.assertEqual("FAIL", self.run_guard(str(artifact.resolve()))[0])

    def test_non_string_artifact_fails_closed_without_crashing(self):
        self.assertEqual("FAIL", self.run_guard({"path": "files/kit.pdf"})[0])

    def test_directory_never_counts_as_deliverable_even_if_size_is_large(self):
        directory = self.root / "files"
        directory.mkdir()
        with patch.object(P.os.path, "getsize", return_value=P.MIN_DELIVERABLE_BYTES + 1):
            self.assertEqual("FAIL", self.run_guard("files")[0])

    def test_authorized_hosted_artifact_is_unverified_not_pass(self):
        status, detail = self.run_guard("gumroad:l/kit")
        self.assertEqual("WARN", status)
        self.assertIn("not checkable", detail)

    def test_disabled_hosted_product_can_pass_guard_but_is_not_ready(self):
        self.page.write_text("Promotion paused", encoding="utf-8")
        status, detail = self.run_guard("gumroad:l/kit", authorized=False)
        self.assertEqual("PASS", status)
        self.assertIn("0 ready", detail)
        self.assertIn("promotion-disabled", detail)
        self.assertIn("not checkable", detail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
