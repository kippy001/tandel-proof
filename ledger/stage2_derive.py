#!/usr/bin/env python3
"""Stage 2 - derived statistics for the U-VCT Scorecard.

Reads validated ledger rows and computes every value the Scorecard displays.
Governance: stats are DERIVED here, never stored in ledger.json. This module
emits semantic data only - no HTML, no presentation formatting (the <small>
tag, comma grouping, tier bars, and color classes belong to Stage 3 render).

Reconciliation: derive() over the seeded ledger reproduces the frozen Stage 0
template exactly: 7-3, 70%, +1025 net edge, median hold 13, 2 open (NVDA/SMH),
by-tier T5 1-0 / T4 2-1 / T3 3-2 / T2 1-0 / T1 avoided.

NOTE on "avg hold": the frozen template's "Avg hold = 13" is the MEDIAN of
calendar holding days, not the mean (mean = 15, pulled up by one 37-day hold).
We compute the median to match. The display label ("Avg") is a Stage 3 copy
decision - relabel to "Median/Typical hold" or keep "Avg" and document it.

stdlib only.

Usage:
    python3 stage2_derive.py [ledger.json]      # print derived stats + reconcile
    from stage2_derive import derive, reconcile
"""

from __future__ import annotations

import json
import sys
from datetime import date
from statistics import median

from stage1_load_validate import load_ledger, validate_ledger

TIER_ORDER = ["T5", "T4", "T3", "T2", "T1"]  # display order, high to low

# Frozen Stage 0 template values - the regression target Stage 2 must reproduce.
FROZEN_EXPECTED = {
    "wins": 7, "losses": 3, "scored": 10, "avoided": 1,
    "hit_rate_pct": 70, "net_edge": 1025, "net_edge_cls": "pos",
    "median_hold_days": 13, "open_count": 2,
    "open_tickers": ["NVDA", "SMH"],
    "by_tier": [
        {"tier": "T5", "wins": 1, "losses": 0, "avoided": 0},
        {"tier": "T4", "wins": 2, "losses": 1, "avoided": 0},
        {"tier": "T3", "wins": 3, "losses": 2, "avoided": 0},
        {"tier": "T2", "wins": 1, "losses": 0, "avoided": 0},
        {"tier": "T1", "wins": 0, "losses": 0, "avoided": 1},
    ],
}


def _d(iso: str) -> date:
    y, m, dd = map(int, iso.split("-"))
    return date(y, m, dd)


def hold_days(row: dict) -> int:
    """Calendar holding days for a win/loss row (closed - opened)."""
    return (_d(row["closed"]) - _d(row["opened"])).days


def derive(ledger: dict, verified_only: bool = False) -> dict:
    """Compute all derived stats + the ordered row sets Stage 3 will render.

    Returns semantic data only. Stage 3 owns all presentation.

    verified_only (§23.82): the PUBLIC page derives everything from
    toon-sha256-v1 rows alone. Until 2026-10-04 it counted the 13 illustrative
    seed rows as a 7-3 record, a 70% hit rate and +1,025 under a masthead
    saying every call was verifiable. The rows stay in ledger.json (append-only);
    they are withdrawn from display and counted in `withdrawn_count`. The
    default (False) keeps reproducing the signed-off seed design for the
    generator-correctness gates.
    """
    rows = ledger["rows"]
    withdrawn = 0
    if verified_only:
        withdrawn = sum(1 for r in rows if r["integrity"]["scheme"] != "toon-sha256-v1")
        rows = [r for r in rows if r["integrity"]["scheme"] == "toon-sha256-v1"]
    open_rows = [r for r in rows if r["state"] == "open"]
    closed = [r for r in rows if r["state"] == "closed"]
    scored = [r for r in closed if r["result"] in ("win", "loss")]
    avoided = [r for r in closed if r["result"] == "avoided"]
    wins = [r for r in scored if r["result"] == "win"]
    losses = [r for r in scored if r["result"] == "loss"]

    net_edge = sum(r["pl"] for r in scored)
    holds = [hold_days(r) for r in scored]
    median_hold = int(round(median(holds))) if holds else 0
    hit_rate = int(round(100 * len(wins) / len(scored))) if scored else 0

    by_tier = []
    for t in TIER_ORDER:
        trows = [r for r in closed if r["tier"] == t]
        if not trows:
            continue
        by_tier.append({
            "tier": t,
            "wins": sum(1 for r in trows if r["result"] == "win"),
            "losses": sum(1 for r in trows if r["result"] == "loss"),
            "avoided": sum(1 for r in trows if r["result"] == "avoided"),
        })

    # Hash-integrity coverage over ALL rows, split by integrity.scheme.
    # Mirrors stage1 _summary so there is one definition of verified/illustrative.
    verified = sum(1 for r in rows if r["integrity"]["scheme"] == "toon-sha256-v1")
    illustrative = sum(1 for r in rows if r["integrity"]["scheme"] == "illustrative-snapshot-v0")

    return {
        # scalar stats (semantic; Stage 3 formats)
        "wins": len(wins),
        "losses": len(losses),
        "scored": len(scored),
        "avoided": len(avoided),
        "hit_rate_pct": hit_rate,
        "net_edge": net_edge,
        "net_edge_cls": "pos" if net_edge >= 0 else "neg",
        "median_hold_days": median_hold,
        "open_count": len(open_rows),
        "open_tickers": [r["ticker"] for r in open_rows],
        "by_tier": by_tier,
        # hash-integrity coverage (semantic; Stage 3 phrases it)
        "verified_count": verified,
        "illustrative_count": illustrative,
        "integrity_total": len(rows),
        "withdrawn_count": withdrawn,
        # region row sets (already chronological from append-only ledger)
        "open_rows": open_rows,
        "closed_rows": closed,
        # NOTE: BUILD_META is a generation timestamp, not derivable from rows.
        # Stage 3 injects it (defaults to build time; override to reproduce frozen).
    }


def reconcile(stats: dict, expected: dict = FROZEN_EXPECTED) -> list[str]:
    """Compare derived stats against the frozen template. Empty list == match."""
    diffs = []
    for k, exp in expected.items():
        got = stats.get(k)
        if got != exp:
            diffs.append(f"{k}: derived {got!r} != frozen {exp!r}")
    return diffs


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else "ledger.json"
    data = load_ledger(path)
    errs = validate_ledger(data)
    if errs:
        print(f"REFUSING: ledger invalid ({len(errs)} error(s)). Run Stage 1.", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 2

    stats = derive(data)
    scalar = {k: v for k, v in stats.items() if k not in ("open_rows", "closed_rows")}
    print(json.dumps(scalar, indent=2))

    diffs = reconcile(stats)
    if diffs:
        print(f"\nRECONCILE MISMATCH ({len(diffs)}):", file=sys.stderr)
        for d in diffs:
            print(f"  - {d}", file=sys.stderr)
        return 1
    print("\nRECONCILE OK - derived stats match frozen Stage 0 template.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
