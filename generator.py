"""Seeded synthetic agent-commerce traffic. Deterministic; fictional only.

Planted classes (400 sessions, fixed subgroup counts):

  verified_human      120  human principal, no agent token needed.
                           6 planted with machine-regular timing (autofill /
                           scripted assist) -> expected challenge.
  legitimate_agent    120  agent acting under a human's delegation token:
                             94 valid, normal behaviour        -> allow
                             10 EXPIRED attestation (pinned)   -> challenge
                              6 scope mismatch (browse only)   -> challenge
                              6 valid but burst behaviour      -> challenge
                              4 valid, high velocity, human-
                                like timing variance           -> allow
                                (velocity alone never punishes a
                                valid attestation)
  unattributed_agent   80  agent with NO attestation:
                             40 machine-regular                -> block
                             40 moderate timing                -> challenge
  bad_bot              80  no legitimate delegation:
                             30 forged token (bad signature)   -> block
                             30 missing, regular + very fast   -> block
                             20 missing, MIMICKING human timing
                                (pinned)                       -> challenge,
                                and the step-up outcome is "fail"

Every session carries `challenge_outcome`: the deterministic simulated
result IF the policy challenges it ("pass" for principals who can prove
a human, "fail" for bad bots).

All tokens are really issued via tokens.issue_token with the demo secret;
expired/forged variants are constructed, not faked flags.
"""

from __future__ import annotations

import json
import random
from typing import Dict, List

from tokens import DEMO_SECRET, issue_token

SEED = 42
NOW = 1_700_000_000
REQUIRED_SCOPE = "checkout"
CLASSES = ("verified_human", "legitimate_agent", "unattributed_agent", "bad_bot")


def _session(sid, true_class, subgroup, principal, token, cv, vel,
             action_count, challenge_outcome):
    return {
        "action_count": action_count,
        "agent_id": None if principal == "human" else f"agent-{sid}",
        "challenge_outcome": challenge_outcome,
        "human_id": f"human-{int(sid[2:]) % 60:03d}",
        "now": NOW,
        "principal": principal,
        "required_scope": REQUIRED_SCOPE,
        "session_id": sid,
        "subgroup": subgroup,
        "timing_cv": round(cv, 4),
        "token": token,
        "true_class": true_class,
        "velocity_per_min": round(vel, 2),
    }


def generate_dataset(seed: int = SEED) -> Dict:
    rng = random.Random(seed)
    sessions: List[Dict] = []
    n = 0

    def sid():
        nonlocal n
        n += 1
        return f"s-{n:04d}"

    # --- verified_human (120) ---
    for i in range(120):
        s = sid()
        if i % 20 == 0:  # 6 planted regular-timing humans
            sessions.append(_session(
                s, "verified_human", "regular_timing", "human", None,
                rng.uniform(0.06, 0.10), rng.uniform(4, 8),
                rng.randint(3, 10), "pass"))
        else:
            sessions.append(_session(
                s, "verified_human", "normal", "human", None,
                rng.uniform(0.35, 0.90), rng.uniform(2, 8),
                rng.randint(3, 10), "pass"))

    # --- legitimate_agent (120) ---
    for i in range(120):
        s = sid()
        hid = f"human-{int(s[2:]) % 60:03d}"
        if i < 94:
            tok = issue_token(hid, f"agent-{s}", ["browse", "checkout"],
                              NOW + 3600, issued_at=NOW - 600)
            sessions.append(_session(
                s, "legitimate_agent", "valid_normal", "agent", tok,
                rng.uniform(0.10, 0.30), rng.uniform(5, 15),
                rng.randint(4, 20), "pass"))
        elif i < 104:  # 10 expired (pinned hard case 1)
            tok = issue_token(hid, f"agent-{s}", ["browse", "checkout"],
                              NOW - 3600, issued_at=NOW - 7200)
            sessions.append(_session(
                s, "legitimate_agent", "expired_attestation", "agent", tok,
                rng.uniform(0.10, 0.30), rng.uniform(5, 15),
                rng.randint(4, 20), "pass"))
        elif i < 110:  # 6 scope mismatch
            tok = issue_token(hid, f"agent-{s}", ["browse"],
                              NOW + 3600, issued_at=NOW - 600)
            sessions.append(_session(
                s, "legitimate_agent", "scope_mismatch", "agent", tok,
                rng.uniform(0.10, 0.30), rng.uniform(5, 15),
                rng.randint(4, 20), "pass"))
        elif i < 116:  # 6 burst behaviour under a valid token
            tok = issue_token(hid, f"agent-{s}", ["browse", "checkout"],
                              NOW + 3600, issued_at=NOW - 600)
            sessions.append(_session(
                s, "legitimate_agent", "valid_burst", "agent", tok,
                rng.uniform(0.02, 0.04), rng.uniform(40, 55),
                rng.randint(30, 60), "pass"))
        else:  # 4 high velocity alone, human-like timing variance
            tok = issue_token(hid, f"agent-{s}", ["browse", "checkout"],
                              NOW + 3600, issued_at=NOW - 600)
            sessions.append(_session(
                s, "legitimate_agent", "valid_fast_humanlike_timing", "agent", tok,
                rng.uniform(0.20, 0.30), rng.uniform(35, 45),
                rng.randint(20, 40), "pass"))

    # --- unattributed_agent (80) ---
    for i in range(80):
        s = sid()
        if i < 40:
            sessions.append(_session(
                s, "unattributed_agent", "regular_timing", "agent", None,
                rng.uniform(0.08, 0.13), rng.uniform(8, 18),
                rng.randint(5, 25), "pass"))
        else:
            sessions.append(_session(
                s, "unattributed_agent", "moderate_timing", "agent", None,
                rng.uniform(0.28, 0.45), rng.uniform(6, 12),
                rng.randint(4, 15), "pass"))

    # --- bad_bot (80) ---
    for i in range(80):
        s = sid()
        hid = f"human-{int(s[2:]) % 60:03d}"
        if i < 30:  # forged: real format, wrong secret
            tok = issue_token(hid, f"agent-{s}", ["browse", "checkout"],
                              NOW + 3600, issued_at=NOW - 600,
                              secret="FORGED-WRONG-SECRET")
            sessions.append(_session(
                s, "bad_bot", "forged_token", "agent", tok,
                rng.uniform(0.05, 0.12), rng.uniform(20, 40),
                rng.randint(10, 40), "fail"))
        elif i < 60:  # missing, machine-regular, very fast
            sessions.append(_session(
                s, "bad_bot", "regular_fast", "agent", None,
                rng.uniform(0.03, 0.06), rng.uniform(45, 70),
                rng.randint(30, 80), "fail"))
        else:  # 20 mimicking human timing (pinned hard case 2)
            sessions.append(_session(
                s, "bad_bot", "mimics_human_timing", "agent", None,
                rng.uniform(0.40, 0.80), rng.uniform(3, 7),
                rng.randint(3, 10), "fail"))

    return {"now": NOW, "seed": seed, "session_count": len(sessions),
            "sessions": sessions}


def dataset_to_json(data: Dict) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"
