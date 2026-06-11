#!/usr/bin/env python3
"""Stage 0 test harness. Run: python3 tests/test_stage0.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import stage0_lock_template as s0  # noqa: E402

REG = s0._load_registry(ROOT / "token_registry.json")
SRC = (ROOT / "tests" / "fixture_marked.html").read_text(encoding="utf-8")

passed = failed = 0


def ok(cond, label):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}")


def expect_raise(fn, needle, label):
    global passed, failed
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        if needle.lower() in str(e).lower():
            passed += 1
            print(f"  PASS  {label}  (raised: {str(e)[:60]})")
        else:
            failed += 1
            print(f"  FAIL  {label}  (wrong msg: {e})")
        return
    failed += 1
    print(f"  FAIL  {label}  (no exception)")


print("Stage 0 — happy path")
template, tmap = s0.lock_template(SRC, REG)
ok(len(tmap) == len(REG), f"all {len(REG)} tokens collapsed")
ok("<!--TOKEN:" not in template and "<!--/TOKEN:" not in template, "no sentinels survive")
ok(all(template.count("{{" + n + "}}") == 1 for n in REG), "each placeholder exactly once")

# Chrome preserved byte-for-byte: strip sentinels+content from source, compare to
# template with placeholders removed -> the static skeleton must match.
import re  # noqa: E402
src_skeleton = s0.PAIR_RE.sub("", SRC)
tpl_skeleton = re.sub(r"\{\{[A-Z0-9_]+\}\}", "", template)
ok(src_skeleton == tpl_skeleton, "static chrome preserved byte-for-byte")

print("Stage 0 — idempotency")
# Re-running on the emitted template: no sentinels, so audit sees zero tokens ->
# missing-token error proves the output can't be re-frozen (it's terminal).
expect_raise(lambda: s0.lock_template(template, REG), "never marked", "frozen output is terminal")

print("Stage 0 — validation failure modes")
expect_raise(lambda: s0.lock_template(SRC.replace("<!--TOKEN:BY_TIER-->", "").replace("<!--/TOKEN:BY_TIER-->", ""), REG),
             "never marked", "missing token rejected")
dup = SRC.replace("<!--/TOKEN:S_OPEN-->", "<!--/TOKEN:S_OPEN-->X<!--TOKEN:S_OPEN-->Y<!--/TOKEN:S_OPEN-->")
expect_raise(lambda: s0.lock_template(dup, REG), "more than once", "duplicate token rejected")
unknown = SRC.replace("<!--TOKEN:BY_TIER-->", "<!--TOKEN:BOGUS_TOKEN-->").replace("<!--/TOKEN:BY_TIER-->", "<!--/TOKEN:BOGUS_TOKEN-->")
expect_raise(lambda: s0.lock_template(unknown, REG), "unknown token", "unknown sentinel rejected")
unbalanced = SRC.replace("<!--/TOKEN:S_INTEGRITY-->", "")  # last token, no open follows
expect_raise(lambda: s0.lock_template(unbalanced, REG), "unclosed", "unbalanced sentinel rejected")
nested = SRC.replace("<!--TOKEN:OPEN_ROWS-->", "<!--TOKEN:OPEN_ROWS--><!--TOKEN:S_HITRATE-->")
expect_raise(lambda: s0.lock_template(nested, REG), "nested", "nested sentinel rejected")

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
