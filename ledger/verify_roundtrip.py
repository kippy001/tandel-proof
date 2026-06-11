#!/usr/bin/env python3
"""
verify_roundtrip.py -- proves the freeze is lossless.

Reconstructs the original page from build/template.html + the region contents
captured from canonical_marked.html, then asserts the result is byte-identical
to the pristine canonical_source.html (same SHA-256). If this passes, the frozen
template provably reproduces the signed-off design exactly when given the
original data.
"""
import hashlib
import re
import sys
from pathlib import Path

PAIR = re.compile(r"<!--\s*TOKEN:([A-Z][A-Z0-9_]*)\s*-->(.*?)<!--\s*/TOKEN:\1\s*-->", re.DOTALL)


def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


HERE = Path(__file__).parent
canonical = (HERE / "canonical_source.html").read_text(encoding="utf-8")
marked    = (HERE / "canonical_marked.html").read_text(encoding="utf-8")
template  = (HERE / "build" / "template.html").read_text(encoding="utf-8")

# Capture the original content of each region from the marked file.
captures = {name: body for name, body in PAIR.findall(marked)}

# Reconstruct: fill each placeholder with its captured content.
recon = template
for name, body in captures.items():
    placeholder = "{{" + name + "}}"
    assert recon.count(placeholder) == 1, f"{placeholder} not unique in template"
    recon = recon.replace(placeholder, body, 1)

same = recon == canonical
print(f"  canonical sha : {sha(canonical)[:24]}\u2026")
print(f"  reconstructed : {sha(recon)[:24]}\u2026")
print(f"  byte-identical: {same}")
if not same:
    # show first divergence for debugging
    for i, (a, b) in enumerate(zip(canonical, recon)):
        if a != b:
            print(f"  first diff at char {i}: {canonical[i-20:i+20]!r} != {recon[i-20:i+20]!r}")
            break
    sys.exit(1)
print("  ROUND-TRIP LOSSLESS \u2014 template reproduces the signed-off design exactly")
