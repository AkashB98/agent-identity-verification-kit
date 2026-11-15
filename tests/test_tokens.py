import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tokens import DEMO_SECRET, issue_token, verify_token  # noqa: E402

NOW = 1_700_000_000


class TestTokens(unittest.TestCase):
    def test_roundtrip_valid(self):
        tok = issue_token("human-1", "agent-1", ["browse", "checkout"],
                          NOW + 3600, issued_at=NOW)
        v = verify_token(tok, required_scope="checkout", now=NOW)
        self.assertEqual(v["status"], "valid")
        self.assertEqual(v["human_id"], "human-1")
        self.assertEqual(v["agent_id"], "agent-1")
        self.assertEqual(v["scopes"], ["browse", "checkout"])

    def test_scopes_sorted_in_payload(self):
        a = issue_token("h", "a", ["checkout", "browse"], NOW + 10, issued_at=NOW)
        b = issue_token("h", "a", ["browse", "checkout"], NOW + 10, issued_at=NOW)
        self.assertEqual(a, b)

    def test_expired(self):
        tok = issue_token("h", "a", ["checkout"], NOW - 1, issued_at=NOW - 7200)
        self.assertEqual(verify_token(tok, now=NOW)["status"], "expired")

    def test_expiry_boundary_not_expired(self):
        tok = issue_token("h", "a", ["checkout"], NOW, issued_at=NOW - 10)
        self.assertEqual(verify_token(tok, now=NOW)["status"], "valid")

    def test_missing(self):
        self.assertEqual(verify_token(None, now=NOW)["status"], "missing")
        self.assertEqual(verify_token("", now=NOW)["status"], "missing")

    def test_tampered_signature_invalid(self):
        tok = issue_token("h", "a", ["checkout"], NOW + 100, issued_at=NOW)
        bad = tok[:-1] + ("0" if tok[-1] != "0" else "1")
        self.assertEqual(verify_token(bad, now=NOW)["status"], "invalid")

    def test_tampered_payload_invalid(self):
        tok = issue_token("h", "a", ["checkout"], NOW + 100, issued_at=NOW)
        payload, _, sig = tok.rpartition(".")
        bad = ("A" if payload[0] != "A" else "B") + payload[1:] + "." + sig
        self.assertEqual(verify_token(bad, now=NOW)["status"], "invalid")

    def test_wrong_secret_invalid(self):
        tok = issue_token("h", "a", ["checkout"], NOW + 100, issued_at=NOW,
                          secret="FORGED-WRONG-SECRET")
        self.assertEqual(verify_token(tok, now=NOW)["status"], "invalid")

    def test_malformed_invalid(self):
        for bad in ("not-a-token", ".", "abc.", ".abc", "a.b.c.d"):
            self.assertEqual(verify_token(bad, now=NOW)["status"], "invalid", bad)

    def test_scope_mismatch(self):
        tok = issue_token("h", "a", ["browse"], NOW + 100, issued_at=NOW)
        v = verify_token(tok, required_scope="checkout", now=NOW)
        self.assertEqual(v["status"], "scope_mismatch")

    def test_no_required_scope_ok(self):
        tok = issue_token("h", "a", ["browse"], NOW + 100, issued_at=NOW)
        self.assertEqual(verify_token(tok, now=NOW)["status"], "valid")

    def test_expired_beats_scope_mismatch(self):
        tok = issue_token("h", "a", ["browse"], NOW - 5, issued_at=NOW - 100)
        v = verify_token(tok, required_scope="checkout", now=NOW)
        self.assertEqual(v["status"], "expired")

    def test_demo_secret_is_placeholder(self):
        self.assertIn("DEMO", DEMO_SECRET)
        self.assertIn("do-not-use", DEMO_SECRET)


if __name__ == "__main__":
    unittest.main()
