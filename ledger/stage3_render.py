#!/usr/bin/env python3
"""Stage 3 - render the U-VCT Scorecard from the ledger.

Closes the four-stage generator. Fills the 13 frozen template tokens
(build/template.html) from ledger.json + the Stage 2 derived stats, and proves
the result is byte-identical to canonical_source.html (the Stage 0 freeze).

Design (enhancement #3): the Scorecard is a PURE FUNCTION of
    (ledger.json, build_meta)
where build_meta is the single render-time input -- the wall-clock "Last
updated" value, which is inherently external to an append-only ledger of trades.
Every other displayed value (record, hit rate, net edge, typical hold, open
set, all table rows, the by-tier bars) is computed from the ledger rows. Stage 2
emits semantic data only; ALL presentation lives here:

  - <small> wrapper on the closed record, en-dash records, middle-dot notes,
  - comma grouping and U+2212 minus on P/L and net edge,
  - calendar date formatting (locale-independent month table),
  - tier-bar flex widths and the avoided color class,
  - tag color classes (w/l/a/live), num pos/neg classes.

The frozen chrome (CSS, masthead prose, verification explainer, hash-anatomy,
table headers, scoring rules, disclaimer, footer, JS) is never touched: only the
13 marked regions are filled, exactly as Stage 0 contracted.

stdlib only.

Usage:
    python3 stage3_render.py                 # render frozen build_meta, assert byte-identity
    python3 stage3_render.py --out page.html # also write the rendered page
    python3 stage3_render.py --build-meta "30 May 2026, 09:00 ET" --out page.html
    from stage3_render import render
"""
from __future__ import annotations

import argparse
import hashlib
import html
import sys
from pathlib import Path

from stage1_load_validate import load_ledger, validate_ledger
from stage2_derive import derive

# --- module-anchored paths (run from anywhere) -----------------------------
HERE = Path(__file__).parent
TEMPLATE = HERE / "build" / "template.html"
CANONICAL = HERE / "canonical_source.html"

# The frozen "Last updated" value baked into canonical_source.html. Supplying it
# lets the script prove the round-trip out of the box; production passes the real
# build time via --build-meta / the render(build_meta=...) argument.
FROZEN_BUILD_META = "28 May 2026, 16:40 ET"

# --- typography (exact code points the signed-off design uses) --------------
EN_DASH = "\u2013"  # - record separator, e.g. 7-3
EM_DASH = "\u2014"  # - empty cell, e.g. open close-date / avoided P/L
MINUS = "\u2212"    # - typographic minus on negative numbers
MIDDOT = "\u00b7"   # - middle dot separator in notes

MONTH_ABBR = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

# result -> (tag css class, tag text)
TAG = {"win": ("w", "win"), "loss": ("l", "loss"), "avoided": ("a", "avoided")}


# --- formatting helpers -----------------------------------------------------
def esc(s) -> str:
    """Escape element text content. No-op on current data; safe for future rows."""
    return html.escape(str(s), quote=False)


def fmt_date(iso: str) -> str:
    """'2026-03-28' -> '28 Mar' (zero-padded day, locale-independent month)."""
    y, m, d = iso.split("-")
    return f"{int(d):02d} {MONTH_ABBR[int(m)]}"


def fmt_signed_int(n: int) -> str:
    """Comma-grouped integer with explicit sign; U+2212 for negatives."""
    if n >= 0:
        return f"+{n:,}"
    return f"{MINUS}{abs(n):,}"


def fmt_edge(pt: float) -> str:
    """Entry edge in points: '+13.1 pt', '-5.0 pt' (U+2212), or '0.0 pt'."""
    if pt > 0:
        return f"+{pt:.1f} pt"
    if pt < 0:
        return f"{MINUS}{abs(pt):.1f} pt"
    return f"{pt:.1f} pt"


# \u00a723.82: the date the illustrative seed rows left the public page.
WITHDRAWN_ON = "4 Oct 2026"


def fmt_integrity(verified: int, illustrative: int, total: int, withdrawn: int = 0) -> str:
    """Footer hash-integrity coverage line. Pure presentation.

    '1 of 14 cryptographically verified \u00b7 13 illustrative'. The illustrative
    clause is dropped once every row is verified; an empty ledger is stated plainly.
    With rows withdrawn from display (verified-only render), the correction is
    stated with its date -- the page's own rule is that corrections are appended
    and dated.
    """
    if total == 0:
        line = "no calls recorded yet"
    else:
        line = f"{verified} of {total} cryptographically verified"
    if illustrative:
        line += f" {MIDDOT} {illustrative} illustrative"
    if withdrawn:
        line += (f" {MIDDOT} correction, {WITHDRAWN_ON}: {withdrawn} illustrative seed rows "
                 f"(design placeholders, never calls) were shown here and counted in the "
                 f"record above until this date; they are withdrawn from this page and "
                 f"remain in ledger.json")
    return line


