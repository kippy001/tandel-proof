#!/usr/bin/env python3
"""run_gates.py - run every ledger/ verification gate in one shot.

This is the authoritative pre-commit check. It runs all gates as
subprocesses and exits non-zero if ANY fails, so it can be used directly in a
commit hook or CI step:

    python3 run_gates.py && git commit ...

The byte-identity gates (verify_roundtrip, stage3 seed render) double as the CRLF
check: if .gitattributes drifts and frozen bytes pick up CRLF, those gates fail
here before anything is committed. Runs from any cwd (module-anchored); each
gate runs with cwd=ledger/ so the scripts' relative defaults resolve.

Path B (enhancement #5): the "generator-correctness" gates are pinned to the
frozen 13-row SEED FIXTURE, so they keep proving "the generator reproduces the
signed-off design" forever. The "live-ledger" gates run against the growing
ledger.json (validate + a render smoke check, NOT byte-identity). This lets
verified rows be appended and committed without re-freezing the Scorecard each
time -- exactly the weekly workflow the stage3 docstring describes.

stdlib only.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent

# Frozen 13-row seed snapshot. NEVER changes: it is the regression target the
# generator must keep reproducing (and what canonical_source.html was frozen
# from). Created once by copying the seed-state ledger.json into the fixture.
SEED_FIXTURE = "tests/fixtures/ledger_seed13.json"

# (label, argv, success_substring-in-stdout-or-None). A gate passes iff its
# return code is 0 AND, when given, the success marker appears in its output.
GATES = [
    # --- generator-correctness regression (pinned to the seed fixture) ------
    ("stage0 tests",       ["tests/test_stage0.py"],                  "10 passed, 0 failed"),
    ("stage2 reconcile",   ["stage2_derive.py", SEED_FIXTURE],        "RECONCILE OK"),
    ("verify_roundtrip",   ["verify_roundtrip.py"],                   "ROUND-TRIP LOSSLESS"),
    ("stage3 seed render", ["stage3_render.py", SEED_FIXTURE],        "STAGE 3 LOSSLESS"),
    ("stage3 tests",       ["tests/test_stage3.py"],                  "30 passed, 0 failed"),
    ("canon tests",        ["tests/test_canonicalize_toon.py"],       "9 passed, 0 failed"),
    ("toon serializer",    ["tests/test_uvct_toon_serializer.py"],    "8 passed, 0 failed"),
    # --- live-ledger soundness (runs against the growing ledger.json) -------
    # stage1 validates schema/structure/integrity of the LIVE ledger.
    ("stage1 validate",    ["stage1_load_validate.py"],               "VALID"),
    ("integrity verify",   ["verify_integrity.py"],                   "INTEGRITY OK"),
    # stage3 live render proves the LIVE ledger actually renders (all tokens
    # fill, no unknown tier/result). A non-frozen --build-meta means byte-
    # identity is NOT asserted; rc==0 iff the render succeeds (marker=None).
    ("stage3 live render", ["stage3_render.py", "ledger.json",
                            "--build-meta", "live-smoke"],            None),
    # §23.82: the PUBLIC page is the verified-only render; prove it renders too.
    ("stage3 public render", ["stage3_render.py", "ledger.json", "--verified-only",
                              "--build-meta", "live-smoke"],          None),
]


def run_one(argv: list[str], marker: str | None) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, *argv],
        cwd=HERE, capture_output=True, text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    rc_ok = proc.returncode == 0
    marker_ok = (marker is None) or (marker in out)
    ok = rc_ok and marker_ok
    # last non-empty line, for a compact one-line status
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    detail = lines[-1] if lines else f"(no output, rc={proc.returncode})"
    if not rc_ok:
        detail = f"rc={proc.returncode} :: {detail}"
    return ok, detail


def main() -> int:
    print(f"Running {len(GATES)} gates in {HERE}\n")
    width = max(len(label) for label, _, _ in GATES)
    failures = 0
    for label, argv, marker in GATES:
        ok, detail = run_one(argv, marker)
        tag = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"  [{tag}]  {label:<{width}}  {detail}")
    print()
    if failures:
        print(f"SUITE FAILED \u2014 {failures}/{len(GATES)} gate(s) failed. Do NOT commit.")
        return 1
    print(f"SUITE PASSED \u2014 all {len(GATES)} gates green. Safe to commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
