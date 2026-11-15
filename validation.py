"""Dataset validation: structural checks on a generated dataset dict."""

from __future__ import annotations

from typing import Dict, List

from generator import CLASSES

REQUIRED_FIELDS = {
    "action_count": int,
    "challenge_outcome": str,
    "now": int,
    "principal": str,
    "required_scope": str,
    "session_id": str,
    "subgroup": str,
    "timing_cv": (int, float),
    "true_class": str,
    "velocity_per_min": (int, float),
}


def validate_dataset(data: Dict) -> List[str]:
    issues: List[str] = []
    if not isinstance(data, dict):
        return ["dataset must be a JSON object"]
    sessions = data.get("sessions")
    if not isinstance(sessions, list) or not sessions:
        return ["dataset.sessions must be a non-empty list"]
    if data.get("session_count") != len(sessions):
        issues.append("session_count does not match len(sessions)")
    seen = set()
    for s in sessions:
        sid = s.get("session_id", "?")
        if sid in seen:
            issues.append(f"duplicate session_id: {sid}")
        seen.add(sid)
        for field, types in REQUIRED_FIELDS.items():
            if field not in s:
                issues.append(f"{sid}: missing field {field}")
            elif not isinstance(s[field], types):
                issues.append(f"{sid}: field {field} has wrong type")
        if s.get("true_class") not in CLASSES:
            issues.append(f"{sid}: unknown true_class {s.get('true_class')}")
        if s.get("challenge_outcome") not in ("pass", "fail"):
            issues.append(f"{sid}: challenge_outcome must be pass|fail")
        if s.get("principal") not in ("human", "agent"):
            issues.append(f"{sid}: principal must be human|agent")
        if not (0 <= float(s.get("timing_cv", -1)) <= 2):
            issues.append(f"{sid}: timing_cv out of range")
        if float(s.get("velocity_per_min", -1)) < 0:
            issues.append(f"{sid}: velocity_per_min negative")
    return issues
