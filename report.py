"""Per-class x per-action reporting. No single headline threshold curve.

Per Claude cross-check (AGREE-WITH-CUTS): results are reported PER CLASS
and PER ACTION — allow / challenge / block counts, false-positive rates
split by legitimate-agent and by human, fraud (bad_bot) caught rate, and
challenge friction as its own cost on legitimate traffic.
"""

from __future__ import annotations

from typing import Dict

from generator import CLASSES
from policy import ACTIONS, decide_all

LEGIT_CLASSES = ("verified_human", "legitimate_agent")


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def build_report(data: Dict) -> Dict:
    decisions = decide_all(data["sessions"])
    per_class = {}
    for cls in CLASSES:
        rows = [d for d in decisions if d["true_class"] == cls]
        counts = {a: sum(1 for d in rows if d["action"] == a) for a in ACTIONS}
        per_class[cls] = {**counts, "total": len(rows)}

    legit_agent = per_class["legitimate_agent"]
    human = per_class["verified_human"]
    bad = per_class["bad_bot"]
    legit_total = sum(per_class[c]["total"] for c in LEGIT_CLASSES)
    legit_challenged = sum(per_class[c]["challenge"] for c in LEGIT_CLASSES)
    challenged = [d for d in decisions if d["action"] == "challenge"]
    challenge_failed = sum(1 for d in challenged if d["challenge_outcome"] == "fail")

    report = {
        "challenge_friction": _rate(legit_challenged, legit_total),
        "challenge_outcomes": {
            "challenged_total": len(challenged),
            "failed": challenge_failed,
            "passed": len(challenged) - challenge_failed,
        },
        "fp_rate_human": _rate(human["challenge"] + human["block"], human["total"]),
        "fp_rate_legit_agent": _rate(
            legit_agent["challenge"] + legit_agent["block"], legit_agent["total"]),
        "fraud_caught_rate": _rate(bad["challenge"] + bad["block"], bad["total"]),
        "per_class": per_class,
        "sessions_total": len(decisions),
        "totals": {a: sum(per_class[c][a] for c in CLASSES) for a in ACTIONS},
    }
    return report


def build_markdown_report(data: Dict) -> str:
    r = build_report(data)
    lines = [
        "# Agent identity verification — per-class x per-action report",
        "",
        f"Sessions: {r['sessions_total']} (synthetic, seeded)",
        "",
        "| Class | Allow | Challenge | Block | Total |",
        "|---|---:|---:|---:|---:|",
    ]
    for cls in CLASSES:
        c = r["per_class"][cls]
        lines.append(f"| {cls} | {c['allow']} | {c['challenge']} | {c['block']} | {c['total']} |")
    t = r["totals"]
    lines += [
        f"| **total** | **{t['allow']}** | **{t['challenge']}** | **{t['block']}** | **{r['sessions_total']}** |",
        "",
        f"- False-positive rate, legitimate agents (challenged+blocked): {r['fp_rate_legit_agent']}",
        f"- False-positive rate, verified humans (challenged+blocked): {r['fp_rate_human']}",
        f"- Fraud caught (bad_bot challenged+blocked): {r['fraud_caught_rate']}",
        f"- Challenge friction (share of legitimate traffic challenged): {r['challenge_friction']}",
        f"- Challenges: {r['challenge_outcomes']['challenged_total']} issued, "
        f"{r['challenge_outcomes']['passed']} passed step-up, "
        f"{r['challenge_outcomes']['failed']} failed step-up",
        "",
    ]
    return "\n".join(lines)
