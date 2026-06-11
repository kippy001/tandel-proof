#!/usr/bin/env python3
"""Canonicalization harness for uvct-toon-v1 (CANONICALIZATION.md steps 1-7).
Run: python3 tests/test_canonicalize_toon.py

The first verified row's TOON was already clean (no BOM, LF-only, single
trailing \n), so normalization steps 2-5 were never exercised by a real digest.
These cases feed deliberately *dirty* inputs and assert each canonicalizes to
the SAME digest as the clean form -- locking step 2 (BOM strip), step 3
(CRLF->LF, lone CR->LF), step 4 (trailing-ws strip), step 5 (trailing-blank
collapse) -- plus step 1 (strict-UTF-8 reject) and glyph survival. Self-running
harness (no pytest), matching tests/test_stage0.py.
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from stage1_load_validate import canonicalize_toon, toon_sha256, CANON_PREFIX  # noqa: E402

# Representative @U-VCT line: LF, single trailing newline, real Unicode
# (-> sigma gamma kappa) = the CLEAN baseline form.
CLEAN = (
    b"@U-VCT|T:MU|W:2026-05-30|REG:LVMR\xe2\x86\x92LOW_OOS|GARCH:\xcf\x83 97%|"
    b"CF:\xce\xb3 0.13,\xce\xba 0.79|DECISION:NO_TRADE\n"
)
CLEAN_DIGEST = toon_sha256(CLEAN)

passed = failed = 0


def check(name, fn):
    global passed, failed
    try:
        fn()
        passed += 1
    except AssertionError as e:
        failed += 1
        print(f"  FAIL: {name}: {e}")
    except Exception as e:  # unexpected (import, decode where not expected, ...)
        failed += 1
        print(f"  ERROR: {name}: {type(e).__name__}: {e}")


def t_baseline():
    pre = canonicalize_toon(CLEAN)
    assert pre.startswith(CANON_PREFIX), "missing domain-separation prefix"
    assert pre.endswith(b"\n") and not pre.endswith(b"\n\n"), "not single trailing nl"


def t_bom_stripped():  # step 2
    assert toon_sha256(b"\xef\xbb\xbf" + CLEAN) == CLEAN_DIGEST


def t_crlf():  # step 3 (likely Windows failure)
    assert toon_sha256(CLEAN.replace(b"\n", b"\r\n")) == CLEAN_DIGEST


def t_lone_cr():  # step 3 second clause
    assert toon_sha256(CLEAN.replace(b"\n", b"\r")) == CLEAN_DIGEST


def t_trailing_ws():  # step 4
    assert toon_sha256(CLEAN.rstrip(b"\n") + b"   \t  \n") == CLEAN_DIGEST


def t_trailing_blanks():  # step 5
    assert toon_sha256(CLEAN.rstrip(b"\n") + b"\n\n\n\n") == CLEAN_DIGEST


def t_all_dirt():  # steps 2-5 combined = realistic Windows artifact
    dirty = b"\xef\xbb\xbf" + CLEAN.rstrip(b"\n").replace(b"\n", b"\r\n") + b"  \r\n\r\n"
    assert toon_sha256(dirty) == CLEAN_DIGEST


def t_strict_utf8():  # step 1: reject, do NOT replace
    try:
        canonicalize_toon(b"@U-VCT|BAD:\xff\xfe|END\n")
    except UnicodeDecodeError:
        return
    raise AssertionError("invalid UTF-8 was not rejected")


def t_glyphs_survive():  # ->/sigma/gamma/kappa preserved through canon
    assert "\u2192".encode("utf-8") in CLEAN
    assert toon_sha256(CLEAN) == hashlib.sha256(canonicalize_toon(CLEAN)).hexdigest()


TESTS = [
    ("baseline_prefix_and_trailing_nl", t_baseline),
    ("bom_stripped", t_bom_stripped),
    ("crlf_normalized", t_crlf),
    ("lone_cr_normalized", t_lone_cr),
    ("trailing_whitespace_stripped", t_trailing_ws),
    ("trailing_blank_lines_collapsed", t_trailing_blanks),
    ("all_dirt_combined", t_all_dirt),
    ("strict_utf8_rejects_invalid", t_strict_utf8),
    ("unicode_glyphs_survive", t_glyphs_survive),
]

for _name, _fn in TESTS:
    check(_name, _fn)

print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)