# TOON canonicalization â€” `uvct-toon-v1`

This pins the exact preimage for the ledger's content-integrity hash. The claim
the hash supports is **content integrity**: "this ledger row corresponds to
exactly this archived TOON; recompute to verify." It is *not* tamper-evidence
against the publisher (a self-published hash can always be recomputed after an
edit). Temporal anchoring is provided by git commit history, not by this hash.

## Why a spec is mandatory

`canonical_source.html` is LF-only and the Stage 0 round-trip is byte-identical
across platforms â€” but the TOON archive originates on a Windows working tree. If
the hashed preimage is not normalized, a skeptic who recomputes on another OS
gets a different digest and the verification story silently breaks. The most
likely failure is newline drift (CRLF vs LF), so normalization is not optional.

## Preimage construction (`uvct-toon-v1`)

Given the raw TOON archive bytes for a run:

1. **Decode** as UTF-8 (strict; reject invalid bytes â€” do not silently replace).
2. **Strip a leading UTF-8 BOM** (`U+FEFF`) if present.
3. **Normalize newlines**: `\r\n` -> `\n`, then any remaining lone `\r` -> `\n`.
4. **Strip trailing whitespace on each line** (spaces/tabs before the newline).
   TOON is whitespace-significant only for indentation (leading), never trailing.
5. **Collapse trailing blank lines** to exactly one terminating `\n`
   (the file ends with a single newline; no more, no fewer).
6. **Domain-separate**: prepend the literal ASCII prefix `uvct-toon-v1\n`.
   This prevents a digest computed over a TOON block from ever colliding with a
   digest computed over some other artifact that happens to share the bytes.
7. **Encode** the result back to UTF-8 -> these bytes are the preimage.

`sha256` = lowercase hex SHA-256 of the preimage (64 chars).

## What is deliberately NOT done here

- **No key reordering / structural canonicalization.** The TOON archive is
  treated as an opaque, ordered text blob. If a future engine emits TOON whose
  key order is non-deterministic, that must be fixed at emission time (or this
  spec bumped to `uvct-toon-v2` with an explicit sort), NOT papered over here.
  Flagged because no live TOON sample was available when this was written.
- **No `run_id[:8] == sha256[:8]` coupling.** Published run_ids already encode
  the first 8 chars of the *old* `compute_snapshot_hash` (e.g.
  `RUN-20260415-TSLA-ae0071f3` <- `data-hash ae0071f3b1568589`), and one seed
  hash (`b71c0fd9a2e4__seed1`) is not even valid hex. run_id is the stable
  identity assigned at open; sha256 is finalized independently at close. Coupling
  them would force run_id rewrites, violating append-only.

## Reference implementation

`stage1_load_validate.py` ships `canonicalize_toon(raw: bytes) -> bytes` and
`toon_sha256(raw: bytes) -> str` implementing exactly the above, stdlib-only.
Enhancement #5 computes real `toon-sha256-v1` values with these functions; until
then, seed rows carry `integrity.scheme = "illustrative-snapshot-v0"` and are
labeled illustrative, never "verified".

## Field order is part of the preimage (`@U-VCT` TOON)

Step "What is deliberately NOT done here" states this spec performs **no key
reordering** â€” the TOON is hashed as an opaque, *ordered* text blob. That makes
field order a load-bearing part of the contract: the same run serialized with
fields in a different order produces a different digest, even though the content
is identical. This section pins that order so a verifier can detect reordering
and an emitter has an authority to conform to.

### Where the `@U-VCT` line comes from

Unlike `@EMRA`/`@GMRO` (consumed as *inputs*) and `@OOS` (emitted by
`skills/shared/oos_regime_validator.py::generate_oos_toon`), the `@U-VCT|â€¦`
scorecard line is **not produced by a deterministic repo function**. It is
emitted by the U-VCT skill as the terminal line of a run, per the skill
convention "every U-VCT run ends with the TOON block as the last line." The
engine (`uvct-enhanced`, `engine_version` recorded per-row, e.g.
`u-vct-v4.1.0`) renders a human report and an internal snapshot hash; it does
not serialize this compact line. **Consequence:** until a deterministic
serializer exists (tracked separately), field order is governed by emitter
convention, not by code â€” so this written contract IS the invariant.

### Canonical field sequence (frozen)

Top-level fields are pipe-delimited (`|`) and MUST appear in this relative
order. The list opens with the literal sentinel `@U-VCT`. Fields that do not
apply to a given run (e.g. trade-leg detail on a `NO_TRADE`) are **omitted, not
reordered** â€” present fields always preserve this sequence.

```
@U-VCT | T | W | SPOT | TIER | EDGE | CAT | REG | M2b | POL | GEX | GARCH | CF | VIA | DECISION | SIZE | CONF | HASH
```

| #  | Key      | Meaning                                              |
|----|----------|------------------------------------------------------|
| 0  | `@U-VCT` | sentinel (literal)                                   |
| 1  | `T`      | ticker                                               |
| 2  | `W`      | run week / date (`YYYY-MM-DD`)                       |
| 3  | `SPOT`   | underlying spot at run                               |
| 4  | `TIER`   | Five-Tier classification + label                     |
| 5  | `EDGE`   | probability edge (points)                            |
| 6  | `CAT`    | catalyst status (state, event, days-to)             |
| 7  | `REG`    | HMM regime (state â†’ OOS call, transition)           |
| 8  | `M2b`    | M2b-LOCAL blend (bw, tcs adj, size mult)            |
| 9  | `POL`    | policy divergence (CB, size mult)                   |
| 10 | `GEX`    | gamma exposure (regime, call/put walls, flip)       |
| 11 | `GARCH`  | volatility forecast (Ïƒ percentile, p)               |
| 12 | `CF`     | Cornish-Fisher (Î³ skew, Îº kurt, mult, label)        |
| 13 | `VIA`    | viable structure + POP                               |
| 14 | `DECISION`| trade decision (`NO_TRADE` / structure)             |
| 15 | `SIZE`   | position size (% of cap)                             |
| 16 | `CONF`   | confidence                                           |
| 17 | `HASH`   | engine internal snapshot hash (NOT the toon-sha256) |

**Intra-field order also matters.** Several fields carry comma-separated
sub-tokens (e.g. `M2b:bw0.72,tcs+0.15,sz1.00x`). Because the blob is opaque,
sub-token order is equally load-bearing and equally convention-governed; the
serializer (when built) must freeze it too.

**`HASH` is not circular.** Field 17 is the engine's internal snapshot hash
(the legacy `compute_snapshot_hash`, ~16 hex chars), which is computed *before*
and is independent of the `toon-sha256-v1` digest taken *over* this canonical
line. The toon-sha256 hashes the line including its `HASH:` field; it does not
hash itself.

### Provenance note for verifiers

This sequence was captured from the first live `toon-sha256-v1` row
(`RUN-20260530-MU-fed3eb41`, `engine_version u-vct-v4.1.0`) and frozen here. If
the U-VCT skill's emitted order ever diverges from this table, that is an
emitter regression (or a deliberate `uvct-toon-v2` bump with an explicit field
sort), NOT something to reconcile silently in the hasher.
