import hashlib
import os
import sys
import unittest
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator import dataset_to_json, generate_dataset  # noqa: E402
from validation import validate_dataset  # noqa: E402


class TestGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = generate_dataset()

    def test_deterministic(self):
        self.assertEqual(self.data, generate_dataset())
        self.assertEqual(dataset_to_json(self.data),
                         dataset_to_json(generate_dataset()))

    def test_byte_stable_md5(self):
        h1 = hashlib.md5(dataset_to_json(generate_dataset()).encode()).hexdigest()
        h2 = hashlib.md5(dataset_to_json(generate_dataset()).encode()).hexdigest()
        self.assertEqual(h1, h2)

    def test_total_and_class_counts(self):
        self.assertEqual(self.data["session_count"], 400)
        counts = Counter(s["true_class"] for s in self.data["sessions"])
        self.assertEqual(counts, {"verified_human": 120, "legitimate_agent": 120,
                                  "unattributed_agent": 80, "bad_bot": 80})

    def test_subgroup_counts(self):
        counts = Counter(s["subgroup"] for s in self.data["sessions"])
        self.assertEqual(counts["expired_attestation"], 10)
        self.assertEqual(counts["mimics_human_timing"], 20)
        self.assertEqual(counts["forged_token"], 30)
        self.assertEqual(counts["scope_mismatch"], 6)

    def test_validates_clean(self):
        self.assertEqual(validate_dataset(self.data), [])

    def test_unique_session_ids(self):
        ids = [s["session_id"] for s in self.data["sessions"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_bad_bots_fail_challenge_humans_pass(self):
        for s in self.data["sessions"]:
            if s["true_class"] == "bad_bot":
                self.assertEqual(s["challenge_outcome"], "fail", s["session_id"])
            else:
                self.assertEqual(s["challenge_outcome"], "pass", s["session_id"])

    def test_different_seed_differs(self):
        self.assertNotEqual(generate_dataset(seed=7), self.data)


if __name__ == "__main__":
    unittest.main()
