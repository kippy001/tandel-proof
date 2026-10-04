# How to Audit a U-VCT Run Hash
**Tandel Quant Analytics · verification spec v1**

*The claim: every U-VCT call is hash-stamped into an append-only ledger before its
outcome is known, and the public scorecard is a pure function of that ledger. This
page is everything you need to check that claim yourself. Trust nothing below —
run it.*

---

## What gets published

For every engine run, three artifacts:

1. **The TOON** — a one-line structured record of the call (`ledger/toons/{run_id}.toon`):
   ticker, date, tier, edge, regime, the decision (including `NO_TRADE`), size, confidence.
2. **The ledger row** (`ledger/ledger.json`) — the same run with outcome fields and an
   integrity stamp: `{"scheme": "toon-sha256-v1", "value": "<64-char hex>"}`.
3. **The scorecard** — the public page. It is regenerated **byte-for-byte** from
   `ledger.json` by a frozen template (SHA-256s pinned in `ledger/build/freeze_manifest.json`).
   The page cannot say anything the data doesn't.

Rows stamped `v0` are **illustrative seed data** — excluded from verification and, since
4 Oct 2026, from the page (see the correction in README.md). Only `toon-sha256-v1` rows
are claims.

## The hash (scheme `toon-sha256-v1`)

The digest is SHA-256 over a *canonical preimage* of the archived TOON
(canonicalization profile `uvct-toon-v1`):

1. Decode the file as strict UTF-8 (invalid bytes = verification failure).
2. Strip one leading BOM if present.
3. Normalize line endings: `CRLF`/`CR` → `LF`.
4. Strip trailing spaces/tabs from each line.
5. Collapse the end of file to exactly one trailing newline.
6. Prepend the domain-separation prefix `uvct-toon-v1\n`.
7. SHA-256 the UTF-8 bytes; lowercase hex.

The result must equal `integrity.value` in the ledger row. Additionally, the
`@U-VCT` line's **field order is frozen** — a reordered TOON fails verification even
if its digest is recomputed, so a row can't be quietly restated as "the same data,
rearranged."

## Verify it — one command

From the repository root:

```bash
python3 ledger/verify_integrity.py ledger/ledger.json   # exit 0 iff every v1 row verifies
python3 ledger/run_gates.py                             # full suite: integrity + scorecard purity
```

Python standard library only; no dependencies to install.

## Verify it — don't trust our verifier either

~15 lines, stdlib only:

```python
import hashlib, json, pathlib

def canonical(raw: bytes) -> bytes:
    text = raw.decode("utf-8")                      # strict
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    body = "\n".join(ln.rstrip(" \t") for ln in text.split("\n")).rstrip("\n") + "\n"
    return b"uvct-toon-v1\n" + body.encode("utf-8")

ledger = json.loads(pathlib.Path("ledger/ledger.json").read_text("utf-8"))
for row in ledger["rows"]:
    if row["integrity"]["scheme"] != "toon-sha256-v1":
        continue                                    # v0 = illustrative, not a claim
    raw = pathlib.Path(f"ledger/toons/{row['run_id']}.toon").read_bytes()
    ok = hashlib.sha256(canonical(raw)).hexdigest() == row["integrity"]["value"]
    print(row["run_id"], "OK" if ok else "MISMATCH")
```

## What this proves — and what it doesn't

**Proves:** the call you see today is byte-identical to the call that was stamped;
the scorecard's numbers are mechanically derived from those calls; nothing was
edited, reordered, or deleted after the fact (the ledger is append-only and lives
in version control — history is public).

**Does not prove:** that future performance resembles the record, that the
methodology is profitable for you, or anything about trades not on the ledger.
A verified record of N calls is exactly that — N, with tier context, is always
displayed. This is research, not financial advice.

## Worked example

Run `RUN-20260530-MU-fed3eb41` (MU, week of 2026-05-30): the engine classified it
**Tier 1 / NO_EDGE** (edge 1.74%) and published **NO_TRADE, size 0.00%** — restraint
is a call too, and it's stamped like every other. Recompute its hash with the
snippet above and compare it to the ledger row.

---

*Spec stability: `uvct-toon-v1` and `toon-sha256-v1` are frozen identifiers. Any
future change ships as `-v2` alongside, never replacing, v1 history. The reference
verifier (`ledger/verify_integrity.py`) and this page are versioned together.*
