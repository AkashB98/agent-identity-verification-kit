"""Shared builders for the test suite (not a test module)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tokens import issue_token  # noqa: E402

NOW = 1_700_000_000


def make_session(subgroup="valid_normal", true_class="legitimate_agent",
                 principal="agent", token="__valid__", cv=0.2, vel=10.0,
                 challenge_outcome="pass", scopes=("browse", "checkout"),
                 exp=NOW + 3600, secret=None):
    """Build one session dict; token='__valid__' issues a real token."""
    if token == "__valid__":
        kwargs = {"secret": secret} if secret else {}
        token = issue_token("human-t", "agent-t", list(scopes), exp,
                            issued_at=NOW - 600, **kwargs)
    return {
        "action_count": 10,
        "agent_id": "agent-t" if principal == "agent" else None,
        "challenge_outcome": challenge_outcome,
        "human_id": "human-t",
        "now": NOW,
        "principal": principal,
        "required_scope": "checkout",
        "session_id": "s-test",
        "subgroup": subgroup,
        "timing_cv": cv,
        "token": token,
        "true_class": true_class,
        "velocity_per_min": vel,
    }
