import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import NOW, make_session  # noqa: E402
from policy import attestation_state, decide  # noqa: E402


class TestPolicy(unittest.TestCase):
    def test_valid_agent_allowed(self):
        d = decide(make_session())
        self.assertEqual(d["action"], "allow")
        self.assertEqual(d["attestation_state"], "valid")

    def test_pinned_expired_attestation_challenged(self):
        # Pinned hard case 1: legitimate agent, EXPIRED attestation.
        s = make_session(subgroup="expired_attestation", exp=NOW - 3600)
        d = decide(s)
        self.assertEqual(d["attestation_state"], "expired")
        self.assertEqual(d["action"], "challenge")
        self.assertEqual(d["challenge_outcome"], "pass")

    def test_pinned_mimicking_bot_not_allowed(self):
        # Pinned hard case 2: bad bot mimicking human timing.
        s = make_session(subgroup="mimics_human_timing", true_class="bad_bot",
                         token=None, cv=0.6, vel=5.0, challenge_outcome="fail")
        d = decide(s)
        self.assertEqual(d["attestation_state"], "missing")
        self.assertNotEqual(d["action"], "allow")
        self.assertEqual(d["action"], "challenge")
        self.assertEqual(d["challenge_outcome"], "fail")

    def test_forged_token_blocked(self):
        s = make_session(true_class="bad_bot", secret="FORGED-WRONG-SECRET")
        d = decide(s)
        self.assertEqual(d["attestation_state"], "invalid")
        self.assertEqual(d["action"], "block")

    def test_scope_mismatch_challenged(self):
        d = decide(make_session(scopes=("browse",)))
        self.assertEqual(d["attestation_state"], "scope_mismatch")
        self.assertEqual(d["action"], "challenge")

    def test_missing_regular_agent_blocked(self):
        d = decide(make_session(token=None, cv=0.10, vel=12.0))
        self.assertEqual(d["action"], "block")

    def test_missing_fast_agent_blocked(self):
        d = decide(make_session(token=None, cv=0.4, vel=50.0))
        self.assertEqual(d["action"], "block")

    def test_missing_moderate_agent_challenged(self):
        d = decide(make_session(token=None, cv=0.35, vel=9.0))
        self.assertEqual(d["action"], "challenge")

    def test_valid_burst_challenged(self):
        d = decide(make_session(cv=0.03, vel=45.0))
        self.assertEqual(d["action"], "challenge")

    def test_velocity_alone_never_punishes_valid(self):
        # Velocity is one minor feature: high velocity + varied timing
        # under a valid attestation must still allow.
        d = decide(make_session(cv=0.25, vel=45.0))
        self.assertEqual(d["action"], "allow")

    def test_regular_timing_alone_valid_allowed(self):
        d = decide(make_session(cv=0.03, vel=10.0))
        self.assertEqual(d["action"], "allow")

    def test_human_allowed(self):
        s = make_session(true_class="verified_human", principal="human",
                         token=None, cv=0.6, vel=5.0)
        d = decide(s)
        self.assertEqual(d["attestation_state"], "human_verified")
        self.assertEqual(d["action"], "allow")

    def test_human_regular_timing_challenged(self):
        s = make_session(true_class="verified_human", principal="human",
                         token=None, cv=0.08, vel=6.0)
        self.assertEqual(decide(s)["action"], "challenge")

    def test_challenge_outcome_none_when_not_challenged(self):
        self.assertIsNone(decide(make_session())["challenge_outcome"])
        s = make_session(true_class="bad_bot", secret="FORGED-WRONG-SECRET")
        self.assertIsNone(decide(s)["challenge_outcome"])


if __name__ == "__main__":
    unittest.main()
