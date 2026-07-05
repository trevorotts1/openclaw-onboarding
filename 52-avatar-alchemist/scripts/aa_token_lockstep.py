#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aa_token_lockstep.py — prompt↔manifest artifact-token lockstep prover (Skill 52).

FIX-AVATAR-03. Before this prover, 38 of 40 prompts used the unresolvable generic
`{{artifact.upstream}}` token — the foreman had no way to know WHICH upstream
each slot wanted, so a wrong-slot injection (or a silently-dropped dependency)
would pass every other gate: SACRED-chain corruption with no alarm. Every generic
token is now a NAMED `{{artifact.<stage_id>}}`, and this gate proves, per stage:

  * MEMBERSHIP: every `{{artifact.X}}` token names a real stage_id that is a
    member of THAT stage's depends_on (no undeclared / wrong-slot injection).
  * COVERAGE ("token count == deps consumed"): every declared depends_on member
    is actually consumed by at least one token (no dead / mis-wired dependency).
  * NO GENERIC: not a single `{{artifact.upstream}}` (or any non-stage-id
    artifact token) survives anywhere.

Together MEMBERSHIP + COVERAGE mean the set of distinct artifacts a stage injects
is EXACTLY its declared depends_on — the prompt and the digest-verified DAG can
never silently disagree again.

stdlib only. Exit 0 = lockstep holds, 2 = violation, 3 = usage/IO error.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

SKILL_ROOT = Path(__file__).resolve().parent.parent
_ARTIFACT_TOKEN_RE = re.compile(r"\{\{artifact\.([^}]*)\}\}")
_PROMPT_FILES = ("system.md", "methodology.md", "user.md")

# The four tone-style prompts (04-07) are BYTE-FOR-BYTE canonical shared IP,
# synced across skills 52/53/54 by verify_tone_core_sync.py (Trevor's standing
# decision). They cannot carry skill-specific named artifact tokens without
# forking that shared core, so they keep the generic `{{artifact.upstream}}` —
# but here it is SANCTIONED, not unresolvable: aa_director resolves it
# POSITIONALLY against depends_on order, which is unambiguous ONLY because the
# upstream-token count must equal len(depends_on) (enforced below). 08-blended-tone
# is NOT exempt: it already uses fully-named tokens and obeys the normal rules.
_SANCTIONED_UPSTREAM_STAGES = {
    "04-tone-style-1", "05-tone-style-2", "06-tone-style-3", "07-tone-style-4",
}


def _manifest_path() -> Path:
    return SKILL_ROOT / "AA-PIPELINE-MANIFEST.json"


def _stage_tokens(prompts_dir: Path, sid: str) -> List[str]:
    toks: List[str] = []
    for fn in _PROMPT_FILES:
        p = prompts_dir / sid / fn
        if p.is_file():
            toks += [m.group(1).strip() for m in _ARTIFACT_TOKEN_RE.finditer(p.read_text(encoding="utf-8"))]
    return toks


def check(manifest: Dict[str, Any], prompts_dir: Path) -> List[Tuple[str, str]]:
    violations: List[Tuple[str, str]] = []
    stage_ids = {s["stage_id"] for s in manifest["stages"]}
    for s in manifest["stages"]:
        sid = s["stage_id"]
        deps = list(s.get("depends_on", []))
        dep_set = set(deps)
        tokens = _stage_tokens(prompts_dir, sid)
        distinct = set(tokens)
        # Shared tone-core stages (04-07): {{artifact.upstream}} is SANCTIONED but
        # must be POSITIONALLY resolvable -> its count must equal len(depends_on),
        # and no OTHER (named) artifact token may appear (that would be ambiguous
        # alongside the positional upstream).
        if sid in _SANCTIONED_UPSTREAM_STAGES:
            up = sum(1 for t in tokens if t == "upstream")
            named = [t for t in distinct if t != "upstream"]
            if up != len(deps):
                violations.append(("AF-AV-TOKEN-UNRESOLVABLE",
                                    f"{sid}: {up} sanctioned {{{{artifact.upstream}}}} token(s) but "
                                    f"depends_on has {len(deps)} — not positionally resolvable"))
            if named:
                violations.append(("AF-AV-TOKEN-NOT-A-DEP",
                                    f"{sid}: shared tone-core stage mixes named artifact token(s) {named} "
                                    f"with the positional {{{{artifact.upstream}}}} — ambiguous"))
            continue
        # NO GENERIC / valid stage id
        for t in distinct:
            if t == "upstream" or t not in stage_ids:
                violations.append(("AF-AV-TOKEN-UNRESOLVABLE",
                                    f"{sid}: prompt references {{{{artifact.{t}}}}} which is not a real "
                                    f"stage_id (generic/unresolvable token)"))
        # MEMBERSHIP: every named artifact token must be a declared dependency
        for t in distinct:
            if t in stage_ids and t not in dep_set:
                violations.append(("AF-AV-TOKEN-NOT-A-DEP",
                                    f"{sid}: injects {{{{artifact.{t}}}}} but {t} is NOT in its depends_on "
                                    f"{sorted(dep_set)} — wrong-slot / undeclared injection"))
        # COVERAGE: every declared dependency must be consumed by a token
        for d in dep_set:
            if d not in distinct:
                violations.append(("AF-AV-TOKEN-DEP-UNCONSUMED",
                                    f"{sid}: depends_on lists {d} but no {{{{artifact.{d}}}}} token consumes "
                                    f"it — dead / mis-wired dependency"))
    return violations


