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

5. **qmd awareness** — the client's qmd `coaching-personas` collection is refreshed
   automatically by `reconcile_qmd_persona_index` (in
   `shared-utils/provision-persona-index.sh`) on every install/update. It repoints
   the collection at the CANONICAL personas dir and re-indexes (BM25 only —
   furnace-safe). **Never** let it point at the skill-bundled folder
   (`~/.openclaw/skills/22-…/personas`), which is frozen at the build snapshot.
   This is the break that made one client answer "no new personas since March."

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

## Quick procedure

```bash
# 1-2. Build the blueprint + add the SET key (Skill 22 pipeline does this).
#      Verify the two counts already match:
find 22-book-to-persona-coaching-leadership-system/personas -mindepth 1 -maxdepth 1 -type d | wc -l
python3 -c 'import json;print(len(json.load(open("22-book-to-persona-coaching-leadership-system/persona-categories.json"))["personas"]))'

# 3-4. Rebuild + publish the index INCREMENTALLY (embeds only the new persona):
shared-utils/prebuilt-index/build-and-publish.sh --persona-id <new-slug>
#      (or --reindex-all — still incremental via HASH-SKIP. Dry-run first with --dry-run.)

# 5. Prove the triad (the N38 gate) is green before you commit:
python3 23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py --only consistency

# 6. qmd refresh + re-wire happen automatically on the client's next update.
```

---

## Why this exists

In June 2026, **sixteen** personas (38 → 54) were added to the SET while one
client's agent still answered *"no new personas since March."* Three independent
breaks produced that one symptom:

1. **BREAK 1** — the agent answered persona-inventory questions from a frozen
   `qmd` cache pointed at the skill-bundled folder, which no pipeline step ever
   refreshed. Closed by `reconcile_qmd_persona_index` (artifact 5) + the N16 hard
   rule (*inventory answers from `persona-categories.json`, never qmd*).
2. **BREAK 2** — the SET had no per-box version stamp, so drift was silent and
   un-rewired. Closed by the `.persona-set-version` sentinel + `_SET_CHANGED`
   re-wire (artifacts 2 & 6).
3. **BREAK 3** — the prebuilt asset was rebuilt + manifest-bumped by hand, lagging
   the source by days, with no CI gate. Closed by `build-and-publish.sh` (the
   missing automation) + the count-triad N38 assertion and CI guard (artifacts
   3, 4 & the gate).

This checklist makes all three impossible to forget.
