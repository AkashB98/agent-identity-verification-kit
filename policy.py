"""Policy engine: (session, attestation) -> allow / challenge / block.

Stated rules (evaluated in order; first match wins):

  R1  attestation invalid (bad signature / malformed)      -> block
        A forged delegation is never stepped up; it is refused.
  R2  attestation expired                                  -> challenge
        Step-up = re-attestation by the human principal. A legitimate
        agent whose attestation lapsed is challenged, never silently
        allowed and never hard-blocked. (Pinned hard case 1.)
  R3  attestation scope_mismatch                           -> challenge
        Step-up = human approves the wider scope.
  R4  attestation missing, principal is an agent:
        machine-regular timing OR very high velocity       -> block
        otherwise                                          -> challenge
        An unattributed agent that also looks human is still never
        allowed outright — it must pass step-up human proof, which a
        bad bot fails. (Pinned hard case 2: a bad bot mimicking human
        timing lands here and is challenged, not allowed.)
  R5  attestation valid:
        machine-perfect timing AND burst velocity          -> challenge
        otherwise                                          -> allow
        Velocity alone never challenges or blocks a validly attested
        agent: it is one minor feature, only meaningful combined with
        near-zero timing variance.
  R6  human_verified principal:
        machine-regular timing                             -> challenge
        otherwise                                          -> allow

Behaviour features: timing_cv = coefficient of variation of inter-action
gaps (low = machine-regular), velocity_per_min = actions per minute.
Thresholds: REGULAR_CV, PERFECT_CV, HIGH_VELOCITY below.
"""

from __future__ import annotations

from typing import Dict

from tokens import verify_token

REGULAR_CV = 0.15        # below this, timing is machine-regular
PERFECT_CV = 0.05        # below this, timing is machine-perfect
HIGH_VELOCITY = 30.0     # actions per minute

ACTIONS = ("allow", "challenge", "block")


def attestation_state(session: Dict) -> str:
    """Resolve a session's attestation state via real token verification."""
    if session.get("principal") == "human":
        return "human_verified"
    return verify_token(session.get("token"),
                        required_scope=session.get("required_scope"),
                        now=session.get("now", 0))["status"]


def decide(session: Dict) -> Dict:
    """Return {"action", "attestation_state", "reason", "challenge_outcome"}.

    challenge_outcome is the simulated step-up result when the action is
    "challenge" (the session's planted would-be outcome), else None.
    """
    state = attestation_state(session)
    cv = float(session["timing_cv"])
    vel = float(session["velocity_per_min"])

    if state == "invalid":
        action, reason = "block", "R1 invalid attestation (bad signature)"
    elif state == "expired":
        action, reason = "challenge", "R2 expired attestation: re-attestation step-up"
    elif state == "scope_mismatch":
        action, reason = "challenge", "R3 scope mismatch: human scope approval step-up"
    elif state == "missing":
        if cv < REGULAR_CV or vel > HIGH_VELOCITY:
            action, reason = "block", "R4 unattributed agent, machine-like behaviour"
        else:
            action, reason = "challenge", "R4 unattributed agent: step-up human proof"
    elif state == "valid":
        if cv < PERFECT_CV and vel > HIGH_VELOCITY:
            action, reason = "challenge", "R5 valid attestation but burst behaviour"
        else:
            action, reason = "allow", "R5 valid attestation"
    elif state == "human_verified":
        if cv < REGULAR_CV:
            action, reason = "challenge", "R6 verified human, machine-regular timing"
        else:
            action, reason = "allow", "R6 verified human"
    else:  # pragma: no cover - states are closed
        raise ValueError(f"unknown attestation state: {state}")

    return {
        "action": action,
        "attestation_state": state,
        "challenge_outcome": session.get("challenge_outcome") if action == "challenge" else None,
        "reason": reason,
        "session_id": session["session_id"],
        "true_class": session["true_class"],
    }


def decide_all(sessions):
    return [decide(s) for s in sessions]