# ---------------------------------------------------------------------------
def run_self_test() -> int:
    import tempfile
    ok = True

    # (1) the REAL tree must be in perfect lockstep right now.
    manifest = json.loads(_manifest_path().read_text(encoding="utf-8"))
    real = check(manifest, SKILL_ROOT / "prompts")
    if not real:
        print("SELF-TEST ok: all 40 real prompts are in lockstep with the manifest "
              "(membership + coverage; only the shared tone-core stages 04-07 keep the "
              "sanctioned, positionally-resolvable {{artifact.upstream}}).")
    else:
        ok = False
        print(f"SELF-TEST FAIL: real tree has {len(real)} lockstep violation(s):")
        for c, m in real[:8]:
            print(f"  [{c}] {m}")

    # (2) synthetic negatives on an isolated mini tree.
    mini = {"stages": [
        {"stage_id": "01-a", "depends_on": []},
        {"stage_id": "02-b", "depends_on": ["01-a"]},
        {"stage_id": "03-c", "depends_on": ["01-a", "02-b"]},
    ]}
    with tempfile.TemporaryDirectory() as td:
        pd = Path(td)
        def _w(sid, body):
            (pd / sid).mkdir(parents=True, exist_ok=True)
            (pd / sid / "user.md").write_text(body, encoding="utf-8")

        # clean: 02-b consumes 01-a; 03-c consumes 01-a + 02-b
        _w("01-a", "no upstream here.")
        _w("02-b", "uses {{artifact.01-a}}.")
        _w("03-c", "uses {{artifact.01-a}} and {{artifact.02-b}}.")
        if not check(mini, pd):
            print("SELF-TEST ok: a clean mini tree passes.")
        else:
            ok = False; print(f"SELF-TEST FAIL: clean mini tree flagged: {check(mini, pd)}")

        # generic token survives -> AF-AV-TOKEN-UNRESOLVABLE
        _w("02-b", "uses {{artifact.upstream}}.")
        codes = {c for c, _ in check(mini, pd)}
        if "AF-AV-TOKEN-UNRESOLVABLE" in codes:
            print("SELF-TEST ok: a surviving {{artifact.upstream}} is REJECTED.")
        else:
            ok = False; print(f"SELF-TEST FAIL: generic token not caught: {codes}")

        # inject a non-dep -> AF-AV-TOKEN-NOT-A-DEP
        _w("02-b", "uses {{artifact.01-a}} and {{artifact.03-c}}.")
        codes = {c for c, _ in check(mini, pd)}
        if "AF-AV-TOKEN-NOT-A-DEP" in codes:
            print("SELF-TEST ok: injecting an artifact NOT in depends_on is REJECTED (wrong-slot guard).")
        else:
            ok = False; print(f"SELF-TEST FAIL: non-dep injection not caught: {codes}")

        # unconsumed dep -> AF-AV-TOKEN-DEP-UNCONSUMED
        _w("02-b", "uses {{artifact.01-a}}.")
        _w("03-c", "uses only {{artifact.01-a}}.")  # drops 02-b
        codes = {c for c, _ in check(mini, pd)}
        if "AF-AV-TOKEN-DEP-UNCONSUMED" in codes:
            print("SELF-TEST ok: a declared-but-unconsumed dependency is REJECTED (coverage guard).")
        else:
            ok = False; print(f"SELF-TEST FAIL: unconsumed dep not caught: {codes}")

        # sanctioned tone-core stage: upstream count MUST equal len(deps)
        tone_mini = {"stages": [
            {"stage_id": "01-a", "depends_on": []},
            {"stage_id": "04-tone-style-1", "depends_on": ["01-a"]},  # 1 dep
        ]}
        _w("04-tone-style-1", "modeled on [{{artifact.upstream}}\n{{artifact.upstream}}]")  # 2 tokens
        codes = {c for c, _ in check(tone_mini, pd)}
        if "AF-AV-TOKEN-UNRESOLVABLE" in codes:
            print("SELF-TEST ok: a sanctioned tone stage with upstream_count != len(deps) is REJECTED "
                  "(not positionally resolvable).")
        else:
            ok = False; print(f"SELF-TEST FAIL: tone upstream-count mismatch not caught: {codes}")
        # and the matching case passes
        tone_ok = {"stages": [
            {"stage_id": "01-a", "depends_on": []},
            {"stage_id": "02-b2", "depends_on": []},
            {"stage_id": "04-tone-style-1", "depends_on": ["01-a", "02-b2"]},
        ]}
        _w("02-b2", "root.")
        if not check(tone_ok, pd):
            print("SELF-TEST ok: a sanctioned tone stage with 2 upstream tokens ↔ 2 deps passes "
                  "(positionally resolvable, shared-IP exemption).")
        else:
            ok = False; print(f"SELF-TEST FAIL: valid sanctioned tone stage flagged: {check(tone_ok, pd)}")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Avatar-Alchemist prompt↔manifest artifact-token lockstep prover.")
    ap.add_argument("--manifest")
    ap.add_argument("--prompts-dir")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return run_self_test()
    try:
        manifest = json.loads(Path(args.manifest or _manifest_path()).read_text(encoding="utf-8"))
        prompts_dir = Path(args.prompts_dir) if args.prompts_dir else (SKILL_ROOT / "prompts")
        violations = check(manifest, prompts_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: {exc}")
        return 3
    if violations:
        print(f"FAIL: {len(violations)} prompt↔manifest lockstep violation(s):")
        for code, msg in violations:
            print(f"  VIOLATION [{code}] {msg}")
        return 2
    print("PASS: all prompts in lockstep with the manifest (membership + coverage; shared tone-core "
          "stages 04-07 keep the sanctioned positional {{artifact.upstream}}).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
