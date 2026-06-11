# ledger/ — Scorecard generator subsystem

Makes the public Scorecard page a **pure function of `ledger.json`**: same data in,
same bytes out. The static chrome (CSS, verification explainer, hash-anatomy,
table headers, scoring rules, disclaimer, footer, JS) is frozen and never
hand-edited; only marked data regions are filled.

Pipeline (all four stages built): **Stage 0** freeze tokenized template →
**Stage 1** loader/validator → **Stage 2** derived stats → **Stage 3** render.
Stage 3 closes the loop: `ledger.json` (+ a build_meta timestamp) regenerates
`canonical_source.html` byte-for-byte, making the Scorecard a pure function of
the ledger.

## Stage 0 — freeze the signed-off design into a tokenized template

`stage0_lock_template.py` collapses human-marked sentinel regions
(`<!--TOKEN:NAME-->…<!--/TOKEN:NAME-->`) into `{{NAME}}` placeholders, leaving
everything else byte-for-byte intact. It is fail-loud: a missing token, a
duplicate, an unknown name, an unbalanced pair, or nesting all abort the freeze,
so the approved design can never be silently altered.

### Files
- `stage0_lock_template.py` — tokenizer + validator (stdlib only; idempotent)
- `token_registry.json` — contract: 13 dynamic regions (10 scalar, 3 region)
- `mark_sentinels.py` — one supervised marking pass; every insertion asserts a unique match
- `verify_roundtrip.py` — reconstructs the original from template + data; asserts byte-identity
- `canonical_source.html` — the pristine signed-off scorecard (provenance)
- `canonical_marked.html` — the sentinel-marked input that was frozen
- `build/template.html` — the frozen template (Stages 1–3 fill this)
- `build/freeze_manifest.json` — provenance + SHA-256 drift tripwire
- `build/tokenization_map.json` — ordered record of collapsed regions
- `stage1_load_validate.py` — ledger loader + schema/structural validator (stdlib)
- `stage2_derive.py` — derived stats (record, hit rate, net edge, median hold, by-tier)
- `stage3_render.py` — render: fills the 13 tokens, proves `ledger.json` → bytes
- `run_gates.py` — runs all 6 gates; non-zero exit on any failure (pre-commit check)
- `ledger.json` — single source of truth (append-only); `ledger.schema.json` — its contract
- `tests/` — Stage 0 (10 checks) + Stage 3 (19 checks: round-trip, purity, formatting)

### Integrity (this freeze — post footer hash-integrity count)
- `canonical_source.html` SHA-256 — `40adc0de03edc39bfd215c05503ac848590728a9b65a9ba16db8669c9a9c82a7`
- `canonical_marked.html` (freeze input) SHA-256 — `8395020444f7d0cc37b4412ccef4a290109214938a15fd44842b8f009b9b47ae`
- `build/template.html` (frozen) SHA-256 — `5f5046fe38954068fbd85702e91b7c0bd7b4c12c2ac72a88ec5b481049567fb5`

**Round-trip guarantee:** `template.html` with the original region data substituted
back reproduces `canonical_source.html` exactly (verified against `40adc0…`). Stage 3
proves the stronger claim: rendering from `ledger.json` alone (+ build_meta)
regenerates those same bytes.

### Reproduce / verify
```bash
python3 run_gates.py               # authoritative pre-commit check: all 6 gates, exit!=0 on any fail
```
Individual gates (what `run_gates.py` runs):
```bash
python3 stage1_load_validate.py    # ledger is VALID
python3 stage2_derive.py           # derived stats reconcile to the freeze
python3 verify_roundtrip.py        # template + data == canonical, byte-identical
python3 stage3_render.py           # ledger.json -> bytes, byte-identical to canonical
python3 tests/test_stage0.py       # 10/10
python3 tests/test_stage3.py       # 19/19
```
Re-freeze (only when the signed-off design itself changes):
```bash
python3 mark_sentinels.py          # canonical_source.html -> canonical_marked.html
python3 stage0_lock_template.py canonical_marked.html --outdir build
```

### Token registry (Stage 3 fills these)
Scalars: `BUILD_META`, `S_CLOSED_REC`, `S_CLOSED_NOTE`, `S_HITRATE`,
`S_NETEDGE`, `S_NETEDGE_CLS` (sign→color), `S_AVGHOLD`, `S_OPEN`, `S_OPEN_NOTE`,
`S_INTEGRITY` (footer hash-integrity coverage: verified/illustrative split).
Regions: `OPEN_ROWS`, `CLOSED_ROWS`, `BY_TIER`. The by-tier caveat paragraph is
frozen chrome, not data.

## Stage 3 — render

`stage3_render.py` is `render(ledger, build_meta) -> html`. Stage 2 emits
semantic data only; all presentation lives in Stage 3 — the `<small>` on the
record, en-dash records, middle-dot notes, comma grouping and U+2212 minus on
P/L and net edge, locale-independent date formatting, tier-bar flex widths, and
the tag/num color classes. It fills the 13 tokens and asserts byte-identity
against `canonical_source.html`.

`build_meta` (the masthead "Last updated" value) is the **single render-time
input** — a wall-clock fact inherently outside an append-only trade ledger.
Everything else displayed is computed from the rows, so the page is a pure
function of `(ledger.json, build_meta)`. Appending a row and re-rendering is the
intended weekly workflow; the reconcile-to-frozen check is a seed regression
assertion (in the round-trip proof), never a precondition for rendering.

> `build/` artifacts are generated. They are committed here as the freeze
> checkpoint other stages depend on; regenerate with the commands above.
