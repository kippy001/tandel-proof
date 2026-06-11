#!/usr/bin/env python3
"""Cryptographic integrity gate for toon-sha256-v1 rows.

stage1_load_validate.py checks the SHAPE of integrity fields (hex-64,
engine_version, canonicalization profile). It does NOT recompute the digest,
so "verified" has been a self-claim, not a checked fact. This gate closes that:
for every toon-sha256-v1 row it loads the archived TOON, recomputes toon_sha256,
and asserts it equals integrity.value -- AND asserts the TOON's @U-VCT field
order conforms to the frozen contract (canonical_line is the identity on it).

Exit 0 iff every v1 row verifies. v0 (illustrative) rows are skipped by design.
Run: python3 verify_integrity.py   (or pass a ledger path)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from stage1_load_validate import load_ledger, canonicalize_toon, toon_sha256, CANON_PREFIX  # noqa: E402
from uvct_toon import canonical_line  # noqa: E402

TOONS = HERE / "toons"


def _line_of(raw: bytes) -> str:
    """The canonical @U-VCT line: preimage minus domain prefix and trailing nl."""
    return canonicalize_toon(raw)[len(CANON_PREFIX):].decode("utf-8").rstrip("\n")


def verify(path: str) -> int:
    data = load_ledger(path)
    v1 = [r for r in data["rows"] if r["integrity"]["scheme"] == "toon-sha256-v1"]
    if not v1:
        print("INTEGRITY OK - no toon-sha256-v1 rows to verify (0 verified)")
        return 0

    checked = ok = 0
    fail = []
    for r in v1:
        rid = r["run_id"]
        stored = r["integrity"]["value"]
        toon = TOONS / f"{rid}.toon"
        checked += 1
        if not toon.exists():
            fail.append(f"{rid}: archived TOON missing ({toon.name})")
            continue
        raw = toon.read_bytes()
        got = toon_sha256(raw)                       # 1. recompute the digest
        if got != stored:
            fail.append(f"{rid}: digest mismatch\n      stored={stored}\n      recomp={got}")
            continue
        if canonical_line(_line_of(raw)) != _line_of(raw):   # 2. field-order conformance
            fail.append(f"{rid}: @U-VCT field order does not conform to frozen contract")
            continue
        ok += 1

    if fail:
        print(f"INTEGRITY FAILED - {len(fail)}/{checked} v1 row(s) bad:", file=sys.stderr)
        for f in fail:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"INTEGRITY OK - {ok}/{checked} toon-sha256-v1 row(s) verified "
          f"(digest recomputed + field order conforms)")
    return 0


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "ledger.json"
    raise SystemExit(verify(p))
