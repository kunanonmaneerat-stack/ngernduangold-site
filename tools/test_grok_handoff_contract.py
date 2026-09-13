"""Local document-contract checks only; never proves receiver access or publishing."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HandoffContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / '.system_control/grok_handoff.json').read_text(encoding='utf-8'))
        cls.roles = json.loads((ROOT / '.system_control/role_capabilities.json').read_text(encoding='utf-8'))
        cls.routines = [(ROOT / 'automation-log/grok-routines' / name).read_text(encoding='utf-8') for name in (
            'ROUTINE-0_capability-probe.md', 'ROUTINE-1_daily-readiness.md', 'ROUTINE-2_publish-slot.md')]

    def test_prepared_is_not_activation(self):
        self.assertEqual(self.data['status'], 'PREPARED_AWAITING_RECEIVER_ACCEPTANCE')
        self.assertIs(self.data['activation_authorized'], False)
        self.assertIs(self.data['scheduler_changes_authorized'], False)

    def test_single_canonical_sources(self):
        refs = self.data['sources_of_truth']
        self.assertEqual(refs['ledger'], 'automation-log/post-ledger.jsonl')
        self.assertEqual(refs['editorial_calendar'], '.system_control/content_calendar.json')
        for value in refs.values():
            self.assertTrue((ROOT / value).is_file(), value)
        self.assertNotIn('placements', self.data)

    def test_roles_respect_existing_capabilities(self):
        self.assertEqual(set(self.data['role_assignments']), {'codex', 'cowork', 'grok', 'owner'})
        self.assertIs(self.roles['actors']['grok']['local_write'], False)
        for actor in ('codex', 'cowork'):
            self.assertIs(self.roles['actors'][actor]['social_publish'], False)

    def test_no_false_receiver_acceptance(self):
        for destination in self.data['destinations'].values():
            self.assertEqual(destination['acceptance_status'], 'UNKNOWN')
        self.assertEqual(self.data['destinations']['grok']['delivery_status'], 'NOT_SENT')

    def test_probe_has_no_mutations(self):
        probe = self.data['read_only_probe']
        for field in ('create_drafts', 'delete_drafts', 'upload_media', 'follow_affiliate_trackers', 'change_scheduler'):
            self.assertIs(probe[field], False)
        self.assertNotIn('ลบ draft นั้นทันที', self.routines[0])
        self.assertNotIn('https://ngernduangold.com/links', self.routines[0])

    def test_identity_and_room_separation(self):
        for field in ('page_only', 'trading_rooms_excluded', 'pantip_publication_excluded'):
            self.assertIs(self.data['separation'][field], True)
        self.assertIs(self.data['separation']['independent_publishers_for_same_job'], False)
        self.assertIs(self.data['separation']['grok_canonical_ledger_write'], False)
        self.assertIn('PUBLIC_IDENTITY_PAGE_ONLY', self.routines[0])

    def test_non_authorizing_precheck_and_unknown_claim(self):
        for routine in self.routines[1:]:
            self.assertIn('PRECHECK_READY_NOT_AUTHORIZED', routine)
        self.assertIn('UNKNOWN field: claim_ack', self.routines[2])
        self.assertIn('รวมทุก operator', self.routines[2])

    def test_review_and_cadence_explicit(self):
        self.assertTrue((ROOT / self.data['review_request']).is_file())
        self.assertEqual(self.data['operational_cadence']['status'], 'PROPOSED_NOT_SCHEDULED')
        self.assertIn('Do not retry', self.data['unknown_outcome_rule'])
        self.assertEqual(len(self.data['required_before_first_publication']), 7)


if __name__ == '__main__':
    unittest.main()
