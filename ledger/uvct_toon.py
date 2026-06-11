#!/usr/bin/env python3
"""Deterministic @U-VCT TOON field serializer (uvct-toon-v1 field-order contract).

CANONICALIZATION.md hashes the @U-VCT line as an opaque ORDERED blob and does NOT
sort keys, so field order is part of the preimage. The line is emitted by skill
convention, not code -- meaning order had no code backstop. This module IS that
backstop: it pins the canonical field sequence in code and refuses anything else.

  emit_uvct_toon(fields)  -> canonical line, fields forced into FIELD_ORDER
  parse_uvct_toon(line)   -> {key: opaque_value}, inverse of emit
  canonical_line(line)    -> normalize an existing line's field order (parse+emit)

Design (deliberately minimal, matches the spec's "opaque blob" stance):
  * Top-level pipe fields are ordered; that is the whole contract.
  * VALUES are opaque strings (everything after the first ':'). Intra-field
    sub-token order is the emitter's responsibility, NOT rewritten here -- the
    spec says sub-token order must be frozen at emission, not papered over.
  * Unknown keys FAIL CLOSED (KeyError). A new field is a uvct-toon-v2 event,
    not something to append in arbitrary position.
"""
from collections import OrderedDict

SENTINEL = "@U-VCT"

# Frozen field sequence. Captured from the first verified row
# (RUN-20260530-MU-fed3eb41, u-vct-v4.1.0) and pinned in CANONICALIZATION.md.
FIELD_ORDER = (
    "T", "W", "SPOT", "TIER", "EDGE", "CAT", "REG", "M2b", "POL",
    "GEX", "GARCH", "CF", "VIA", "DECISION", "SIZE", "CONF", "HASH",
)
_ORDER_INDEX = {k: i for i, k in enumerate(FIELD_ORDER)}


def emit_uvct_toon(fields) -> str:
    """Serialize {key: value} into the canonical @U-VCT line.

    Fields are emitted in FIELD_ORDER; absent fields are omitted (not
    reordered). Input iteration order is irrelevant -- that is the point.
    Unknown keys raise KeyError (fail closed). No trailing newline.
    """
    fields = dict(fields)
    unknown = [k for k in fields if k not in _ORDER_INDEX]
    if unknown:
        raise KeyError(
            f"unknown @U-VCT field(s) {unknown} -- not in the frozen contract; "
            f"a new field requires a uvct-toon-v2 bump, not silent emission"
        )
    parts = [SENTINEL]
    for key in FIELD_ORDER:
        if key in fields:
            val = fields[key]
            if "|" in str(val):
                raise ValueError(f"field {key!r} value contains '|' (delimiter)")
            parts.append(f"{key}:{val}")
    return "|".join(parts)


def parse_uvct_toon(line: str) -> "OrderedDict[str, str]":
    """Inverse of emit_uvct_toon. Splits on '|', then first ':' per field.

    Validates the sentinel and rejects unknown / duplicate keys (fail closed).
    Values are returned opaque (everything after the first colon).
    """
    line = line.rstrip("\n")
    segs = line.split("|")
    if not segs or segs[0] != SENTINEL:
        raise ValueError(f"missing/!{SENTINEL} sentinel: {segs[:1]}")
    out: "OrderedDict[str, str]" = OrderedDict()
    for seg in segs[1:]:
        if ":" not in seg:
            raise ValueError(f"malformed field (no ':'): {seg!r}")
        key, val = seg.split(":", 1)
        if key not in _ORDER_INDEX:
            raise KeyError(f"unknown @U-VCT field {key!r}")
        if key in out:
            raise ValueError(f"duplicate field {key!r}")
        out[key] = val
    return out


def canonical_line(line: str) -> str:
    """Normalize an existing @U-VCT line's field order to the contract.

    parse+emit round-trip. For a conformant line this is the identity; for a
    reordered line it restores FIELD_ORDER. Intended as the emission path for
    NEW verified rows so order can never drift into the digest.
    """
    return emit_uvct_toon(parse_uvct_toon(line))
