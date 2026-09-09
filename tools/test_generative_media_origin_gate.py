#!/usr/bin/env python3
from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from generative_media_origin_gate import check, load_json, main, origin_problems, policy_problems


POLICY = {
    "schema_version": 1,
    "strict_no_watermark": True,
    "google_flow": {
        "role": "IDEATION_STORYBOARD_ONLY",
        "final_pixels_allowed": False,
        "final_audio_allowed": False,
    },
    "final_asset_required_fields": [
        "generator_origin", "contains_flow_pixels", "contains_flow_audio", "synthid_expected"
    ],
    "allowed_final_origins": ["LOCAL_HTML_SVG_FFMPEG_WINDOWS_TTS"],
}
ORIGIN = {
    "generator_origin": "LOCAL_HTML_SVG_FFMPEG_WINDOWS_TTS",
    "contains_flow_pixels": False,
    "contains_flow_audio": False,
    "synthid_expected": False,
}
PACK = {"days": [{"candidate_id": "fresh-01", "tiktok_draft": {
    "candidate_asset": {"path": "fresh.mp4", "media_origin": ORIGIN}
}}]}


class OriginGateTests(unittest.TestCase):
    def test_local_asset_passes(self):
        self.assertEqual(check(POLICY, PACK), [])

    def test_unknown_origin_blocks(self):
        pack = deepcopy(PACK)
        del pack["days"][0]["tiktok_draft"]["candidate_asset"]["media_origin"]
        self.assertTrue(check(POLICY, pack))

    def test_flow_pixels_block_even_when_visible_watermark_off(self):
        pack = deepcopy(PACK)
        pack["days"][0]["tiktok_draft"]["candidate_asset"]["media_origin"]["contains_flow_pixels"] = True
        self.assertTrue(check(POLICY, pack))

    def test_synthid_expected_blocks(self):
        pack = deepcopy(PACK)
        pack["days"][0]["tiktok_draft"]["candidate_asset"]["media_origin"]["synthid_expected"] = True
        self.assertTrue(check(POLICY, pack))

    def test_single_asset_origin_helper_is_fail_closed(self):
        self.assertEqual(policy_problems(POLICY), [])
        self.assertEqual(origin_problems(POLICY, ORIGIN), [])
        self.assertTrue(origin_problems(POLICY, None))

    def test_policy_cannot_allow_flow_by_self_attested_false_flags(self):
        policy = deepcopy(POLICY)
        policy["allowed_final_origins"].append("GOOGLE_FLOW")
        self.assertTrue(policy_problems(policy))

    def test_cli_describes_origin_as_attestation_not_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy_path = root / "policy.json"
            pack_path = root / "pack.json"
            policy_path.write_text(json.dumps(POLICY), encoding="utf-8")
            pack_path.write_text(json.dumps(PACK), encoding="utf-8")
            output = StringIO()
            with patch(
                "sys.argv",
                ["generative_media_origin_gate.py", "--policy", str(policy_path), "--pack", str(pack_path)],
            ), redirect_stdout(output):
                self.assertEqual(0, main())
            message = output.getvalue()
            self.assertIn("origin not independently verified", message)
            self.assertNotIn("Flow output absent", message)

    def test_duplicate_and_nonfinite_origin_evidence_is_rejected(self):
        values = (
            '{"schema_version":1,"strict_no_watermark":false,'
            '"strict_no_watermark":true}',
            '{"schema_version":1,"unused":NaN}',
            '{"schema_version":1,"unused":1e999}',
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.json"
            for value in values:
                path.write_text(value, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_json(path)


if __name__ == "__main__":
    unittest.main()
