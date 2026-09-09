#!/usr/bin/env python3
"""Isolated fail-closed tests for build_site own-product fulfillment.

``build_site.py`` generates files at import time, so these tests compile only
the policy constant and loader function from its AST.  No site output, network
call, policy mutation, or payment endpoint is touched.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build_site.py"


def isolated_loader():
    tree = ast.parse(BUILD.read_text(encoding="utf-8"), filename=str(BUILD))
    selected = []
    for node in tree.body:
        if (isinstance(node, ast.Assign) and
                any(isinstance(target, ast.Name) and
                    target.id == "OWN_PRODUCT_DELIVERABLE_BINDINGS"
                    for target in node.targets)):
            selected.append(node)
        elif (isinstance(node, ast.FunctionDef) and
              node.name == "load_own_product_policy"):
            selected.append(node)
    if len(selected) != 2:
        raise AssertionError("build policy loader AST contract changed")
    namespace = {"os": os, "json": json, "__file__": str(BUILD)}
    exec(compile(ast.Module(body=selected, type_ignores=[]),
                 str(BUILD), "exec"), namespace)
    return (namespace["load_own_product_policy"],
            namespace["OWN_PRODUCT_DELIVERABLE_BINDINGS"])


class OwnProductFulfillmentTests(unittest.TestCase):
    def setUp(self):
        self.load, self.bindings = isolated_loader()

    @staticmethod
    def item(product_id, deliverable, *, status="DELIVERABLE_READY",
             authorized=True):
        return {
            "id": product_id,
            "deliverable": deliverable,
            "status": status,
            "promotion_authorized": authorized,
        }

    @staticmethod
    def write_policy(root: Path, items: list[dict]) -> Path:
        path = root / "policy.json"
        path.write_text(json.dumps({"products": {"items": items}}),
                        encoding="utf-8")
        return path

    def load_fixture(self, root: Path, items: list[dict]):
        return self.load(
            policy_path=self.write_policy(root, items),
            project_root=root,
        )

    def test_current_policy_loads_without_importing_or_building_site(self):
        products = self.load(
            policy_path=ROOT / ".system_control" / "policy.json",
            project_root=ROOT,
        )
        self.assertEqual(
            {"letter-kit-199", "ebook-59", "debt-toolkit-gumroad"},
            set(products),
        )
        self.assertTrue(all(
            item["promotion_authorized"] is False
            for item in products.values()
        ))

    def test_boolean_true_cannot_override_missing_status_or_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(SystemExit, "DELIVERABLE_READY"):
                self.load_fixture(root, [self.item(
                    "letter-kit-199", None,
                    status="PROMISED-BUT-MISSING",
                )])
            with self.assertRaisesRegex(SystemExit, "without a deliverable"):
                self.load_fixture(root, [self.item("ebook-59", None)])

    def test_letter_kit_cannot_impersonate_existing_ebook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "automation-log" / "_ebook_debt-payoff_v1.2.pdf"
            artifact.parent.mkdir()
            artifact.write_bytes(b"real-but-wrong-product")
            with self.assertRaisesRegex(SystemExit, "identity is not approved"):
                self.load_fixture(root, [self.item(
                    "letter-kit-199",
                    "automation-log/_ebook_debt-payoff_v1.2.pdf",
                )])

    def test_local_deliverable_must_exist_and_be_nonempty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item = self.item(
                "ebook-59", "automation-log/_ebook_debt-payoff_v1.2.pdf")
            with self.assertRaisesRegex(SystemExit, "missing or empty"):
                self.load_fixture(root, [item])

            artifact = root / "automation-log" / "_ebook_debt-payoff_v1.2.pdf"
            artifact.parent.mkdir()
            artifact.write_bytes(b"")
            with self.assertRaisesRegex(SystemExit, "missing or empty"):
                self.load_fixture(root, [item])

            artifact.write_bytes(b"verified-local-product")
            products = self.load_fixture(root, [item])
            self.assertTrue(products["ebook-59"]["promotion_authorized"])

    def test_local_deliverable_cannot_escape_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            outside = root.parent / "outside.pdf"
            outside.write_bytes(b"not-project-owned")
            self.bindings["ebook-59"] = "../outside.pdf"
            with self.assertRaisesRegex(SystemExit, "escapes the project"):
                self.load_fixture(root, [self.item(
                    "ebook-59", "../outside.pdf")])

    def test_absolute_local_deliverable_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "ebook.pdf"
            artifact.write_bytes(b"product")
            absolute = str(artifact.resolve())
            self.bindings["ebook-59"] = absolute
            with self.assertRaisesRegex(SystemExit, "project-relative"):
                self.load_fixture(root, [self.item("ebook-59", absolute)])

    def test_only_exact_hosted_toolkit_identity_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exact = self.item(
                "debt-toolkit-gumroad", "gumroad:l/debt-toolkit")
            products = self.load_fixture(root, [exact])
            self.assertTrue(
                products["debt-toolkit-gumroad"]["promotion_authorized"])

            with self.assertRaisesRegex(SystemExit, "identity is not approved"):
                self.load_fixture(root, [self.item(
                    "debt-toolkit-gumroad", "gumroad:l/debt-payoff-planner")])

    def test_unauthorized_missing_product_remains_validly_paused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            products = self.load_fixture(root, [self.item(
                "letter-kit-199", None,
                status="PROMISED-BUT-MISSING", authorized=False,
            )])
            self.assertFalse(products["letter-kit-199"]["promotion_authorized"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
