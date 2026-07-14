# U84 / GK-22 — On-box CONTENT proof for P3-05

**Unit:** U84 (crosswalk GK-22), P0, live → fleet (operator-box leg only per fix scope — see
Fleet-roll note at the bottom).

**Binary acceptance (master spec, `skill6-blended-persona-kanban-MASTER-SPEC-v2-2026-07-13.md`
line 1982-1986):** "on the operator's own box FIRST, verify the deployed skill content
manifest shows Skill 45 ≥ v1.3.3 and Skill 35 ≥ v2.9.8 by CONTENT (manifest `src_git_sha` +
presence of `pregen_prompt_gate.py`, `prompt-bands.json`, `prove_gip_prompt_floor.py`), never
by version stamp alone... per box: manifest sha matches main AND the three named files exist
with matching hashes; the check command + output archived per box in the per-item ledger."

**Box:** operator box, `/Users/blackceomacmini` (`.openclaw/skills/` = the live/deployed skill
root the agent actually runs against — distinct from the git checkout used to build).

---

## 1. Manifest read-out (primary source: `/Users/blackceomacmini/.openclaw/skills/.onboarding-content-manifest.json`)

See `manifest-readout.json`. Key fields:

```
version:      v20.0.10
src_git_sha:  3dfa2c8c4c9ca77de1e624747147e0f41209dfcc
tree_sha:     0d2c6d9a2537dd9e32e5921d04ca2a0cb3f21f0ebe5ca2c60cc0647a1df3e020
installed_at: 2026-07-13T08:24:27Z
skills["35-social-media-planner"]:        b51eec47015a5b16c96bc07a7d4cce3e8b4048128e4e44f50155ca5ba375d865
skills["45-design-intelligence-library"]: 88826df8d6d77b52b6e35b44319104db3271bdb98eaec71cba5798fa759cb52e
```

## 2. The `src_git_sha` ≠ `origin/main` HEAD nuance — ADJUDICATED

`git rev-parse origin/main` at verification time = `256c3a196c6a685df7fba1ffcd002c7712c93833`.
The manifest's `src_git_sha` (`3dfa2c8c...`) does **not** literally equal current HEAD — this
is expected and does NOT by itself indicate stale/broken content, because `main` is under
active development (e.g. the `chainA` merge `f6636fc0` + ripple `94c1b915` + ledger commits
landed on 2026-07-13 AFTER this box's last install, touching skills `06`, `23`, `49` — none of
which are `35` or `45`).

