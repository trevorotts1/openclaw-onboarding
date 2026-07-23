# ADDING A PERSONA — the propagation checklist (NEVER skip a step)

> Sibling doctrine to `ADDING-DEPARTMENTS-ROLES-SOPS.md`. Referenced by **N38** in
> `AGENTS.md`. If you are adding a coaching/leadership persona to the fleet, this
> is the binding checklist. The N38 consistency gate hard-fails (rc=5) if you
> skip the count steps, and CI blocks the merge.

A persona is **not "added"** when its blueprint dir exists. It is added when **all
six** of these coupled artifacts agree and have shipped. Adding the blueprint
alone gives clients a persona that is *matchable-but-vector-less* (semantic search
can't find it), or one their agent **will never even mention** (a frozen
conversational cache). Both happened in June 2026 — see *Why this exists* below.

---

## The six coupled artifacts (they MUST move together)

1. **Blueprint** — `22-book-to-persona-coaching-leadership-system/personas/<slug>/persona-blueprint.md`.
   Built by the Skill-22 pipeline (`pipeline/orchestrator.py`).

2. **SET** — add the `<slug>` key to
   `22-book-to-persona-coaching-leadership-system/persona-categories.json`
   (`domain` / `perspective` / `custom` tags) and bump `lastUpdated`.
   **This is what the MATCHER reads** (`persona-selector-v2.py` →
   `list_available_personas` builds the entire candidate universe from
   `data["personas"].keys()`). A persona absent from the SET is structurally
   unreachable.

3. **Prebuilt INDEX (incremental — NO furnace)** — run
   `shared-utils/prebuilt-index/build-and-publish.sh`. It downloads the CURRENT
   published asset and runs `gemini-section-indexer.py`, whose md5 **HASH-SKIP**
   guard embeds ONLY the new/changed persona and HASH-SKIPs every unchanged one.
   Persona #55 = ~tens of vectors, **never** the full corpus. **NEVER `--force` a
   full re-embed of all personas** — that is the token furnace this whole system
   exists to avoid.

4. **MANIFEST** — `build-and-publish.sh` bumps
   `shared-utils/prebuilt-index/INDEX-MANIFEST.json`: `persona_count`,
   `canonical_persona_count`, `chunk_count`, `sha256`, `gz_size_bytes`,
   `source_db_bytes`, `release_tag`, `build_date`, `persona_set_md5`. It then
   publishes the new `gemini-index.sqlite.gz` GitHub Release asset. Commit the
   bumped manifest. **Clients DOWNLOAD this asset; they never recompute it.**

5. **Client-side persona awareness** — persona inventory is resolved from the
   canonical SET file (`persona-categories.json`) via `persona-selector-v2.py`
   (`list_available_personas`). Clients get the updated SET + prebuilt Gemini
   index on every install/update (via `provision-persona-index.sh`). The
   persona-selector builds its candidate universe from the SET keys — the
   canonical source that is always in lockstep with the published asset. This
   prevents the June 2026 break where a client answered "no new personas since
   March" because inventory came from a stale cache instead of the SET.

6. **Re-wire** — on update, `reconcile_persona_assets` writes a
   `.persona-set-version` sentinel and exports `_SET_CHANGED=1` when the SET grew;
   `install.sh` / `update-skills.sh` then run `rewire_on_persona_set_change`, which
   (a) regenerates every dept `governing-personas.md`
   (`create_role_workspaces.py --refresh-personas-only`) so the Command Center
   dashboard surfaces the new persona, and (b) busts persona stickiness
   (`persona-selector-v2.py --mode bust-stickiness`) so a stale sticky pick can't
   keep winning for up to `ANTI_STALENESS_THRESHOLD` (5) dispatches.

---

## The gate that enforces this

`23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py` (the N38 single
source of truth) hard-fails (**rc=5**) if the persona-SET COUNT triad disagrees:

```
blueprint dirs  ==  persona-categories.json keys
                ==  INDEX-MANIFEST.persona_count
                ==  INDEX-MANIFEST.canonical_persona_count
```

This rides the existing wiring at no extra cost:
`scripts/qc-system-integrity.sh` CHECK X.12, build-preflight
`lib-onboarding-state.sh oc_repo_consistency_ok()` (a client build **refuses** to
run against a drifted repo), and CI `.github/workflows/qc-static.yml`. A second
CI guard — `.github/workflows/persona-set-asset-consistency-guard.yml` — enforces
the same triad at the PR boundary on the exact files that move when a persona is
added.

**If the gate is red, the persona did NOT ship — finish the checklist.**

---

## Quick procedure — the ONE command

The Skill-22 book pipeline writes the new persona to the **workspace** only. Do
**not** hand-edit the six artifacts. One atomic, re-runnable command moves the
repo blueprint dir + `persona-categories.json` + the INDEX-MANIFEST + the release
asset together, and **refuses to complete (rolling back) unless the count triad
and the published asset all agree at the same N**:

```bash
# On the OPERATOR box (workspace + Gemini key + gh auth):
22-book-to-persona-coaching-leadership-system/pipeline/publish-personas-to-fleet.sh
#   --dry-run    prove the count/asset math without spending embed credits
#   --no-asset   sync repo + manifest COUNTS only (hermetic; used by the tests)
```

It sanitizes each blueprint of operator-local paths, validates the tags against
the controlled vocabulary, delta-embeds via `build-and-publish.sh` (HASH-SKIP —
never a full furnace), publishes the asset, and verifies sha256 before pointing
the fleet at it. Then review the diff and commit the three repo paths.

**Prove it's green before you commit** (the same triad CI + pre-commit run):

```bash
22-book-to-persona-coaching-leadership-system/pipeline/assert-personas-published.sh --repo-only
python3 23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py --only consistency
```

The pre-commit hook and the `update-skills.sh` pre-roll path run this guard
automatically; SET delivery + re-wire happen on the client's next update. See
`22-…/PIPELINE.md` → *Adding books → publishing personas to the fleet* for the
full runbook. If you must operate the underlying asset step directly (advanced),
`shared-utils/prebuilt-index/build-and-publish.sh --persona-id <slug>` still
exists — but `publish-personas-to-fleet.sh` is the mandated wrapper that keeps
all four artifacts in lockstep.

---

## Why this exists

In June 2026, **sixteen** personas (38 → 54) were added to the SET while one
client's agent still answered *"no new personas since March."* Three independent
breaks produced that one symptom:

1. **BREAK 1** — the agent answered persona-inventory questions from a frozen
   conversational cache pointed at the skill-bundled folder, which no pipeline
   step ever refreshed. Closed by the N16 hard rule (*inventory answers ONLY
   from `persona-categories.json`, the SET file — the matcher's ground truth*).
2. **BREAK 2** — the SET had no per-box version stamp, so drift was silent and
   un-rewired. Closed by the `.persona-set-version` sentinel + `_SET_CHANGED`
   re-wire (artifacts 2 & 6).
3. **BREAK 3** — the prebuilt asset was rebuilt + manifest-bumped by hand, lagging
   the source by days, with no CI gate. Closed by `build-and-publish.sh` (the
   missing automation) + the count-triad N38 assertion and CI guard (artifacts
   3, 4 & the gate).

This checklist makes all three impossible to forget.
