#!/usr/bin/env python3
"""
mark_sentinels.py -- one supervised pass that wraps the 13 dynamic regions of
the canonical scorecard in <!--TOKEN:NAME-->...<!--/TOKEN:NAME--> sentinels.

Reads  : canonical_source.html  (pristine, untouched)
Writes : canonical_marked.html

Every edit asserts an exact, unique match (count == 1). If the source changes
shape and an anchor stops matching uniquely, this fails loudly rather than
mis-placing a sentinel. Whitespace inside captured regions is preserved
verbatim, so freezing is lossless (proven separately by verify_roundtrip.py).
"""
import re
import sys
from pathlib import Path

SRC = Path("canonical_source.html")
OUT = Path("canonical_marked.html")

html = SRC.read_text(encoding="utf-8")


def wrap_literal(text, name, anchor, inner):
    """Wrap `inner` (a substring of `anchor`) with sentinels; anchor must be unique."""
    assert text.count(anchor) == 1, f"[{name}] anchor not unique ({text.count(anchor)}x): {anchor[:60]!r}"
    marked_anchor = anchor.replace(inner, f"<!--TOKEN:{name}-->{inner}<!--/TOKEN:{name}-->", 1)
    return text.replace(anchor, marked_anchor, 1)


def wrap_region(text, name, pattern):
    """Wrap regex group(2) (the inner content) with sentinels; pattern must match once."""
    rx = re.compile(pattern, re.DOTALL)
    matches = rx.findall(text)
    assert len(matches) == 1, f"[{name}] region pattern matched {len(matches)}x (need 1)"
    return rx.sub(lambda m: f"{m.group(1)}<!--TOKEN:{name}-->{m.group(2)}<!--/TOKEN:{name}-->{m.group(3)}", text, count=1)


# --- scalars (leaf values; surrounding markup stays frozen) -------------------
html = wrap_literal(html, "BUILD_META",
                    '<b style="color:var(--text)">28 May 2026, 16:40 ET</b>',
                    '28 May 2026, 16:40 ET')
html = wrap_literal(html, "S_CLOSED_REC",
                    '<div class="val">7<small>\u2013\u200b'.replace('\u200b', '') + '3</small></div>'
                    if False else '<div class="val">7<small>\u20133</small></div>',
                    '7<small>\u20133</small>')
html = wrap_literal(html, "S_CLOSED_NOTE",
                    '<div class="note">10 scored \u00b7 1 avoided</div>',
                    '10 scored \u00b7 1 avoided')
html = wrap_literal(html, "S_HITRATE",
                    '<div class="val">70<small>%</small></div>',
                    '70')
html = wrap_literal(html, "S_NETEDGE",
                    '<div class="val pos">+1,025</div>',
                    '+1,025')
# Promote the sign-color class to its own token (sequential, not nested).
# Done after the value wrap so the class anchor `class="val pos"` is still intact.
html = wrap_literal(html, "S_NETEDGE_CLS",
                    'class="val pos"',
                    'pos')
html = wrap_literal(html, "S_AVGHOLD",
                    '<div class="val">13<small>d</small></div>',
                    '13')
html = wrap_literal(html, "S_OPEN",
                    '<div class="val live" style="color:var(--live)">2</div>',
                    '2')
html = wrap_literal(html, "S_OPEN_NOTE",
                    '<div class="note">NVDA \u00b7 SMH</div>',
                    'NVDA \u00b7 SMH')

# Footer hash-integrity coverage line (seed value: 0 verified / 13 illustrative).
html = wrap_literal(html, "S_INTEGRITY",
                    '<div class="ledger-integrity">Hash integrity: 0 of 13 cryptographically verified \u00b7 13 illustrative</div>',
                    '0 of 13 cryptographically verified \u00b7 13 illustrative')

# --- regions (variable-length blocks) -----------------------------------------
# Open-positions tbody: anchored by the NVDA hash, unique to that table.
html = wrap_region(html, "OPEN_ROWS",
                   r'(<tbody>)(\s*<tr class="row" data-hash="c4e1a8b97f3d0e21".*?)(</tbody>)')
# Closed-ledger tbody: anchored by the UAN seed hash, unique to that table.
html = wrap_region(html, "CLOSED_ROWS",
                   r'(<tbody>)(\s*<tr class="row" data-hash="b71c0fd9a2e4__seed1".*?)(</tbody>)')
# By-tier bars: ends at the </div> immediately preceding the permanent caveat <p>.
html = wrap_region(html, "BY_TIER",
                   r'(<div class="tiers">)(.*?)(\n    </div>\n    <p style="color:var\(--text-faint\))')

OUT.write_text(html, encoding="utf-8")

# sanity: 11 opens + 11 closes
opens = len(re.findall(r"<!--\s*TOKEN:", html))
closes = len(re.findall(r"<!--\s*/TOKEN:", html))
print(f"marked {opens} opens / {closes} closes -> {OUT}")
assert opens == 13 and closes == 13, "expected 13 paired sentinels"
print("OK")
