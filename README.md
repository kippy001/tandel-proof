# Tandel Quant Analytics — Public Proof Ledger

**Every call we publish is hash-stamped into this repository before its outcome is
known. This repo exists so you can check that claim instead of trusting it.**

The [scorecard](https://kippy001.github.io/tandel-proof/) is rendered as a pure
function of [`ledger/ledger.json`](ledger/ledger.json) — same data in, same bytes
out, byte-for-byte. The ledger is append-only, every analysis (TOON) is archived
verbatim in [`ledger/toons/`](ledger/toons/), and each row carries a SHA-256
integrity stamp over a published canonical form. Because this history lives in
version control, edits, reorderings, and deletions are public events.

## Audit it (two minutes)

```bash
git clone https://github.com/kippy001/tandel-proof
cd tandel-proof
python3 ledger/verify_integrity.py ledger/ledger.json   # recompute every digest
python3 ledger/run_gates.py                             # full suite, incl. byte-identical re-render
```

No dependencies — Python standard library only. Don't trust our verifier either:
[VERIFICATION.md](VERIFICATION.md) specifies the canonicalization in seven steps and
includes a ~15-line independent verifier you can write yourself.

## What's here

| Path | What it is |
|---|---|
| `index.html` | The public scorecard (copy of `ledger/canonical_source.html`, the signed-off render) |
| `ledger/ledger.json` | Single source of truth — append-only call ledger with integrity stamps |
| `ledger/toons/` | Archived one-line analysis records (TOONs), hashed verbatim |
| `ledger/verify_integrity.py` | Recomputes every `toon-sha256-v1` digest + field-order check |
| `ledger/run_gates.py` | All integrity gates: schema, derived stats, round-trip, byte-identical render, tests |
| `ledger/stage*.py`, `ledger/build/` | The full render pipeline + frozen template (SHA-256s pinned in `build/freeze_manifest.json`) |
| `VERIFICATION.md` | The spec: canonicalization profile, DIY verifier, what verification proves and doesn't |

Rows stamped `v0` are **illustrative seed data** — excluded from verification and from
the scorecard. Only `toon-sha256-v1` rows are claims.

> **Correction, 4 Oct 2026.** Until this date the scorecard showed 13 `v0` rows — a 7–3 closed
> record, a 70% hit rate, +1,025 net edge and two "live" positions from 27 May — and counted them in
> its headline numbers, under a heading that said every call was verifiable. They were illustrative
> seed placeholders from the page's design, **never calls**. The scorecard now shows and counts
> `toon-sha256-v1` rows only (`stage3_render.py --verified-only`); the 13 rows remain in
> `ledger/ledger.json`, unedited, because nothing leaves the ledger. The verified record today is one
> row: MU, 30 May 2026, NO_TRADE (avoided).

## What this proves — and what it doesn't

Verification proves the record is *authentic*: what you see today is byte-identical
to what was stamped, and the scorecard's numbers are mechanically derived from those
calls. It does **not** prove future performance, suitability, or profitability for
you. Sample size and tier context are always displayed.

## The weekly read

The desk publishes a verified weekly read — free.
**[Get it here](https://tandel-quant-analytics.kit.com/0464c66f7c)** (double opt-in;
unsubscribe any time).

---

*This is impersonal market research and education distributed on a regular schedule
to all subscribers — not personalized investment advice, not a recommendation, and
not tailored to any individual. Options involve substantial risk and are not
suitable for all investors. Tandel Quant Analytics is not a registered investment
adviser. Past results, verifiable or not, do not predict future outcomes.*

*© 2026 Tandel Quant Analytics. You are welcome to clone this repository and run the
verification code for audit purposes. Please do not republish the content.*
