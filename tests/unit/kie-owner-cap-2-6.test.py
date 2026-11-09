#!/usr/bin/env python3
"""G-7 (fix plan A2, unowned): the owner cap is present for every GPT Image 2.6 route.

The owner ruling (20,000 characters) existed only as prose while `owner_prompt_cap_chars`
was absent from the data, so Skill 74 fell through to the vendor schema and resolved 32,000.
This guard makes the absence loud: every `gpt-image-2-6/*` route in the owner catalog that
Skill 74 actually reads (66-kie-image/models.json, via kie_live_adapter._policy_rows) must
declare a positive integer `owner_prompt_cap_chars`, every such route must resolve to ONE
value, and Skill 71's policy must not carry a second hard-coded copy of it.

Scope note: the ruling names the GPT Image 2.6 prompt cap. `wan/2-6-*` are VIDEO routes with
their own limits and are deliberately out of scope; they are listed in the output so a reader
can see they were considered, not missed.

`--self-test` proves the guard BITES: it runs the same check over a mutated copy of the
catalog with the owner cap removed and requires a FAILURE there. A guard that cannot fail
is exactly the "green test that measures nothing" this fix plan exists to delete.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "66-kie-image" / "models.json"
POLICY = ROOT / "71-blackceo-signature-page" / "references" / "prompt-budget-policy.json"
IN_SCOPE_PREFIX = "gpt-image-2-6/"


def check(catalog_path: Path, policy_path: Path) -> tuple[list[str], list[str], set]:
    """-> (fails, notes, caps). Pure function so the self-test can drive a mutated tree."""
    fails, notes = [], []
    models = json.loads(catalog_path.read_text(encoding="utf-8"))
    rows = [r for r in models.get("models") or []
            if isinstance(r, dict) and str(r.get("canonical_model_id", "")).startswith(IN_SCOPE_PREFIX)]
    if not rows:
        fails.append("no %s route in %s" % (IN_SCOPE_PREFIX, catalog_path))
        return fails, notes, set()

    caps = set()
    for row in rows:
        mid = row["canonical_model_id"]
        cap = row.get("owner_prompt_cap_chars")
        if not (isinstance(cap, int) and not isinstance(cap, bool) and cap > 0):
            fails.append("%s has no positive integer owner_prompt_cap_chars (got %r)" % (mid, cap))
        else:
            caps.add(cap)
    if len(caps) > 1:
        fails.append("the 2.6 routes disagree about the owner cap: %s" % sorted(caps))

    for row in models.get("models") or []:
        if not isinstance(row, dict):
            continue
        mid = str(row.get("canonical_model_id", ""))
        if mid.startswith("wan/2-6-"):
            notes.append("OUT OF SCOPE: %s (video route, not the GPT Image 2.6 ruling)" % mid)

    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    prows = [r for r in policy.get("models") or []
             if isinstance(r, dict) and "gpt-image-2-6" in str(r.get("match"))]
    if not prows:
        fails.append("Skill 71 policy has no gpt-image-2-6 row")
    for row in prows:
        if "max_chars" in row:
            fails.append("Skill 71 policy hard-codes max_chars=%r instead of reading the owner cap"
                         % row["max_chars"])
        src = row.get("max_chars_from") or {}
        if src.get("field") != "owner_prompt_cap_chars":
            fails.append("Skill 71 policy max_chars_from does not read owner_prompt_cap_chars")
    return fails, notes, caps


def self_test() -> int:
    """The negative fixture: remove the cap from one 2.6 route, the guard MUST fail."""
    real_fails, _, _ = check(CATALOG, POLICY)
    if real_fails:
        for f in real_fails:
            print("FAIL G-7 (real tree): " + f)
        return 1
    with tempfile.TemporaryDirectory(prefix="bld002-g7-") as d:
        mutated = Path(d) / "models.json"
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
        for row in data.get("models") or []:
            if isinstance(row, dict) and str(row.get("canonical_model_id", "")).startswith(IN_SCOPE_PREFIX):
                row.pop("owner_prompt_cap_chars", None)
                break
        mutated.write_text(json.dumps(data), encoding="utf-8")
        neg_fails, _, _ = check(mutated, POLICY)
        if not neg_fails:
            print("FAIL G-7 SELF-TEST: a 2.6 route with no owner cap was NOT caught — the guard does not bite")
            return 1
        print("PASS G-7 SELF-TEST: removing the owner cap from a 2.6 route fails the guard (%d finding)"
              % len(neg_fails))
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--self-test" in argv:
        return self_test()
    for p in (CATALOG, POLICY):
        if not p.is_file():
            print("FAIL G-7: missing %s" % p)
            return 1
    fails, notes, caps = check(CATALOG, POLICY)
    for n in notes:
        print(n)
    for f in fails:
        print("FAIL G-7: " + f)
    if fails:
        return 1
    print("PASS G-7: owner_prompt_cap_chars present and equal (%s) for every %s route"
          % (sorted(caps), IN_SCOPE_PREFIX))
    return 0


if __name__ == "__main__":
    sys.exit(main())
