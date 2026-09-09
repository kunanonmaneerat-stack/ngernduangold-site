import datetime
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import preflight


class PostingCapClaimTests(unittest.TestCase):
    def _run(self, raw_lines):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = os.path.join(tmp, "post-ledger.jsonl")
            with open(ledger, "w", encoding="utf-8", newline="\n") as handle:
                handle.writelines(raw_lines)
            with mock.patch.object(preflight, "LEDGER", ledger):
                preflight.results[:] = []
                preflight.check_posting_cap()
                return dict(preflight.results[0])

    @staticmethod
    def _claim(index, day, hour):
        return {
            "dedup_key": "claim-%d" % index,
            "channel": "yt",
            "clip_key": "sha256:" + str(index) * 64,
            "scheduled_for": day,
            "scheduled_at": "%sT%02d:00:00+07:00" % (day, hour),
            "posted_at": "%sT07:00:00+07:00" % day,
            "type": "claim",
            "status": "claimed",
        }

    @staticmethod
    def _line(row):
        return json.dumps(row, separators=(",", ":")) + "\n"

    def test_three_sha256_claims_reserve_youtube_daily_quota(self):
        today = datetime.date.today().isoformat()
        result = self._run([
            self._line(self._claim(1, today, 8)),
            self._line(self._claim(2, today, 12)),
            self._line(self._claim(3, today, 16)),
        ])
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("3 posts", result["detail"])

    def test_confirmation_status_does_not_double_count_claim(self):
        today = datetime.date.today().isoformat()
        first = self._claim(1, today, 8)
        second = self._claim(2, today, 12)
        result = self._run([
            self._line(first),
            self._line({"dedup_key": first["dedup_key"], "type": "status",
                        "status": "POSTED", "post_id": "video-1"}),
            self._line(second),
            self._line({"dedup_key": second["dedup_key"], "type": "status",
                        "status": "POSTED", "post_id": "video-2"}),
        ])
        self.assertEqual(result["status"], "PASS")

    def test_claim_uses_scheduled_day_not_local_claim_write_day(self):
        today = datetime.date.today()
        rows = []
        for index in range(1, 4):
            day = (today + datetime.timedelta(days=index - 1)).isoformat()
            rows.append(self._line(self._claim(index, day, 8)))
        self.assertEqual(self._run(rows)["status"], "PASS")

    def test_malformed_json_fails_closed_instead_of_under_counting(self):
        result = self._run(["{not-json\n"])
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("malformed", result["detail"])

    def test_unclassifiable_claim_fails_closed(self):
        today = datetime.date.today().isoformat()
        row = self._claim(1, today, 8)
        row.pop("scheduled_for")
        result = self._run([self._line(row)])
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("unclassifiable", result["detail"])

    def test_claim_missing_exact_scheduled_time_fails_closed(self):
        today = datetime.date.today().isoformat()
        row = self._claim(1, today, 8)
        row.pop("scheduled_at")
        result = self._run([self._line(row)])
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("unclassifiable", result["detail"])

    def test_claim_malformed_scheduled_time_fails_closed(self):
        today = datetime.date.today().isoformat()
        row = self._claim(1, today, 8)
        row["scheduled_at"] = "not-an-iso-timestamp"
        result = self._run([self._line(row)])
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("unclassifiable", result["detail"])


if __name__ == "__main__":
    unittest.main()
