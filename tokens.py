"""Agent attestation tokens: HMAC-signed delegation from a human principal.

A token says: "human <human_id> delegates to agent <agent_id> the right to
act with <scopes> until <exp>". The signature is HMAC-SHA256 over the
base64url-encoded payload, keyed with DEMO_SECRET.

DEMO_SECRET is an obvious placeholder constant for this offline demo kit.
It is NOT a real credential and must never be used in production — a real
deployment would hold the signing key in a KMS/HSM and rotate it.

Token format:  <base64url(payload_json)>.<hmac_hex>
Payload JSON (sorted keys): {"agent_id", "exp", "human_id", "iat", "scopes"}

verify_token returns one of five attestation states:
  valid           signature ok, not expired, required scope present
  expired         signature ok, but now > exp
  invalid         malformed token or signature mismatch (forgery / tamper)
  missing         no token presented at all
  scope_mismatch  signature ok, not expired, required scope absent
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Dict, List, Optional

DEMO_SECRET = "DEMO-SECRET-do-not-use-in-production"

STATES = ("valid", "expired", "invalid", "missing", "scope_mismatch")


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _sign(payload_b64: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"),
                    hashlib.sha256).hexdigest()


def issue_token(human_id: str, agent_id: str, scopes: List[str],
                expiry: int, issued_at: int = 0,
                secret: str = DEMO_SECRET) -> str:
    """Issue a signed delegation token. `expiry`/`issued_at` are epoch seconds."""
    payload = {
        "agent_id": agent_id,
        "exp": int(expiry),
        "human_id": human_id,
        "iat": int(issued_at),
        "scopes": sorted(scopes),
    }
    payload_b64 = _b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return payload_b64 + "." + _sign(payload_b64, secret)


def verify_token(token: Optional[str], required_scope: Optional[str] = None,
                 now: int = 0, secret: str = DEMO_SECRET) -> Dict:
    """Verify a token. Returns {"status": <state>, ...payload fields when known}."""
    if token is None or token == "":
        return {"status": "missing"}
    if not isinstance(token, str) or "." not in token:
        return {"status": "invalid"}
    payload_b64, _, sig = token.rpartition(".")
    if not payload_b64 or not sig:
        return {"status": "invalid"}
    expected = _sign(payload_b64, secret)
    if not hmac.compare_digest(expected, sig):
        return {"status": "invalid"}
    try:
        payload = json.loads(_b64decode(payload_b64).decode("utf-8"))
    except Exception:
        return {"status": "invalid"}
    if not isinstance(payload, dict) or "exp" not in payload:
        return {"status": "invalid"}
    result = {
        "agent_id": payload.get("agent_id"),
        "human_id": payload.get("human_id"),
        "scopes": payload.get("scopes", []),
    }
    if int(now) > int(payload["exp"]):
        result["status"] = "expired"
        return result
    if required_scope is not None and required_scope not in result["scopes"]:
        result["status"] = "scope_mismatch"
        return result
    result["status"] = "valid"
    return result
