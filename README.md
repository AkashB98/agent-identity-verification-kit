# agent-identity-verification-kit

**Hiring signal:** I can build the "Know Your Human" layer for agentic commerce — the check that answers *who is this agent acting for, and may it do this?* before money moves. Agents are becoming buyers; every agent transaction needs a verifiable delegation from a human principal, not just a bot-or-not guess. This kit implements that delegation check for real, then measures what the policy costs legitimate traffic.

> JD backing: Sardine, Lead — Agentic Commerce (surfaced 2026-11-14): agent identity verification for agent-driven commerce.

## Core: attestation / delegation verification

`tokens.py` is real, testable logic — not a scoring table:

- `issue_token(human_id, agent_id, scopes, expiry)` issues a delegation token: a JSON payload (`human_id`, `agent_id`, sorted `scopes`, `iat`, `exp`), base64url-encoded and signed with **HMAC-SHA256** (Python stdlib only).
- `verify_token(token, required_scope, now)` returns one of five attestation states: `valid`, `expired` (signature ok, past `exp`), `invalid` (malformed or bad signature — forgery/tampering), `missing` (no token), `scope_mismatch` (valid token, required scope absent).

The signing secret is the obvious placeholder constant `DEMO_SECRET = "DEMO-SECRET-do-not-use-in-production"` — a demo key, not a credential. A production deployment would hold the key in a KMS/HSM, rotate it, and bind tokens to device/session signals this kit does not model.

## Policy engine (`policy.py`)

Sessions carry an attestation state plus two behaviour features: timing regularity (`timing_cv`, the coefficient of variation of inter-action gaps — low means machine-regular) and velocity (actions/minute, deliberately **one minor feature only**). Rules, in order:

| Rule | Condition | Action |
|---|---|---|
| R1 | attestation `invalid` | **block** — a forged delegation is refused, never stepped up |
| R2 | attestation `expired` | **challenge** — step-up is re-attestation by the human |
| R3 | attestation `scope_mismatch` | **challenge** — step-up is human scope approval |
| R4 | attestation `missing` (agent) | **block** if timing is machine-regular or velocity is very high; else **challenge** (step-up human proof) |
| R5 | attestation `valid` | **allow**, unless timing is machine-perfect *and* velocity is bursting → challenge |
| R6 | verified human | **allow**, unless timing is machine-regular → challenge |

Velocity alone never challenges or blocks a validly attested agent — it only matters combined with near-zero timing variance (R5) or a missing attestation (R4).

Two pinned hard cases are enforced by tests and evals:

1. **Legitimate agent, expired attestation** → challenge. Never silently allowed, never hard-blocked.
2. **Bad bot mimicking human timing** → challenge, and its simulated step-up outcome is `fail`. Human-like timing earns an unattributed agent nothing without attestation.

## Results — per class, per action (from the actual run)

There is deliberately **no single fraud-vs-false-positive curve**: one threshold number would hide exactly the trade-off a buyer of this system needs to see. On the seeded synthetic corpus (400 sessions):

| Class | Allow | Challenge | Block | Total |
|---|---:|---:|---:|---:|
| verified_human | 114 | 6 | 0 | 120 |
| legitimate_agent | 98 | 22 | 0 | 120 |
| unattributed_agent | 0 | 40 | 40 | 80 |
| bad_bot | 0 | 20 | 60 | 80 |
| **total** | **212** | **88** | **100** | **400** |

- **False-positive rate, legitimate agents** (challenged + blocked): **0.1833** — driven by the 10 expired attestations, 6 scope mismatches, and 6 burst-behaviour challenges; every one is a step-up the agent's human can pass, none is a hard refusal.
- **False-positive rate, verified humans:** **0.05** (6 of 120 planted with machine-regular timing, e.g. autofill/scripted assist).
- **Fraud caught** (bad_bot challenged + blocked): **1.0** — 0 of 80 bad bots allowed; the 20 timing-mimics are all caught at the step-up, which they fail.
- **Challenge friction** (share of legitimate traffic — humans + legitimate agents — challenged): **0.1167**. Of 88 challenges issued, 68 pass step-up and 20 fail — and every failure is a bad bot.

## POC framing

- **Success criteria:** zero bad bots allowed; every expired attestation challenged (never allowed); legitimate-agent allow rate ≥ 0.75; verified-human allow rate ≥ 0.90; fraud caught ≥ 0.95.
- **Thresholds:** `REGULAR_CV = 0.15`, `PERFECT_CV = 0.05`, `HIGH_VELOCITY = 30` actions/min (in `policy.py`); POC gates in `cli.py` (`GATE_*` constants).
- **Gate they feed:** `python3 cli.py check --input fixtures/sample_sessions.json` exits 0 only if all criteria hold (1 = breach, 2 = usage/data error) — the CI gate a pilot would run before widening agent traffic, and the same numbers a merchant would review weekly during a proof-of-concept.

## Quick start

```bash
python3 cli.py generate --out fixtures/sample_sessions.json   # seeded synthetic sessions
python3 cli.py report --input fixtures/sample_sessions.json   # per-class x per-action (md; --format json)
python3 cli.py check --input fixtures/sample_sessions.json    # POC gates; exit 0 = pass
python3 demo.py                                               # full path incl. serve round-trip, exit 0
python3 evals/run_evals.py                                    # 12 golden evals -> evals/eval_report.json
python3 -m unittest discover -s tests                         # 53 tests
python3 cli.py serve --port 8765                              # GET /report, GET /health on 127.0.0.1
```

## Synthetic corpus (`generator.py`, seed 42)

400 fictional sessions with planted subgroups: verified humans (120, 6 with regular timing), legitimate agents (120: 94 valid, 10 expired, 6 scope-mismatch, 6 burst, 4 fast-but-varied-timing), unattributed agents (80: 40 machine-regular, 40 moderate), bad bots (80: 30 forged tokens signed with a wrong secret, 30 regular-and-fast, 20 mimicking human timing). Tokens in the corpus are really issued and verified — expired and forged variants are constructed through the token module, not faked flags. Each session's `challenge_outcome` is the deterministic simulated step-up result (`pass` for principals who can prove a human, `fail` for bad bots). Generation is deterministic: the committed fixture is byte-identical to generator output, asserted by the evals.

## Honest limits

- This is **not real identity verification**: no biometrics, no document checks, no device attestation, no real KYC. It models the signals + policy layer only.
- The challenge is a simulated outcome field, not a real step-up flow (no WebAuthn, no OTP, no liveness).
- Behaviour features are two summary statistics on synthetic data; real traffic would need per-principal baselines, and timing mimicry in the wild is far more sophisticated than a planted CV band.
- The HMAC secret is a single shared demo placeholder; production delegation needs asymmetric signatures or a token service, key rotation, revocation, and replay protection (nonce/`jti`), none of which are modelled here.
- All principals, agents, and sessions are fictional; no personal data is used anywhere.

## Dev-loop honesty note

One real bug was hit and fixed during the build: the session builder derived `human_id` by applying `% 60` to the string session id (`"s-0001" % 60`), which raises `TypeError` on the first generated session — the generator crashed before any test ran. Fixed by parsing the numeric suffix (`int(sid[2:]) % 60`), and generator tests now cover the full 400-session build. Separately, the author's initial hand-count of total challenges (108) was wrong — the true total is 88 — so the pinned expectations in the report tests and evals were corrected to the actual run rather than the other way around.

## License

MIT — see `LICENSE`. Copyright Akash Bhargava.
