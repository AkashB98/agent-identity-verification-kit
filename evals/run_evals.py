#!/usr/bin/env python3
"""Golden evals for agent-identity-verification-kit.

SYNTHETIC DATA ONLY. Every eval is deterministic: run_evals.py writes
eval_report.json (sort_keys, indent=2, no timestamps) and the file must
be byte-identical across runs.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import threading
import urllib.request
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli import EXIT_OK, check_dataset  # noqa: E402
from cli import main as cli_main, make_server, reset_state  # noqa: E402
from generator import dataset_to_json, generate_dataset  # noqa: E402
from policy import decide  # noqa: E402
from report import build_report  # noqa: E402
from tokens import issue_token, verify_token  # noqa: E402
from validation import validate_dataset  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURE = os.path.join(ROOT, "fixtures", "sample_sessions.json")
RESULTS = []
NOW = 1_700_000_000


def check(name, passed, detail=""):
    RESULTS.append({"name": name, "passed": bool(passed), "detail": detail})
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return passed


def _run_cli(argv):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return cli_main(argv)


def main():
    print("== golden evals: agent-identity-verification-kit ==")
    data = generate_dataset()
    report = build_report(data)

    # E1: generator determinism (bytes pinned by md5 equality across runs)
    t1 = dataset_to_json(generate_dataset())
    t2 = dataset_to_json(generate_dataset())
    check("E1 generator determinism (seed=42, 400 sessions)",
          t1 == t2, f"md5={hashlib.md5(t1.encode()).hexdigest()}")

    # E2: dataset validates clean and matches the committed fixture bytes
    fixture_text = open(FIXTURE, encoding="utf-8").read() if os.path.exists(FIXTURE) else ""
    check("E2 dataset valid + fixture bytes match generator output",
          validate_dataset(data) == [] and fixture_text == t1)

    # E3: token round-trip + tamper detection
    tok = issue_token("human-1", "agent-1", ["browse", "checkout"],
                      NOW + 3600, issued_at=NOW)
    tampered = tok[:-1] + ("0" if tok[-1] != "0" else "1")
    check("E3 token verify: valid ok, tampered invalid",
          verify_token(tok, required_scope="checkout", now=NOW)["status"] == "valid"
          and verify_token(tampered, now=NOW)["status"] == "invalid")

    # E4: PINNED — legitimate agent with EXPIRED attestation is challenged
    expired = [s for s in data["sessions"] if s["subgroup"] == "expired_attestation"]
    check("E4 pinned: expired attestation -> challenge (never allow/block)",
          len(expired) == 10
          and all(decide(s)["action"] == "challenge" for s in expired),
          f"{len(expired)} expired-attestation sessions")

    # E5: PINNED — bad bot mimicking human timing is never allowed, fails step-up
    mimics = [s for s in data["sessions"] if s["subgroup"] == "mimics_human_timing"]
    mimic_decisions = [decide(s) for s in mimics]
    check("E5 pinned: human-timing mimic -> challenge + step-up fail",
          len(mimics) == 20
          and all(d["action"] == "challenge" for d in mimic_decisions)
          and all(d["challenge_outcome"] == "fail" for d in mimic_decisions),
          f"{len(mimics)} mimicking bots")

    # E6: no bad bot is ever allowed; fraud caught rate is 1.0
    check("E6 bad_bot allow == 0 and fraud_caught_rate == 1.0",
          report["per_class"]["bad_bot"]["allow"] == 0
          and report["fraud_caught_rate"] == 1.0)

    # E7: per-class x per-action table is exact and sums to totals
    pc = report["per_class"]
    exact = (
        pc["verified_human"] == {"allow": 114, "block": 0, "challenge": 6, "total": 120}
        and pc["legitimate_agent"] == {"allow": 98, "block": 0, "challenge": 22, "total": 120}
        and pc["unattributed_agent"] == {"allow": 0, "block": 40, "challenge": 40, "total": 80}
        and pc["bad_bot"] == {"allow": 0, "block": 60, "challenge": 20, "total": 80}
        and report["totals"] == {"allow": 212, "block": 100, "challenge": 88})
    check("E7 per-class x per-action table exact", exact)

    # E8: false-positive split + challenge friction are the pinned values
    check("E8 FP rates split by class + challenge friction",
          report["fp_rate_legit_agent"] == 0.1833
          and report["fp_rate_human"] == 0.05
          and report["challenge_friction"] == 0.1167,
          f"fp_agent={report['fp_rate_legit_agent']} fp_human={report['fp_rate_human']} "
          f"friction={report['challenge_friction']}")

    # E9: velocity alone never punishes a valid attestation
    fast = [s for s in data["sessions"]
            if s["subgroup"] == "valid_fast_humanlike_timing"]
    check("E9 velocity-only valid agents still allowed",
          len(fast) == 4 and all(decide(s)["action"] == "allow" for s in fast))

    # E10: forged tokens block; scope mismatches challenge
    forged = [s for s in data["sessions"] if s["subgroup"] == "forged_token"]
    scoped = [s for s in data["sessions"] if s["subgroup"] == "scope_mismatch"]
    check("E10 forged -> block, scope mismatch -> challenge",
          all(decide(s)["action"] == "block" for s in forged)
          and all(decide(s)["action"] == "challenge" for s in scoped))

    # E11: POC gates pass via the CLI check path
    breaches, _ = check_dataset(data)
    check("E11 POC gates pass (check_dataset clean, CLI check exit 0)",
          breaches == [] and _run_cli(["check", "--input", FIXTURE]) == EXIT_OK)

    # E12: serve round-trip — /health ok and /report matches local report
    reset_state(data)
    server = make_server(0)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=10) as r:
            health_ok = json.loads(r.read())["status"] == "ok"
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/report", timeout=10) as r:
            served = json.loads(r.read())
        serve_ok = health_ok and served == report
    finally:
        server.shutdown(); server.server_close()
    check("E12 serve round-trip (/health, /report matches)", serve_ok)

    passed = sum(1 for r in RESULTS if r["passed"])
    out = {
        "results": RESULTS,
        "summary": {"passed": passed, "total": len(RESULTS)},
    }
    out_path = os.path.join(HERE, "eval_report.json")
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"evals: {passed}/{len(RESULTS)} passed -> {out_path}")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