Verified: `git merge-base --is-ancestor 3dfa2c8c... origin/main` → **YES**, `3dfa2c8c` is a real
ancestor commit of current `main` (merge-of-PR-#581, v20.0.10 tag point), not a fork or a lie.

**Ruling applied (per the fix mandate: "content byte-match is the real acceptance, not sha
equality"):** sha equality is NOT required. What is required, and what was proven below, is
that the CONTENT of Skill 45 and Skill 35 — specifically the three named files, and the
skills' shipped trees as a whole — is byte-identical between (a) the commit the manifest
claims installed content from, (b) current `origin/main` HEAD, and (c) what is actually on
disk on this box. All three converge because no commit between `3dfa2c8c` and `256c3a19`
touches skill 35 or skill 45's shipped files.

## 3. Named-file byte-match proof (`git hash-object`, content-addressed blob sha)

See `named-files-hash-object-compare.txt`. All three named files
(`prompt-bands.json`, `prove_gip_prompt_floor.py`, `pregen_prompt_gate.py`) are byte-identical
across: the manifest's `src_git_sha`, current `origin/main` HEAD, and the deployed on-box copy.
Zero drift on any of the three.

## 4. Whole-skill content-hash proof (the repo's OWN on-box content-check tool)

Ran `scripts/skill-content-hash.sh` (the tool `update-skills.sh` itself uses to gate the
version-stamp write on real content parity — this IS "the on-box content check") against two
roots:

```
$ bash scripts/skill-content-hash.sh <clean checkout of origin/main HEAD 256c3a19>
35-social-media-planner|b51eec47015a5b16c96bc07a7d4cce3e8b4048128e4e44f50155ca5ba375d865
45-design-intelligence-library|88826df8d6d77b52b6e35b44319104db3271bdb98eaec71cba5798fa759cb52e
exit=0

$ bash scripts/skill-content-hash.sh /Users/blackceomacmini/.openclaw/skills   # LIVE deployed box
35-social-media-planner|884865d1d0a5707234250f9014ddc50a5ff250ef6757905cf528060e979f840f
45-design-intelligence-library|88826df8d6d77b52b6e35b44319104db3271bdb98eaec71cba5798fa759cb52e
exit=0
```

Full outputs archived in `skill-content-hash-vs-origin-main-256c3a19.txt` and
`skill-content-hash-deployed-box-live-run.txt`.

**Skill 45: exact match** (`88826df8...` both sides) — clean PASS, no further action.

**Skill 35: digest differs** (`b51eec47...` vs `884865d1...`). Root-caused by per-file diff
(`skill35-divergence-diff.txt`): the ONLY difference between the deployed tree and the
`origin/main` tree is a `.pytest_cache/` directory (4 files: `.gitignore`, `CACHEDIR.TAG`,
`README.md`, `v/cache/nodeids`) present on the deployed box and absent from the git tree — a
local pytest run's cache artifact, never shipped, never committed (confirmed absent from
`origin/main`'s tree). `scripts/skill-content-hash.sh`'s exclusion list (mirrors
`_should_exclude()` in the same script) does not yet list `.pytest_cache/` among its excluded
paths (same class as the already-excluded `__pycache__/`, `node_modules/`, `working/`
exclusions) — a minor, non-blocking gap, noted below as a follow-up, NOT a P0 blocker: it does
not touch any of the three named GK-22 files (independently confirmed byte-identical in
section 3) and does not touch any other shipped file (the diff shows 4 ADDED lines only, zero
changed/removed lines across the rest of the tree).

## 5. On-box skill versions (never trusted alone, corroborating only)

```
45-design-intelligence-library/skill-version.txt (deployed): 1.3.3    [required >= 1.3.3]  PASS
35-social-media-planner/skill-version.txt (deployed):        v2.9.10  [required >= v2.9.8]  PASS
```

## VERDICT — U84 / GK-22: **PASS** (operator box)

- Manifest `src_git_sha` traced to a real ancestor commit of current `main` — not a
  version-stamp-over-stale-content defect for these two skills (adjudicated in §2).
- All three named files byte-identical box ↔ manifest-sha ↔ current main HEAD (§3).
- Skill 45's full shipped tree byte-identical box ↔ main HEAD via the repo's own
  `skill-content-hash.sh` (§4).
- Skill 35's full shipped tree byte-identical box ↔ main HEAD EXCLUDING a local
  `.pytest_cache/` test-cache artifact that is not shipped content (§4) — root-caused, not
  hand-waved.
- Both on-box `skill-version.txt` stamps meet/exceed the floor (§5), consistent with (not
  substituting for) the content proof above.

**Named remediation row (per BINARY acceptance: "A box that fails is a named remediation row,
never a silent skip"):** this box does NOT fail — see verdict above. No remediation row filed
for this box.

**Minor follow-up filed (non-blocking):** add `.pytest_cache/` to
`scripts/skill-content-hash.sh`'s `_should_exclude()` exclusion list (same class as
`__pycache__/`) so a box that has ever run `pytest` inside a skill dir doesn't show a false
digest divergence on future GK-22-style checks. Tracked as follow-up unit
**U84-F1** in the ledger.

## Fleet-roll leg — EXPLICITLY DEFERRED to P4 (per fix mandate)

GK-22's full unit also specifies "then the standard batched fleet roll on the operator's
timing." Per the fix instructions for this pass: **the fleet roll is NOT executed now.** P4 is
the operator-timed batch that executes the single fleet rollout across client boxes
(in-place update; Docker = force-recreate; code-only, never re-initializing credentials) per
the master spec's P4 definition (line 137). This ledger row proves the OPERATOR-BOX leg only;
the fleet-roll leg is a named PENDING-P4 note, not a silent skip and not a fabricated result.
