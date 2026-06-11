#!/usr/bin/env python3
"""Stage 1 - ledger loader / validator for the U-VCT Scorecard subsystem.

Single source of truth is ledger.json. This module loads it, enforces the
governance contract (one row per run_id, append-only-friendly invariants,
state-dependent required fields, integrity-scheme rules), and exposes the
canonical TOON hashing functions for enhancement #5.

stdlib only - no scipy/hmmlearn/arch/jsonschema. Fail-loud by design: a bad
ledger should raise, never silently produce a wrong scorecard.

Usage:
    python3 stage1_load_validate.py [ledger.json]      # validate, print summary
    from stage1_load_validate import load_ledger, validate_ledger, toon_sha256
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date

RUN_ID_RE = re.compile(r"^RUN-(\d{8})-([A-Z0-9.]{1,8})-([0-9a-z_]{8})$")
COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")
ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

TIERS = {"T1", "T2", "T3", "T4", "T5"}
STATES = {"open", "closed"}
RESULTS = {"win", "loss", "avoided"}
SCHEMES = {"illustrative-snapshot-v0", "toon-sha256-v1"}

CANON_PROFILE = "uvct-toon-v1"
CANON_PREFIX = b"uvct-toon-v1\n"


# --------------------------------------------------------------------------
# Canonical TOON hashing (reference impl for enhancement #5). See CANONICALIZATION.md
# --------------------------------------------------------------------------
def canonicalize_toon(raw: bytes) -> bytes:
    """Return the canonical preimage bytes for a raw TOON archive.

    Steps (uvct-toon-v1): strict UTF-8 decode, strip BOM, CRLF/CR -> LF,
    strip trailing whitespace per line, collapse to a single terminating
    newline, prepend the domain-separation prefix, re-encode UTF-8.
    """
    text = raw.decode("utf-8")            # strict: raises on invalid bytes
    if text and text[0] == "\ufeff":
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip(" \t") for ln in text.split("\n")]
    body = "\n".join(lines).rstrip("\n") + "\n"
    return CANON_PREFIX + body.encode("utf-8")


def toon_sha256(raw: bytes) -> str:
    """Lowercase hex SHA-256 over the canonical TOON preimage."""
    return hashlib.sha256(canonicalize_toon(raw)).hexdigest()


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
def load_ledger(path: str = "ledger.json") -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("ledger root must be a JSON object")
    if data.get("_version") != "ledger-v1":
        raise ValueError(f"unsupported ledger _version: {data.get('_version')!r}")
    if not isinstance(data.get("rows"), list):
        raise ValueError("ledger.rows must be an array")
    return data


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def _parse_iso(value: str):
    m = ISO_DATE_RE.match(value)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _validate_integrity(integ, where, errors):
    if not isinstance(integ, dict):
        errors.append(f"{where}: integrity must be an object")
        return
    scheme = integ.get("scheme")
    value = integ.get("value")
    if scheme not in SCHEMES:
        errors.append(f"{where}: integrity.scheme {scheme!r} not in {sorted(SCHEMES)}")
    if not isinstance(value, str) or not value:
        errors.append(f"{where}: integrity.value must be a non-empty string")
        return
    if scheme == "toon-sha256-v1":
        if not HEX64_RE.match(value):
            errors.append(f"{where}: toon-sha256-v1 value must be 64-char lowercase hex")
        if not integ.get("engine_version"):
            errors.append(f"{where}: toon-sha256-v1 requires non-null engine_version")
        if integ.get("canonicalization") != CANON_PROFILE:
            errors.append(f"{where}: toon-sha256-v1 requires canonicalization == {CANON_PROFILE!r}")
    # v0: value is opaque (legacy hash or seed placeholder) - no hex check.
    # No run_id[:8] == value[:8] coupling is enforced, by design.


def _validate_signals(sig, where, errors):
    if sig is None:
        return
    if not isinstance(sig, dict):
        errors.append(f"{where}: signals must be an object")
        return
    fr = sig.get("forced_roll_probability")
    if fr is not None and not (isinstance(fr, (int, float)) and 0 <= fr <= 1):
        errors.append(f"{where}: signals.forced_roll_probability must be in [0,1]")
    sm = sig.get("sizing_multiplier")
    if sm is not None and not (isinstance(sm, (int, float)) and sm >= 0):
        errors.append(f"{where}: signals.sizing_multiplier must be >= 0")


def validate_ledger(data: dict) -> list[str]:
    """Return a list of human-readable governance errors. Empty list == valid."""
    errors: list[str] = []
    seen_run_ids: set[str] = set()

    for i, row in enumerate(data.get("rows", [])):
        where = f"row[{i}]"
        if not isinstance(row, dict):
            errors.append(f"{where}: not an object")
            continue

        run_id = row.get("run_id")
        where = f"row[{i}] {run_id!r}"

        # run_id identity + uniqueness (append-only: no dupes)
        if not isinstance(run_id, str) or not RUN_ID_RE.match(run_id or ""):
            errors.append(f"{where}: run_id missing or malformed (RUN-YYYYMMDD-TICKER-xxxxxxxx)")
        elif run_id in seen_run_ids:
            errors.append(f"{where}: duplicate run_id (ledger is append-only, one row per run)")
        else:
            seen_run_ids.add(run_id)

        # required common fields
        for f in ("ticker", "structure"):
            if not isinstance(row.get(f), str) or not row[f]:
                errors.append(f"{where}: {f} must be a non-empty string")
        if row.get("tier") not in TIERS:
            errors.append(f"{where}: tier {row.get('tier')!r} not in {sorted(TIERS)}")
        if not COMMIT_RE.match(str(row.get("commit", ""))):
            errors.append(f"{where}: commit must be a 7-40 char lowercase hex sha")

        opened = row.get("opened")
        d_open = _parse_iso(opened) if isinstance(opened, str) else None
        if d_open is None:
            errors.append(f"{where}: opened must be a valid ISO date (YYYY-MM-DD)")

        state = row.get("state")
        if state not in STATES:
            errors.append(f"{where}: state {state!r} not in {sorted(STATES)}")

        # state-dependent governance
        if state == "open":
            if not row.get("status"):
                errors.append(f"{where}: open rows require a 'status' (e.g. 'live')")
            for forbidden in ("closed", "result", "pl"):
                if forbidden in row:
                    errors.append(f"{where}: open rows must not carry '{forbidden}'")

        elif state == "closed":
            if "status" in row:
                errors.append(f"{where}: closed rows must not carry 'status'")
            result = row.get("result")
            if result not in RESULTS:
                errors.append(f"{where}: closed rows require result in {sorted(RESULTS)}")
            if not isinstance(row.get("entry_edge_pt"), (int, float)):
                errors.append(f"{where}: closed rows require numeric entry_edge_pt")

            if result in ("win", "loss"):
                closed = row.get("closed")
                d_close = _parse_iso(closed) if isinstance(closed, str) else None
                if d_close is None:
                    errors.append(f"{where}: {result} rows require a valid ISO 'closed' date")
                elif d_open and d_close < d_open:
                    errors.append(f"{where}: closed date precedes opened date")
                if not isinstance(row.get("pl"), (int, float)):
                    errors.append(f"{where}: {result} rows require numeric 'pl'")
            elif result == "avoided":
                if "closed" in row:
                    errors.append(f"{where}: avoided rows carry no 'closed' date (render shows a dash)")
                if row.get("pl") is not None:
                    errors.append(f"{where}: avoided rows require pl == null (no trade taken)")

        _validate_integrity(row.get("integrity"), where, errors)
        _validate_signals(row.get("signals"), where, errors)

    return errors


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _summary(data: dict) -> str:
    rows = data["rows"]
    closed = [r for r in rows if r.get("state") == "closed"]
    open_ = [r for r in rows if r.get("state") == "open"]
    scored = [r for r in closed if r.get("result") in ("win", "loss")]
    wins = [r for r in scored if r["result"] == "win"]
    avoided = [r for r in closed if r.get("result") == "avoided"]
    v1 = [r for r in rows if r["integrity"]["scheme"] == "toon-sha256-v1"]
    v0 = [r for r in rows if r["integrity"]["scheme"] == "illustrative-snapshot-v0"]
    return (
        f"rows={len(rows)}  open={len(open_)}  closed={len(closed)}  "
        f"scored={len(scored)}  avoided={len(avoided)}\n"
        f"record={len(wins)}-{len(scored)-len(wins)}  "
        f"hit_rate={round(100*len(wins)/len(scored)) if scored else 0}%  "
        f"net_edge={sum(r['pl'] for r in scored):+d}\n"
        f"integrity: {len(v0)} illustrative / {len(v1)} verified"
    )


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else "ledger.json"
    try:
        data = load_ledger(path)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"LOAD FAILED: {e}", file=sys.stderr)
        return 2
    errors = validate_ledger(data)
    if errors:
        print(f"INVALID ({len(errors)} error(s)):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("VALID")
    print(_summary(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
