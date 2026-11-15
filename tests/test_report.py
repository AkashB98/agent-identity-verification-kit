import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator import generate_dataset  # noqa: E402
from report import build_markdown_report, build_report  # noqa: E402


class TestReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = build_report(generate_dataset())

    def test_per_class_table_exact(self):
        pc = self.report["per_class"]
        self.assertEqual(pc["verified_human"],
                         {"allow": 114, "block": 0, "challenge": 6, "total": 120})
        self.assertEqual(pc["legitimate_agent"],
                         {"allow": 98, "block": 0, "challenge": 22, "total": 120})
        self.assertEqual(pc["unattributed_agent"],
                         {"allow": 0, "block": 40, "challenge": 40, "total": 80})
        self.assertEqual(pc["bad_bot"],
                         {"allow": 0, "block": 60, "challenge": 20, "total": 80})

    def test_totals_sum(self):
        self.assertEqual(self.report["sessions_total"], 400)
        self.assertEqual(self.report["totals"],
                         {"allow": 212, "block": 100, "challenge": 88})
        for cls, row in self.report["per_class"].items():
            self.assertEqual(row["allow"] + row["challenge"] + row["block"],
                             row["total"], cls)

    def test_headline_rates(self):
        self.assertEqual(self.report["fp_rate_legit_agent"], 0.1833)
        self.assertEqual(self.report["fp_rate_human"], 0.05)
        self.assertEqual(self.report["fraud_caught_rate"], 1.0)
        self.assertEqual(self.report["challenge_friction"], 0.1167)

    def test_challenge_outcomes(self):
        co = self.report["challenge_outcomes"]
        self.assertEqual(co["challenged_total"], 88)
        self.assertEqual(co["failed"], 20)   # only the mimicking bad bots fail
        self.assertEqual(co["passed"], 68)

    def test_no_bad_bot_allowed(self):
        self.assertEqual(self.report["per_class"]["bad_bot"]["allow"], 0)

    def test_markdown_contains_table_and_rates(self):
        md = build_markdown_report(generate_dataset())
        self.assertIn("| bad_bot | 0 | 20 | 60 | 80 |", md)
        self.assertIn("challenge friction", md.lower())


if __name__ == "__main__":
    unittest.main()
