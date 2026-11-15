"""CLI: generate | report | check | demo | serve.

SYNTHETIC DATA ONLY — every principal, agent and session is fictional.
This kit models signals + policy for agent identity verification; it is
NOT real identity verification and performs no biometrics.

Exit codes: check 0 = pass, 1 = quality breach, 2 = usage/IO error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from generator import dataset_to_json, generate_dataset  # noqa: E402
from policy import decide_all  # noqa: E402
from report import build_markdown_report, build_report  # noqa: E402
from validation import validate_dataset  # noqa: E402

EXIT_OK, EXIT_FAIL, EXIT_ERROR = 0, 1, 2

# POC gates (see README "POC framing").
GATE_MAX_BAD_BOT_ALLOW = 0          # no bad bot may be allowed, ever
GATE_MIN_LEGIT_AGENT_ALLOW = 0.75   # share of legitimate agents allowed outright
GATE_MIN_HUMAN_ALLOW = 0.90         # share of verified humans allowed outright
GATE_MIN_FRAUD_CAUGHT = 0.95        # share of bad bots challenged or blocked


def canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True)


def load_dataset(path: str) -> Dict:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("dataset file must contain a JSON object")
    return data


def _load_or_error(path: str) -> Optional[Dict]:
    try:
        return load_dataset(path)
    except FileNotFoundError:
        print(f"error: file not found: {path}", file=sys.stderr)
    except (ValueError, OSError) as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
    return None


def _validated(args):
    data = _load_or_error(args.input)
    if data is None:
        return None, EXIT_ERROR
    issues = validate_dataset(data)
    if issues:
        for issue in issues[:20]:
            print(f"data-quality: {issue}", file=sys.stderr)
        return None, EXIT_ERROR
    return data, EXIT_OK


def _write_out(args, text: str, summary: str) -> int:
    if getattr(args, "out", None):
        try:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            print(f"error: cannot write {args.out}: {exc}", file=sys.stderr)
            return EXIT_ERROR
        print(summary)
    else:
        print(text, end="")
    return EXIT_OK


def cmd_generate(args) -> int:
    data = generate_dataset(seed=args.seed)
    return _write_out(args, dataset_to_json(data),
                      f"generated synthetic sessions: {data['session_count']} "
                      f"(seed={args.seed}) -> {args.out}")


def cmd_report(args) -> int:
    data, code = _validated(args)
    if data is None:
        return code
    if args.format == "json":
        return _write_out(args, canonical(build_report(data)) + "\n",
                          f"report -> {args.out}")
    return _write_out(args, build_markdown_report(data),
                      f"report -> {args.out}")


def check_dataset(data: Dict):
    """Return (breaches, report). Empty breaches = POC gates pass."""
    report = build_report(data)
    decisions = decide_all(data["sessions"])
    pc = report["per_class"]
    breaches = []
    if pc["bad_bot"]["allow"] > GATE_MAX_BAD_BOT_ALLOW:
        breaches.append(f"bad_bot allowed {pc['bad_bot']['allow']} sessions "
                        f"(gate: {GATE_MAX_BAD_BOT_ALLOW})")
    legit_allow = pc["legitimate_agent"]["allow"] / max(pc["legitimate_agent"]["total"], 1)
    if legit_allow < GATE_MIN_LEGIT_AGENT_ALLOW:
        breaches.append(f"legitimate_agent allow rate {round(legit_allow, 4)} "
                        f"< {GATE_MIN_LEGIT_AGENT_ALLOW}")
    human_allow = pc["verified_human"]["allow"] / max(pc["verified_human"]["total"], 1)
    if human_allow < GATE_MIN_HUMAN_ALLOW:
        breaches.append(f"verified_human allow rate {round(human_allow, 4)} "
                        f"< {GATE_MIN_HUMAN_ALLOW}")
    if report["fraud_caught_rate"] < GATE_MIN_FRAUD_CAUGHT:
        breaches.append(f"fraud_caught_rate {report['fraud_caught_rate']} "
                        f"< {GATE_MIN_FRAUD_CAUGHT}")
    for d in decisions:
        if d["attestation_state"] == "expired" and d["action"] == "allow":
            breaches.append(f"{d['session_id']}: expired attestation was allowed")
    mimics = [s for s in data["sessions"] if s["subgroup"] == "mimics_human_timing"]
    for s in mimics:
        d = next(x for x in decisions if x["session_id"] == s["session_id"])
        if d["action"] == "allow":
            breaches.append(f"{s['session_id']}: human-timing-mimicking bot was allowed")
    return breaches, report


def cmd_check(args) -> int:
    data = _load_or_error(args.input)
    if data is None:
        return EXIT_ERROR
    issues = validate_dataset(data)
    if issues:
        for issue in issues[:20]:
            print(f"data-quality: {issue}")
        print(f"check FAIL (data quality): {len(issues)} issue(s)")
        return EXIT_ERROR
    breaches, report = check_dataset(data)
    pc = report["per_class"]
    print(f"sessions={report['sessions_total']} "
          f"allow={report['totals']['allow']} challenge={report['totals']['challenge']} "
          f"block={report['totals']['block']}")
    for cls in sorted(pc):
        c = pc[cls]
        print(f"  {cls}: allow={c['allow']} challenge={c['challenge']} "
              f"block={c['block']} total={c['total']}")
    print(f"  fp_legit_agent={report['fp_rate_legit_agent']} "
          f"fp_human={report['fp_rate_human']} "
          f"fraud_caught={report['fraud_caught_rate']} "
          f"challenge_friction={report['challenge_friction']}")
    if breaches:
        for b in breaches:
            print(f"check FAIL: {b}")
        return EXIT_FAIL
    print("check PASS")
    return EXIT_OK


def cmd_demo(args) -> int:
    import demo as demo_mod
    try:
        demo_mod.main()
    except AssertionError as exc:
        print(f"demo FAILED: {exc}", file=sys.stderr)
        return EXIT_FAIL
    return EXIT_OK


# ------------------------------------------------------------------- serve

class _State:
    def __init__(self):
        self.data: Dict = generate_dataset()


_STATE = _State()


def get_state() -> _State:
    return _STATE


def reset_state(data: Optional[Dict] = None) -> None:
    _STATE.data = data if data is not None else generate_dataset()


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, payload: Any) -> None:
        self._send(code, (canonical(payload) + "\n").encode(), "application/json")

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            return self._send_json(200, {"status": "ok"})
        if self.path == "/report":
            return self._send_json(200, build_report(_STATE.data))
        return self._send_json(404, {"error": "unknown endpoint"})

    def log_message(self, *a: Any) -> None:
        pass


def make_server(port: int) -> HTTPServer:
    return HTTPServer(("127.0.0.1", port), _Handler)


def cmd_serve(args) -> int:
    if args.input:
        data = _load_or_error(args.input)
        if data is None:
            return EXIT_ERROR
        reset_state(data)
    server = make_server(args.port)
    print(f"serving on http://127.0.0.1:{args.port}  (GET /report, GET /health)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent-identity-verification-kit",
        description="Agent identity verification: HMAC attestation tokens "
                    "bound to a human principal, plus a policy engine over "
                    "synthetic agent-commerce sessions.")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="generate the synthetic session dataset")
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--out", default=None)
    g.set_defaults(func=cmd_generate)

    r = sub.add_parser("report", help="per-class x per-action report")
    r.add_argument("--input", required=True)
    r.add_argument("--format", choices=("md", "json"), default="md")
    r.add_argument("--out", default=None)
    r.set_defaults(func=cmd_report)

    c = sub.add_parser("check", help="CI gate: exit 0 pass / 1 breach / 2 error")
    c.add_argument("--input", required=True)
    c.set_defaults(func=cmd_check)

    sub.add_parser("demo", help="run the end-to-end demo").set_defaults(func=cmd_demo)

    s = sub.add_parser("serve", help="localhost report API")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--input", default=None)
    s.set_defaults(func=cmd_serve)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