def _num_cell(row: dict) -> tuple[str, str]:
    """(td class, P/L text) for a closed row."""
    if row["result"] in ("win", "loss"):
        cls = "num pos" if row["pl"] >= 0 else "num neg"
        return cls, fmt_signed_int(row["pl"])
    return "num", EM_DASH  # avoided -> no color class, em-dash


# --- region renderers (one row-pair = visible row + collapsible drawer) ------
def render_open_pair(row: dict) -> str:
    rid = row["run_id"]
    status = row["status"]  # 'live'
    return (
        f'<tr class="row" data-hash="{row["integrity"]["value"]}" '
        f'data-commit="{row["commit"]}" data-id="{rid}">\n'
        f'          <td><a class="runlink">{rid}</a></td>\n'
        f'          <td>{fmt_date(row["opened"])}</td>'
        f'<td>{esc(row["ticker"])}</td>'
        f'<td>{esc(row["structure"])}</td>'
        f'<td class="tier">{row["tier"]}</td>'
        f'<td><span class="tag {status}">{status}</span></td>\n'
        f'        </tr>\n'
        f'        <tr class="drawer"><td colspan="6"><div class="drawer-inner">'
        f'<div class="drawer-pad"></div></div></td></tr>'
    )


def render_closed_pair(row: dict) -> str:
    rid = row["run_id"]
    closed = fmt_date(row["closed"]) if row.get("closed") else EM_DASH
    ncls, ntext = _num_cell(row)
    tcls, ttext = TAG[row["result"]]
    return (
        f'<tr class="row" data-hash="{row["integrity"]["value"]}" '
        f'data-commit="{row["commit"]}" data-id="{rid}">\n'
        f'          <td><a class="runlink">{rid}</a></td>\n'
        f'          <td>{fmt_date(row["opened"])}</td><td>{closed}</td>'
        f'<td>{esc(row["ticker"])}</td>'
        f'<td>{esc(row["structure"])}</td>'
        f'<td class="tier">{row["tier"]}</td>'
        f'<td>{fmt_edge(row["entry_edge_pt"])}</td>'
        f'<td class="{ncls}">{ntext}</td>'
        f'<td><span class="tag {tcls}">{ttext}</span></td>\n'
        f'        </tr>\n'
        f'        <tr class="drawer"><td colspan="9"><div class="drawer-inner">'
        f'<div class="drawer-pad"></div></div></td></tr>'
    )


def render_by_tier(by_tier: list[dict]) -> str:
    lines = []
    for t in by_tier:
        n = t["tier"][1:]  # 'T5' -> '5'
        if t["wins"] == 0 and t["losses"] == 0 and t["avoided"] > 0:
            bar = '<span class="l" style="flex:1;background:var(--avoid)"></span>'
            rec = "avoided"
        else:
            parts = []
            if t["wins"] > 0:
                parts.append(f'<span class="w" style="flex:{t["wins"]}"></span>')
            if t["losses"] > 0:
                parts.append(f'<span class="l" style="flex:{t["losses"]}"></span>')
            bar = "".join(parts)
            rec = f'{t["wins"]}{EN_DASH}{t["losses"]}'
        lines.append(
            f'<div class="trow"><span>Tier {n}</span>'
            f'<span class="bar">{bar}</span>'
            f'<span class="rec">{rec}</span></div>'
        )
    return "\n      " + "\n      ".join(lines)


