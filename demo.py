"""End-to-end demo: tokens -> generate -> validate -> policy -> report
-> check gates -> serve round-trip.

SYNTHETIC DATA ONLY (fictional principals and agents). Runs fully
offline; the serve round-trip is loopback-only on an ephemeral port.
Every stage asserts.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli import check_dataset, make_server, reset_state  # noqa: E402
from generator import generate_dataset  # noqa: E402
from policy import decide  # noqa: E402
from report import build_markdown_report, build_report  # noqa: E402
from tokens import issue_token, verify_token  # noqa: E402
from validation import validate_dataset  # noqa: E402

NOW = 1_700_000_000


def _get(port: int, path: str):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, resp.read()


def main() -> None:
    print("== 1. attestation token: issue + verify (HMAC-SHA256) ==")
    tok = issue_token("human-001", "agent-x", ["browse", "checkout"],
                      NOW + 3600, issued_at=NOW - 600)
    v = verify_token(tok, required_scope="checkout", now=NOW)
    assert v["status"] == "valid", v
    assert verify_token(tok, required_scope="checkout", now=NOW + 7200)["status"] == "expired"
    tampered = tok[:-1] + ("0" if tok[-1] != "0" else "1")
    assert verify_token(tampered, now=NOW)["status"] == "invalid"
    print("   valid / expired / tampered-invalid all verified")

    print("\n== 2. generate synthetic sessions (seed=42, 400 sessions) ==")
    data = generate_dataset()
    assert data == generate_dataset(), "generator must be deterministic"
    assert validate_dataset(data) == [], validate_dataset(data)[:3]
    print(f"   {data['session_count']} sessions, deterministic re-generation verified")

    print("\n== 3. pinned hard cases ==")
    expired = next(s for s in data["sessions"] if s["subgroup"] == "expired_attestation")
    d = decide(expired)
    assert d["action"] == "challenge", d
    print(f"   expired attestation ({expired['session_id']}): {d['action']} — {d['reason']}")
    mimic = next(s for s in data["sessions"] if s["subgroup"] == "mimics_human_timing")
    d = decide(mimic)
    assert d["action"] == "challenge" and d["challenge_outcome"] == "fail", d
    print(f"   human-timing mimic ({mimic['session_id']}): {d['action']}, "
          f"step-up outcome={d['challenge_outcome']} — {d['reason']}")

    print("\n== 4. per-class x per-action report ==")
    report = build_report(data)
    print(build_markdown_report(data))
    assert report["per_class"]["bad_bot"]["allow"] == 0

    print("== 5. POC gates (check) ==")
    breaches, _ = check_dataset(data)
    assert breaches == [], breaches
    print("   all POC gates pass")

    print("== 6. serve round-trip (GET /health, GET /report) ==")
    reset_state(data)
    server = make_server(0)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        status, body = _get(port, "/health")
        assert status == 200 and json.loads(body)["status"] == "ok"
        status, body = _get(port, "/report")
        served = json.loads(body)
        assert status == 200 and served == report, "served report must match local report"
        print(f"   /health ok, /report matches local report (port {port})")
    finally:
        server.shutdown(); server.server_close()

    print("\nDemo result: PASS")


if __name__ == "__main__":
    main()
