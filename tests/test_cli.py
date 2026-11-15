import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli import EXIT_ERROR, EXIT_FAIL, EXIT_OK, main as cli_main  # noqa: E402
from cli import make_server, reset_state  # noqa: E402
from generator import dataset_to_json, generate_dataset  # noqa: E402


def _run(argv):
    with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
        code = cli_main(argv)
    return code, out.getvalue()


class TestCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = os.path.join(cls.tmp.name, "sessions.json")
        with open(cls.path, "w", encoding="utf-8") as fh:
            fh.write(dataset_to_json(generate_dataset()))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_generate_to_stdout(self):
        code, out = _run(["generate"])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(json.loads(out)["session_count"], 400)

    def test_report_md(self):
        code, out = _run(["report", "--input", self.path])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("per-class", out)

    def test_report_json(self):
        code, out = _run(["report", "--input", self.path, "--format", "json"])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(json.loads(out)["fraud_caught_rate"], 1.0)

    def test_check_pass(self):
        code, out = _run(["check", "--input", self.path])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("check PASS", out)

    def test_check_missing_file(self):
        code, _ = _run(["check", "--input", "/nope/missing.json"])
        self.assertEqual(code, EXIT_ERROR)

    def test_check_breach_when_bot_allowed(self):
        data = generate_dataset()
        # Corrupt: give a mimicking bot a valid token -> it would be allowed.
        from tokens import issue_token
        for s in data["sessions"]:
            if s["subgroup"] == "mimics_human_timing":
                s["token"] = issue_token(s["human_id"], s["agent_id"],
                                         ["browse", "checkout"],
                                         s["now"] + 3600, issued_at=s["now"])
                break
        bad_path = os.path.join(self.tmp.name, "bad.json")
        with open(bad_path, "w", encoding="utf-8") as fh:
            fh.write(dataset_to_json(data))
        code, out = _run(["check", "--input", bad_path])
        self.assertEqual(code, EXIT_FAIL)
        self.assertIn("check FAIL", out)

    def test_demo_exit_0(self):
        code, _ = _run(["demo"])
        self.assertEqual(code, EXIT_OK)


class TestServe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reset_state(generate_dataset())
        cls.server = make_server(0)
        cls.port = cls.server.server_address[1]
        cls.t = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close()

    def _get(self, path):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())

    def test_health(self):
        status, body = self._get("/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")

    def test_report(self):
        status, body = self._get("/report")
        self.assertEqual(status, 200)
        self.assertEqual(body["sessions_total"], 400)
        self.assertEqual(body["per_class"]["bad_bot"]["allow"], 0)

    def test_unknown_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/nope")
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