# --- token assembly ---------------------------------------------------------
def build_tokens(stats: dict, build_meta: str) -> dict[str, str]:
    """Map all 13 template tokens to their rendered fill strings."""
    open_pairs = [render_open_pair(r) for r in stats["open_rows"]]
    closed_pairs = [render_closed_pair(r) for r in stats["closed_rows"]]

    open_region = "\n        " + "\n        ".join(open_pairs) + "\n      "
    closed_region = "\n        " + "\n\n        ".join(closed_pairs) + "\n      "
    by_tier_region = render_by_tier(stats["by_tier"])

    open_note = f" {MIDDOT} ".join(stats["open_tickers"])
    # §23.82: with nothing scored there is no hit rate, edge or hold -- a 0 would
    # read as a measured zero. The seed design always has scored rows.
    scored = stats["scored"] > 0

    return {
        "BUILD_META": build_meta,
        "S_CLOSED_REC": f'{stats["wins"]}<small>{EN_DASH}{stats["losses"]}</small>',
        "S_CLOSED_NOTE": f'{stats["scored"]} scored {MIDDOT} {stats["avoided"]} avoided',
        "S_HITRATE": str(stats["hit_rate_pct"]) if scored else EM_DASH,
        "S_NETEDGE_CLS": stats["net_edge_cls"],
        "S_NETEDGE": fmt_signed_int(stats["net_edge"]) if scored else EM_DASH,
        "S_AVGHOLD": str(stats["median_hold_days"]) if scored else EM_DASH,
        "S_OPEN": str(stats["open_count"]),
        "S_OPEN_NOTE": open_note,
        "OPEN_ROWS": open_region,
        "CLOSED_ROWS": closed_region,
        "BY_TIER": by_tier_region,
        "S_INTEGRITY": fmt_integrity(
            stats["verified_count"], stats["illustrative_count"], stats["integrity_total"],
            stats.get("withdrawn_count", 0),
        ),
    }


def render(ledger: dict, build_meta: str = FROZEN_BUILD_META,
           verified_only: bool = False) -> str:
    """Render the full Scorecard HTML. Pure function of (ledger, build_meta).

    verified_only=True is the PUBLIC render (§23.82): only toon-sha256-v1 rows
    are shown or counted. The default reproduces the signed-off seed design.

    Works for ANY valid ledger -- appending a row and re-rendering is the
    intended weekly workflow. The reconcile-to-frozen check is a regression
    assertion for the SEED ledger and lives in the round-trip proof (main),
    not here; gating render on it would freeze the page to the seed forever.
    """
    stats = derive(ledger, verified_only=verified_only)
    tokens = build_tokens(stats, build_meta)
    page = TEMPLATE.read_text(encoding="utf-8")
    for name, value in tokens.items():
        ph = "{{" + name + "}}"
        if page.count(ph) != 1:
            raise ValueError(f"{ph} not unique in template (found {page.count(ph)})")
        page = page.replace(ph, value, 1)
    return page


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Stage 3 render + round-trip proof.")
    ap.add_argument("ledger", nargs="?", default=str(HERE / "ledger.json"))
    ap.add_argument("--build-meta", default=FROZEN_BUILD_META,
                    help="'Last updated' value (default: the frozen canonical value).")
    ap.add_argument("--out", default=None,
                    help="write the rendered page to this path.")
    ap.add_argument("--verified-only", action="store_true",
                    help="the public render: show and count toon-sha256-v1 rows only (§23.82).")
    args = ap.parse_args(argv[1:])

    data = load_ledger(args.ledger)
    errs = validate_ledger(data)
    if errs:
        print(f"REFUSING: ledger invalid ({len(errs)} error(s)). Run Stage 1.",
              file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 2

    page = render(data, args.build_meta, verified_only=args.verified_only)

    if args.out:
        Path(args.out).write_text(page, encoding="utf-8", newline="")
        print(f"  wrote {args.out}  ({len(page.encode('utf-8'))} bytes)")

    # Round-trip proof: only meaningful against the frozen build_meta.
    canonical = CANONICAL.read_text(encoding="utf-8")
    same = page == canonical
    print(f"  canonical sha : {_sha(canonical)[:24]}\u2026")
    print(f"  rendered  sha : {_sha(page)[:24]}\u2026")
    print(f"  byte-identical: {same}")
    if not same:
        if args.build_meta != FROZEN_BUILD_META:
            print("  (byte-identity is only expected with the frozen --build-meta)")
            return 0
        for i, (a, b) in enumerate(zip(canonical, page)):
            if a != b:
                lo = max(0, i - 30)
                print(f"  first diff at char {i}:")
                print(f"    canonical: {canonical[lo:i+30]!r}")
                print(f"    rendered : {page[lo:i+30]!r}")
                break
        else:
            print(f"  length differs: canonical {len(canonical)} vs rendered {len(page)}")
        return 1
    print("  STAGE 3 LOSSLESS \u2014 ledger.json + build_meta regenerates the "
          "signed-off Scorecard exactly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
