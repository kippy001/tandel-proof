#!/usr/bin/env python3
"""Round-trip + reorder-invariance harness for the @U-VCT serializer.
Run: python3 tests/test_uvct_toon_serializer.py

Proves three things:
  1. FAITHFUL: the frozen FIELD_ORDER reproduces the real first verified row
     (RUN-20260530-MU-fed3eb41) byte-for-byte -- so the contract isn't a guess.
  2. ENFORCED: scrambling the input field order yields the SAME canonical line,
     and the SAME toon-sha256 -- field reordering is now impossible to affect
     the digest, not merely discouraged.
  3. FAIL CLOSED: unknown fields, bad sentinel, '|' in values are rejected.

Self-running harness (no pytest), matching tests/test_stage0.py style.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from uvct_toon import emit_uvct_toon, parse_uvct_toon, canonical_line, FIELD_ORDER  # noqa: E402
from stage1_load_validate import canonicalize_toon, toon_sha256, CANON_PREFIX  # noqa: E402

# The real first verified row's archived TOON + its stored digest.
TOON_PATH = ROOT / "toons" / "RUN-20260530-MU-fed3eb41.toon"
STORED = "71ea6f25083a285cae9903336587dbcbb5992dd5d29fd5618c0878c261ae9dcd"

raw = TOON_PATH.read_bytes()
# canonical line = canonicalized preimage minus the domain prefix and trailing nl
CANON_LINE = canonicalize_toon(raw)[len(CANON_PREFIX):].decode("utf-8").rstrip("\n")

passed = failed = 0


def check(name, fn):
    global passed, failed
    try:
        fn(); passed += 1
    except AssertionError as e:
        failed += 1; print(f"  FAIL: {name}: {e}")
    except Exception as e:
        failed += 1; print(f"  ERROR: {name}: {type(e).__name__}: {e}")


def t_roundtrip_byte_identical():           # (1) FAITHFUL
    fields = parse_uvct_toon(CANON_LINE)
    assert emit_uvct_toon(fields) == CANON_LINE, "re-emit not byte-identical to source"


def t_all_fields_recognized():              # contract covers every field present
    fields = parse_uvct_toon(CANON_LINE)
    assert set(fields).issubset(set(FIELD_ORDER))
    assert list(fields) == [k for k in FIELD_ORDER if k in fields], "source not in contract order"


def t_reorder_invariant_line():             # (2) ENFORCED -- order in == order out
    fields = parse_uvct_toon(CANON_LINE)
    scrambled = dict(reversed(list(fields.items())))
    assert emit_uvct_toon(scrambled) == CANON_LINE, "scrambled input changed the line"


def t_reorder_invariant_digest():           # (2) ENFORCED -- same digest, matches stored
    fields = parse_uvct_toon(CANON_LINE)
    scrambled = dict(sorted(fields.items()))           # alphabetical: maximally wrong order
    line = canonical_line("|".join(["@U-VCT"] + [f"{k}:{v}" for k, v in scrambled.items()]))
    digest = toon_sha256((line + "\n").encode("utf-8"))
    assert digest == STORED, f"normalized digest {digest[:12]} != stored {STORED[:12]}"


def t_canonical_line_is_identity_on_conformant():
    assert canonical_line(CANON_LINE) == CANON_LINE


def t_reject_unknown_field():               # (3) FAIL CLOSED
    try:
        emit_uvct_toon({"T": "MU", "BOGUS": "x"})
    except KeyError:
        return
    raise AssertionError("unknown field not rejected")


def t_reject_bad_sentinel():
    try:
        parse_uvct_toon("@OOS|T:MU")
    except ValueError:
        return
    raise AssertionError("bad sentinel not rejected")


def t_reject_pipe_in_value():
    try:
        emit_uvct_toon({"T": "M|U"})
    except ValueError:
        return
    raise AssertionError("'|' in value not rejected")


TESTS = [
    ("roundtrip_byte_identical", t_roundtrip_byte_identical),
    ("all_fields_recognized", t_all_fields_recognized),
    ("reorder_invariant_line", t_reorder_invariant_line),
    ("reorder_invariant_digest_matches_stored", t_reorder_invariant_digest),
    ("canonical_line_identity_on_conformant", t_canonical_line_is_identity_on_conformant),
    ("reject_unknown_field", t_reject_unknown_field),
    ("reject_bad_sentinel", t_reject_bad_sentinel),
    ("reject_pipe_in_value", t_reject_pipe_in_value),
]
for _n, _f in TESTS:
    check(_n, _f)
print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
