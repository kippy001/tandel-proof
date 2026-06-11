#!/usr/bin/env python3
"""
stage0_lock_template.py  --  Stage 0 of the scorecard generator pipeline.

Turns the canonical (signed-off) scorecard HTML into a FROZEN, tokenized
template that the downstream stages fill. It does NOT invent markup: it only
collapses regions a human has explicitly marked with paired sentinel comments:

    <!--TOKEN:OPEN_ROWS-->  ...illustrative content...  <!--/TOKEN:OPEN_ROWS-->

Each marked region is replaced by its placeholder ``{{OPEN_ROWS}}``. Everything
outside the sentinels (CSS, masthead prose, verification explainer, hash-anatomy,
table headers, scoring rules, disclaimer, footer, JS) is preserved byte-for-byte.

Guarantees enforced here:
  * every token in the registry is marked exactly once  (no missing / no dupes)
  * no sentinel names appear that are not in the registry (no typos / no rogue)
  * no unbalanced or nested sentinels
  * the emitted template contains each placeholder exactly once and NO sentinels
  * idempotent: re-running on the output is a no-op (output has no sentinels)

Outputs (into --outdir, default ./build):
  template.html          the frozen template (chrome verbatim + {{TOKENS}})
  tokenization_map.json  ordered record of what was collapsed (name, kind, bytes)
  freeze_manifest.json   sha256(template) + source provenance + registry + ts

This script is pure stdlib. No engine dependencies.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
from pathlib import Path

GENERATOR_VERSION = "stage0-lock-template-v1.0"

# Paired sentinel:  <!--TOKEN:NAME-->  ...captured...  <!--/TOKEN:NAME-->
# NAME = UPPER_SNAKE. DOTALL so regions can span newlines. Non-greedy capture.
OPEN_RE  = re.compile(r"<!--\s*TOKEN:([A-Z][A-Z0-9_]*)\s*-->")
CLOSE_RE = re.compile(r"<!--\s*/TOKEN:([A-Z][A-Z0-9_]*)\s*-->")
PAIR_RE  = re.compile(
    r"<!--\s*TOKEN:([A-Z][A-Z0-9_]*)\s*-->(.*?)<!--\s*/TOKEN:\1\s*-->",
    re.DOTALL,
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_registry(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    reg: dict[str, str] = {}
    for entry in data["tokens"]:
        name, kind = entry["name"], entry["kind"]
        if kind not in ("scalar", "region"):
            raise ValueError(f"registry: token {name} has bad kind {kind!r}")
        if name in reg:
            raise ValueError(f"registry: duplicate token {name!r}")
        reg[name] = kind
    if not reg:
        raise ValueError("registry: no tokens defined")
    return reg


def _audit_sentinels(html: str, registry: dict[str, str]) -> list[tuple[str, str]]:
    """Validate sentinel structure before mutating anything. Returns ordered
    list of (name, kind) as they appear. Raises ValueError on any violation."""
    opens  = [(m.start(), m.group(1)) for m in OPEN_RE.finditer(html)]
    closes = [(m.start(), m.group(1)) for m in CLOSE_RE.finditer(html)]

    # Unknown names anywhere -> hard fail (catches typos like TOEKN/CLOSED_ROW).
    for _, name in opens + closes:
        if name not in registry:
            raise ValueError(f"sentinel uses unknown token {name!r} (not in registry)")

    # Walk in document order; sentinels must be strictly non-overlapping pairs.
    events = sorted(
        [(pos, "open", n) for pos, n in opens] + [(pos, "close", n) for pos, n in closes]
    )
    stack: list[str] = []
    order: list[str] = []
    for _, kind, name in events:
        if kind == "open":
            if stack:
                raise ValueError(
                    f"nested sentinel: {name!r} opened inside {stack[-1]!r} (regions must be flat)"
                )
            stack.append(name)
            order.append(name)
        else:  # close
            if not stack:
                raise ValueError(f"close sentinel /{name} with no matching open")
            if stack[-1] != name:
                raise ValueError(f"mismatched close: expected /{stack[-1]}, found /{name}")
            stack.pop()
    if stack:
        raise ValueError(f"unclosed sentinel(s): {', '.join(stack)}")

    # Coverage: every registry token marked exactly once.
    seen = {}
    for n in order:
        seen[n] = seen.get(n, 0) + 1
    dupes   = sorted(n for n, c in seen.items() if c > 1)
    missing = sorted(set(registry) - set(seen))
    if dupes:
        raise ValueError(f"token(s) marked more than once: {', '.join(dupes)}")
    if missing:
        raise ValueError(f"registry token(s) never marked in source: {', '.join(missing)}")

    return [(n, registry[n]) for n in order]


def lock_template(source_html: str, registry: dict[str, str]):
    order = _audit_sentinels(source_html, registry)

    captured: dict[str, str] = {}

    def _replace(m: re.Match) -> str:
        name, body = m.group(1), m.group(2)
        captured[name] = body
        return "{{" + name + "}}"

    template = PAIR_RE.sub(_replace, source_html)

    # Post-conditions: no sentinels survive, each placeholder appears exactly once.
    leftover = OPEN_RE.findall(template) + CLOSE_RE.findall(template)
    if leftover:
        raise AssertionError(f"sentinels survived collapse: {leftover}")
    for name in registry:
        n = template.count("{{" + name + "}}")
        if n != 1:
            raise AssertionError(f"placeholder {{{{{name}}}}} appears {n}x (expected 1)")

    token_map = [
        {"order": i, "name": n, "kind": k, "captured_bytes": len(captured[n].encode("utf-8"))}
        for i, (n, k) in enumerate(order)
    ]
    return template, token_map


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Freeze the canonical scorecard into a tokenized template.")
    ap.add_argument("source", help="Path to the canonical (sentinel-marked) scorecard HTML")
    ap.add_argument("--registry", default=str(Path(__file__).with_name("token_registry.json")))
    ap.add_argument("--outdir", default=str(Path(__file__).with_name("build")))
    args = ap.parse_args(argv)

    src_path = Path(args.source)
    outdir   = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    source_html = src_path.read_text(encoding="utf-8")
    registry    = _load_registry(Path(args.registry))

    template, token_map = lock_template(source_html, registry)

    tpath = outdir / "template.html"
    tpath.write_text(template, encoding="utf-8")
    (outdir / "tokenization_map.json").write_text(
        json.dumps({"tokens": token_map}, indent=2), encoding="utf-8"
    )
    manifest = {
        "generator": GENERATOR_VERSION,
        "frozen_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "source_file": src_path.name,
        "source_sha256": _sha256(source_html),
        "template_sha256": _sha256(template),
        "token_count": len(token_map),
        "tokens": [t["name"] for t in token_map],
    }
    (outdir / "freeze_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"  source      : {src_path.name}  ({len(source_html):,} bytes)")
    print(f"  template    : {tpath}  ({len(template):,} bytes)")
    print(f"  tokens      : {len(token_map)}  ->  {', '.join(t['name'] for t in token_map)}")
    print(f"  source  sha : {manifest['source_sha256'][:16]}\u2026")
    print(f"  template sha: {manifest['template_sha256'][:16]}\u2026")
    print("  FROZEN OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
