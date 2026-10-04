#!/usr/bin/env python3
"""Stage 3 test harness. Run: python3 tests/test_stage3.py"""
import copy
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import stage3_render as s3            # noqa: E402
from stage1_load_validate import load_ledger  # noqa: E402
from stage2_derive import derive     # noqa: E402

# Path B (enhancement #5): these are generator-correctness regression tests, so
# they run against the PINNED 13-row seed fixture, never the live (growing)
# ledger.json. canonical_source.html was frozen from this exact seed, so the
# byte-identity proof below holds permanently while ledger.json is free to grow.
LEDGER = load_ledger(str(ROOT / "tests" / "fixtures" / "ledger_seed13.json"))
CANON = (ROOT / "canonical_source.html").read_text(encoding="utf-8")

passed = failed = 0


def ok(cond, label):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}")


if __name__ == "__main__":
    print("Stage 3 - round-trip (the core proof)")
    seed = s3.render(LEDGER)  # frozen build_meta by default
    ok(seed == CANON, "seed ledger + frozen build_meta is byte-identical to canonical_source.html")
    ok(hashlib.sha256(seed.encode()).hexdigest()
       == hashlib.sha256(CANON.encode()).hexdigest(), "rendered SHA-256 matches canonical")
    ok("\r" not in seed, "output is LF-only (no CRLF)")
    ok(re.search(r"\{\{[A-Z_]+\}\}", seed) is None, "no template tokens left unfilled")

    print("Stage 3 - purity and determinism")
    ok(s3.render(LEDGER) == s3.render(LEDGER), "render is deterministic (two calls identical)")
    alt = s3.render(LEDGER, build_meta="30 May 2026, 09:00 ET")
    ok(alt != CANON, "changing build_meta changes the page")
    ok(re.search(r"\{\{[A-Z_]+\}\}", alt) is None, "alt build_meta still fills every token")
    ok(CANON.replace(s3.FROZEN_BUILD_META, "30 May 2026, 09:00 ET", 1) == alt,
       "build_meta is the ONLY render-time variable (page minus masthead is invariant)")

    print("Stage 3 - reflects ledger changes (genuine function, not a copy)")
    # append a brand-new open row -> open count grows, new id appears, still lossless-shaped
    m = copy.deepcopy(LEDGER)
    m["rows"].append({
        "run_id": "RUN-20260530-AAPL-deadbeef", "ticker": "AAPL", "opened": "2026-05-30",
        "structure": "bull put spread", "tier": "T2", "state": "open", "status": "live",
        "commit": "abc1234",
        "integrity": {"scheme": "illustrative-snapshot-v0", "value": "deadbeefcafef00d",
                      "engine_version": None, "canonicalization": None},
    })
    pg = s3.render(m)
    ok('data-id="RUN-20260530-AAPL-deadbeef"' in pg, "appended row renders in output")
    ok(derive(m)["open_count"] == 3, "derived open_count reflects the append")
    ok(re.search(r"\{\{[A-Z_]+\}\}", pg) is None, "appended-ledger render fills every token")

    # flip a win to a loss -> a negative P/L cell with U+2212 appears for that ticker
    m2 = copy.deepcopy(LEDGER)
    for r in m2["rows"]:
        if r["run_id"] == "RUN-20260512-SMH-d0c3a7b8":
            r["result"] = "loss"; r["pl"] = -160
    ok('<td class="num neg">\u2212160</td>' in s3.render(m2), "flipped win->loss renders a U+2212 neg cell")

    print("Stage 3 - footer integrity count (genuine function of integrity.scheme)")
    # Seed is 13 illustrative / 0 verified -> canonical footer states exactly that.
    ok("Hash integrity: 0 of 13 cryptographically verified \u00b7 13 illustrative" in seed,
       "seed footer shows 0 of 13 verified / 13 illustrative")
    # Flip one seed row to a verified scheme -> the count moves with the data.
    mv = copy.deepcopy(LEDGER)
    mv["rows"][0]["integrity"] = {
        "scheme": "toon-sha256-v1",
        "value": "a" * 64, "engine_version": "u-vct-4.1.1", "canonicalization": "uvct-toon-v1",
    }
    pgv = s3.render(mv)
    ok("1 of 13 cryptographically verified \u00b7 12 illustrative" in pgv,
       "flipping one row to toon-sha256-v1 bumps verified, drops illustrative")
    # Helper: illustrative clause dropped when every row is verified; empty stated plainly.
    ok(s3.fmt_integrity(14, 0, 14) == "14 of 14 cryptographically verified",
       "fmt_integrity drops illustrative clause at full coverage")
    ok(s3.fmt_integrity(0, 0, 0) == "no calls recorded yet", "fmt_integrity handles empty ledger")

    print("Stage 3 - verified-only public render (§23.82)")
    # The live ledger's one verified row on top of the 13 illustrative seed rows:
    # the state the public page was in when it showed 7-3 / 70% / +1,025.
    live = load_ledger(str(ROOT / "ledger.json"))
    v1 = [r for r in live["rows"] if r["integrity"]["scheme"] == "toon-sha256-v1"]
    mixed = copy.deepcopy(LEDGER)
    mixed["rows"] += copy.deepcopy(v1[:1])
    st = derive(mixed, verified_only=True)
    ok((st["wins"], st["losses"], st["scored"], st["avoided"], st["open_count"],
        st["withdrawn_count"]) == (0, 0, 0, 1, 0, 13),
       "verified_only derives from the one v1 row and withdraws the 13 illustrative")
    pub = s3.render(mixed, "4 Oct 2026, 12:00 ET", verified_only=True)
    ok(not any(r["run_id"] in pub for r in LEDGER["rows"]),
       "no illustrative Run ID appears on the public render")
    ok(v1[0]["run_id"] in pub, "the verified row is rendered")
    ok('<div class="val">—<small>%</small></div>' in pub,
       "hit rate with nothing scored is an em-dash, not 0%")
    ok("correction, 4 Oct 2026: 13 illustrative seed rows" in pub,
       "the footer states the correction and its date")
    ok(s3.render(mixed) == s3.render(mixed, verified_only=False),
       "the default render is unchanged (it still shows every row)")
    ok(derive(LEDGER, verified_only=True)["integrity_total"] == 0,
       "the seed fixture alone has nothing verified to show")

    print("Stage 3 - formatting helpers")
    ok(s3.fmt_date("2026-03-28") == "28 Mar", "fmt_date zero-pads day, abbreviates month")
    ok(s3.fmt_date("2026-05-02") == "02 May", "fmt_date handles single-digit day")
    ok(s3.fmt_signed_int(1025) == "+1,025", "fmt_signed_int: comma group + leading plus")
    ok(s3.fmt_signed_int(-410) == "\u2212410", "fmt_signed_int: U+2212 for negatives")
    ok(s3.fmt_edge(13.1) == "+13.1 pt", "fmt_edge positive")
    ok(s3.fmt_edge(0.0) == "0.0 pt", "fmt_edge zero has no sign")
    ok(s3.fmt_edge(-5.0) == "\u22125.0 pt", "fmt_edge negative uses U+2212")

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
