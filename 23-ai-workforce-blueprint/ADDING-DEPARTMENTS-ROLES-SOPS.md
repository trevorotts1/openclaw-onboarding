# Adding a Department, Role, SOP, or Persona — Contributor Checklist

**Read this BEFORE you touch the workforce blueprint.** This repo carries **six
independent sources of truth** about departments / roles / SOPs / personas. They
used to drift silently — six departments once shipped **unbuildable** because
nothing cross-checked the floor against the rosters, and eleven floor
departments silently fell back to the generic `['leadership']` persona pool
because their canonical ids were missing from the persona maps.

A single gate now makes that **impossible**:

```
python3 23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py
```

The bare invocation runs **TWO gates**:

1. the **5-dimension consistency gate** (floor × roster × library × SOP ×
   persona, **exit 5** on drift); and
2. the **artifact-coverage gate** (v12.25.0 — the *complete check for
   everything*, **exit 6** on drift), which makes sure no floor department, role,
   skill count, bootstrap file, or version marker can silently drift out of a
   **downstream artifact**. See ["The artifact-coverage gate"](#the-artifact-coverage-gate-complete-check-for-everything)
   below.

Both **HARD-FAIL** on any drift, run in CI on every PR/commit
(`.github/workflows/qc-static.yml`), run in the onboarding QC gate
(`scripts/qc-system-integrity.sh` CHECK X.12), and a client build **refuses to
run** against a drifted repo (`lib-onboarding-state.sh` `oc_repo_consistency_ok`,
which fails closed on **any** nonzero rc — 5 *or* 6). If you add/rename a
department, role, SOP, persona, **skill, bootstrap file, or version marker** and
DON'T update every related source, your commit fails here until you do. Run the
sub-gates in isolation with `--only consistency` / `--only artifact`.

---

## The six sources of truth (and the files that own them)

| # | Source of truth | File |
|---|-----------------|------|
| 1 | **FLOOR** — which departments every client gets | `department-naming-map.json` (`.mandatory` + each vertical pack's `universal_primary` dept) |
| 2 | **ROSTERS** — the proposed specialist menu per dept | `suggested-roles/<dept>-suggested-roles.md` |
| 3 | **ROLE LIBRARY** — the pre-written role + Section-9 SOP bodies | `templates/role-library/_index.json` + `templates/role-library/<dept>/<role-slug>.md` |
| 4 | **SOP SOURCE** — where a role's SOPs come from | role-library copy path (canonical, guarded by `sop_boundary_gate.is_canonical_dept`); for `personal-assistant`, the Skill-42 library `42-personal-assistant-library/specialists/` |
| 5 | **PERSONA DOMAINS** — which coaching personas a dept draws from | `build-workforce.py` `create_governing_personas_md` **and** `generate_persona_matrix` (`dept_to_domains`), plus `create_role_workspaces.py` `write_governing_personas_md` (`DEPT_DOMAIN_HINTS`) |
| 6 | **NO ORPHANS** | no roster without a floor/library home; no floor dept the library can't reach |

The gate resolves these using the **exact same functions the build uses**
(`parse_roster`, `library_lookup`, `normalize_dept`, `evaluate_floor`,
`is_canonical_dept`), so a green gate guarantees the build will succeed and a red
gate is a real build failure, not a lint opinion.

---

## The artifact-coverage gate (complete check for everything)

The 5-dimension gate proves every floor dept is internally consistent. The
artifact-coverage gate (`--only artifact`, **exit 6** on drift) proves that no
floor dept, role, skill, bootstrap file, or version can silently fall out of a
**downstream artifact** — the class of drift the first gate doesn't see.

| Dimension | What it guarantees | How it's checked |
|-----------|--------------------|------------------|
| **ORG-CHART** | every floor dept (and its roster roles) is rendered in the org chart | runs the REAL `build-workforce.generate_org_chart` against a synthesized full-floor `selected_departments`, asserts every dept name + roster role appears |
| **ROUTING** | every floor dept has a row in `universal-sops/00-ROUTING.md` (no unrouted dept silently falling back to `general-task`) | runs the REAL `write_universal_routing_map`, asserts a `departments/<dept>/` row per floor dept |
| **COMMAND-CENTER** | every floor dept gets a Kanban column / Telegram topic | runs the REAL `generate_departments_json`, asserts every floor dept slug is present (+ CEO column first) |
| **DREAMING** | every floor dept gets a workspace + `memory/` substrate (the thing dreaming consolidates); dreaming is configured workspace-wide with **no per-dept exclusion list** | asserts `create_department_workspace` is driven by the `selected_departments` loop + creates `memory/`, that `install.sh configure_dreaming` writes the global `memory-core` dreaming config, and that no `DREAMING_DEPARTMENTS`-style per-dept list omits a floor dept |
| **GENERATOR-WIRING** | the org-chart / routing / command-center generators are actually **called** by the build (not just defined) | static call-site check in `build-workforce.py` |
| **BOOTSTRAP** | the core/bootstrap files are consistent: the 6 shipped templates (`IDENTITY`/`SOUL`/`AGENTS`/`USER`/`TOOLS`/`HEARTBEAT`.md) exist at repo root, `MEMORY.md` is **not** committed (it's seeded fresh+empty per agent), and the canonical 7-file enumeration in `Start Here.md` names all seven | file existence + `Start Here.md` scan |
| **SKILLS-COUNT** | `install.sh` active-skill prose == README count == the actual skill-dir tree (active = numbered dirs minus `*-ARCHIVED`), and every active skill has a README inventory row | parse README `**N numbered skill folders**` / `M active + K archived` + inventory rows + `install.sh` `(N active + K archived)` / `The N active skills`, compare to the live tree |
| **VERSION** | every repo-wide version marker agrees with `/version` — the 9-marker `bump-version.sh` set **plus** `cc-compat.json` `onboardingVersion` | reads each marker, compares the normalized semver to `/version` |
| **CONTENT-HASH** | the per-artifact content manifest is **present + current**: every `roles[]`/`sops[]` entry has `content_sha` + `content_version`, each stored `content_sha` equals a freshly recomputed one (manifest not stale vs the live `.md` files), and `render_sha` recomputes with no un-mapped **canonical** `{{TOKEN}}` surviving the neutral render | re-runs the `hash-content-manifest.py` pipeline (`check_manifest`) over the live library files; **exit 6** on any drift — makes a stale manifest impossible to ship |

These mirror the build the same way the 5-dimension gate does: ORG-CHART /
ROUTING / COMMAND-CENTER / DREAMING are all **derived at build time** by iterating
`selected_departments`, so there is no static per-dept dict to diff. The gate
SYNTHESIZES a full-floor `selected_departments` (from `load_canonical_floor()` +
the vertical-pack one-liners — the same metadata the build uses) and runs the
**real generator functions**, so a generator that drops a dept, hardcodes a
subset, or is unwired **fails**. The drift you must fix:

- **version drift** → run `./scripts/bump-version.sh vX.Y.Z` (rolls all 9 markers
  atomically) and update `cc-compat.json` `onboardingVersion` (or use
  `scripts/release.sh`, which rolls both).
- **skills-count drift** → after adding/removing/archiving a skill dir, update the
  two README counts (`**N numbered skill folders**` and `M active + K archived`),
  add the inventory-table row for a new skill, and update the `install.sh` prose
  (`(N active + K archived)` and `The N active skills`).
- **bootstrap drift** → never delete a shipped core template; never commit a
  `MEMORY.md` at repo root (it must be per-client empty); keep the `Start Here.md`
  7-file list complete.
- **org-chart / routing / command-center / dreaming drift** → never replace a
  generator's `selected_departments` loop with a hardcoded subset, and keep every
  generator wired into the build.
- **content-hash drift** → after adding or editing ANY role / SOP / department,
  run `python3 scripts/hash-content-manifest.py` to re-stamp the manifest (details
  in ["Per-artifact content hashes + change detection"](#per-artifact-content-hashes--change-detection-v12270) below). The
  gate FAILS if the stored `content_sha` no longer matches the file.

The adversarial fixtures
(`scripts/test-artifact-coverage.sh`) plant exactly one drift per dimension and
prove the gate exits 6 — a green gate that never fails is worthless.

---

## Per-artifact content hashes + change detection (v12.27.0)

Each canonical artifact (role, dept-level SOP, department) carries a **content
hash + version** in `templates/role-library/_index.json`, so the system can tell —
per role, per SOP, per department — whether a given client's built copy is **out of
date** vs the current library content. This is what drives "this client's role X is
out of date → refresh it".

### The hash is computed on the CANONICAL TEMPLATE, never on rendered client bytes

This is the whole point. Every library `.md` is a pure template full of `{{TOKENS}}`
(`{{COMPANY_NAME}}`, `{{ISO_DATE}}`, `{{GENERATION_DATE}}`, …). At instantiation
those tokens become per-client values **and** volatile values (`datetime.now()`), so
a hash of the *rendered client file* differs for **every client and every day** even
when the library is unchanged → massive false positives. Instead, `content_sha` is
computed over the **template** with `{{TOKENS}} left intact** (the tokens **are** the
canonical content), via:

1. strip the provenance HTML-comment marker line(s) (self-reference removal),
2. normalize the volatile header fields — the `**Last updated:**` and `**Version:**`
   values become `<NORMALIZED>` (so a re-generation that only re-dates the header is
   **not** a content change),
3. CRLF→LF and strip one trailing newline,
4. `content_sha = "sha256:" + sha256(bytes)`.

Two identical templates therefore produce the **same** `content_sha` regardless of
which client they serve — zero per-client false positives. A `render_sha`
cross-check (forward-render through `fill_tokens()` with a fixed neutral config + a
frozen clock) is a build-time **determinism** assertion only (it proves no un-mapped
canonical token survives a render); **detection compares `content_sha`**.

A **department**'s `content_sha` is the sha over its sorted `(member-slug,
member content_sha)` list, so a dept goes stale when a member is added/removed/renamed
**or** any member role's content changes. `content_version` defaults to `1.0.0` and
auto patch-bumps when `content_sha` changes between manifest runs.

### The three tools

| Tool | Role |
|------|------|
| `scripts/hash-content-manifest.py` | **Generator.** Idempotent in-place stamper (modeled on `tag_role_classes.py`) — stamps `content_sha`/`render_sha`/`content_version`/`content_hashed_at` onto every `roles[]` entry, adds the top-level `sops[]` array for `<dept>/sops/*.md`, computes the per-dept `content_sha`, and writes the self-describing `content_manifest{}` header. **Run it LAST in the library-build chain** (after `generate-role-library.py` / `tag_role_classes.py`) and after editing any role/SOP. `--dry-run` / `--summary` / `--check`. |
| build pipeline (`create_role_workspaces.py` + `build-workforce.py`) | **Build record.** At instantiation, stamps a `workforce-provenance` HTML-comment marker into each `how-to.md` carrying the **source** `content_sha`/`content_version` copied from the manifest, and rolls them up into `.workforce-build-state.json` → `artifactProvenance.{roles,depts,sops}`. The build-state is the fast detection path; the per-file marker is the ground-truth fallback. |
| `scripts/detect-stale-artifacts.py` | **Detector.** Given a client workspace + the manifest, reports per artifact: **CURRENT** (source sha == manifest sha), **STALE** (source sha changed since build), **MISSING** (manifest offers it, client never built it), **ORPHAN** (client built a key not in the manifest), **UNTRACKED** (built before provenance shipped). `--json`; **exit 0** = all current, **10** = actionable drift (feeds the refresh queue), **2** = load error. Read-only on the client side. |

### When you edit a role / SOP / department — you MUST re-stamp

After adding or changing any role/SOP/dept `.md`, run:

```bash
python3 23-ai-workforce-blueprint/scripts/hash-content-manifest.py
```

The consistency gate's **CONTENT-HASH** dimension (`--only artifact`, exit 6) and the
`qc-static.yml` `hash-content-manifest.py --check` step both **fail** if you skip
this — a stale manifest cannot ship. Because the hash is canonical-source based, your
edit changes **only** that artifact's `content_sha`, which makes `detect-stale-artifacts.py`
flag **only** the clients built from the old sha, for **only** that artifact —
precise, per-artifact, false-positive-free fan-out. The refresh flow
(`update-skills.sh`, after `migrate-existing-workforce.sh`) runs the detector and
writes the actionable items to `.artifact-refresh-queue.json` for re-instantiation
via the same additive library-fill path.

---

## Scenario A — Adding a NEW department to the floor

A new floor department touches **all six** sources. Do every step:

1. **FLOOR** — add the dept to `department-naming-map.json`:
   - a mandatory dept → add an entry under `mandatory` with a
     `suggested_roles_file` field that names its roster file;
   - a vertical-pack universal-primary dept → add it to the pack's
     `auto_add_departments` with `universal_primary: true` and a
     `base_suggested_roles` file (and, preferably, ship a dedicated
     `<dept>-suggested-roles.md`).
   - Keep `scripts/department-floor.py` `HARDCODED_MANDATORY` in lockstep (it is
     the broken-install fallback — same id list as the naming map).
2. **ROSTER** — create `suggested-roles/<dept>-suggested-roles.md`. Use the
   `### N. Role Name` header format (or the `| # | Slug | Title | Type | Purpose |`
   table format — both parse). Give each role an explicit **`**Slug:**`** line
   that matches its role-library slug **exactly** (this removes all ambiguity;
   see Scenario B).
3. **ROLE LIBRARY** — add a template `templates/role-library/<dept>/<role-slug>.md`
   for every roster role (≥3 KB, with its Section-9 SOP block), then regenerate
   `_index.json` so every role appears with the correct `dept` / `slug` / `path`.
4. **SOP SOURCE** — because the dept now has a `templates/role-library/<dept>/`
   tree, `sop_boundary_gate.is_canonical_dept` will treat it as canonical and the
   build will COPY (not author) its SOPs. That is correct — do NOT route a
   canonical dept through LLM authoring. (Only `personal-assistant` uses a
   sibling Skill-42 library instead.)
5. **PERSONA DOMAINS** — add the dept's **canonical id** as a key to ALL THREE
   persona maps, mapped to real `persona-categories.json` domain tags (valid
   tags: `marketing, sales, leadership, finance, operations, communication,
   copywriting, mindset, productivity-systems, coaching, strategy-innovation,
   personal-development`). NEVER leave it to fall back to `['leadership']`:
   - `scripts/build-workforce.py` → `create_governing_personas_md` `dept_to_domains`
   - `scripts/build-workforce.py` → `generate_persona_matrix` `dept_to_domains`
   - `scripts/create_role_workspaces.py` → `write_governing_personas_md` `DEPT_DOMAIN_HINTS`
   > **Watch the id namespace.** `selected_departments` keys on the **canonical**
   > dept id (`billing-finance`, `customer-support`, `web-development`,
   > `communications`, `openclaw-maintenance`, `social-media`,
   > `paid-advertisement`, …) — NOT the legacy short ids
   > (`billing`/`support`/`webdev`/`comms`/…). Add the canonical id; keep any
   > legacy id only as an alias.
6. **RUN THE GATE** until it is green:
   ```
   python3 23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py
   ```

---

## Scenario B — Adding (or renaming) a ROLE in an existing department

1. **ROLE LIBRARY** — add/rename `templates/role-library/<dept>/<role-slug>.md`
   and regenerate `_index.json` (correct `dept` / `slug` / `title` / `path`).
   - **Slugs must be clean ASCII.** Never let a real em-dash leak in as the
     escaped bytes `\342\200\224` — that corruption once made two sales roles
     unresolvable. Use a plain hyphen.
2. **ROSTER** — add the role to `suggested-roles/<dept>-suggested-roles.md` with
   an explicit **`**Slug:** <exact-library-slug>`** line right under the
   `### N. Name` header.
   - The roster name is often shorter than the library title (e.g. roster
     "SDR" vs library `sdr-sales-development-rep`, or "Account Executive" vs
     `account-executive-full-cycle`). The name normalizer cannot always bridge a
     qualifier suffix, so the explicit `**Slug:**` line is what makes the role
     resolve. If you skip it, the gate's `[LIBRARY/SOP]` check fails.
3. **RUN THE GATE.** The `[LIBRARY/SOP]` failure lists the exact unresolved
   role slug; fix the `**Slug:**` line or the library entry until it resolves.

A role you remove from a roster must also leave the library index clean (no
orphan library entry the floor never reaches → `[ORPHAN-FLOOR]` / `[ORPHAN-ROSTER]`).

---

## Scenario C — Adding or changing an SOP

- **Canonical dept (has a `templates/role-library/<dept>/` tree):** the SOP lives
  **inside** the role's `<role-slug>.md` (its Section-9 block) — that template IS
  the SOP source, copied + token-personalized at build time. Edit the template,
  not a separate authoring queue. The boundary gate (`sop_boundary_gate.py`)
  REFUSES LLM authoring for canonical depts on purpose (token economics +
  determinism), so a canonical dept must never appear in the
  `sop-research-manifest.json` authoring path.
- **`personal-assistant`:** SOPs come from the Skill-42 library
  (`42-personal-assistant-library/specialists/<NN-slug>/SOP/`). Add the SOP there
  and make sure the PA roster slug matches the specialist folder slug.
- Either way, **every floor dept's roles must resolve an SOP source** — the gate's
  `SOP` column goes `NO` the instant a role has neither a library template nor a
  sibling-library folder.

---

## Scenario D — Adding or changing a persona / persona domain

- New coaching personas live in
  `22-book-to-persona-coaching-leadership-system/persona-categories.json` (each
  carries one or more `domain` tags from the 12-tag vocabulary).
- A department draws personas via its **domain tags**, not by naming a persona.
  So when you want a dept to pull a new persona, add the relevant **domain tag**
  to that dept's entry in the three persona maps (Scenario A step 5). NEVER add a
  dept to only one or two of the three maps — the gate's `PERSONA` column requires
  the dept id in ALL THREE (`create_governing_personas_md`,
  `generate_persona_matrix`, `DEPT_DOMAIN_HINTS`).

---

## What the gate prints

```
DEPT                          ROSTER LIBRARY  INSTANTIATE   SOP   PERSONA  STATUS
marketing                     yes    yes      15/15 roles   yes   yes      OK
sales                         yes    NO       13/13 roles   NO    yes      DRIFT
...
RESULT: FAIL — N entity(ies) with drift, M broken relationship(s) (rc=5)
```

- **ROSTER `NO`** → roster file missing or parsed 0 roles (wrong format / wrong filename).
- **LIBRARY `NO`** → ≥1 roster role resolves no library/SOP template (add `**Slug:**` or the template).
- **INSTANTIATE `x/y`** → dry-run materialized x of y roster roles; x<y means a role failed to materialize.
- **SOP `NO`** → a role has no SOP source, or the dept isn't a canonical/sibling-library dept.
- **PERSONA `NO`** → the dept id is missing from one or more persona-domain maps (→ `['leadership']` fallback).

Run `--json` for machine-readable detail. The `FAILURE DETAIL` block names the
exact dept, category, and the unresolved slugs.

---

## Tests

- `scripts/test-repo-consistency.sh` — fixture tests proving the gate **bites**:
  it PASSES on the clean repo and FAILS when a roster / role / persona-mapping /
  library slug is broken in an isolated sandbox. Run it after any change here.
- The gate + these tests run in CI (`.github/workflows/qc-static.yml`,
  "Skill 23 repo-consistency gate" step).

**Bottom line:** floor + roster + library + SOP + persona move **together**, or
the gate fails your commit. There is no longer a way to ship an inconsistent
department.
