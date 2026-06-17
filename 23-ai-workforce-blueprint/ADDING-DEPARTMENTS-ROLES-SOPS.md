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

It **HARD-FAILS (exit 5)** on any drift, runs in CI on every PR/commit
(`.github/workflows/qc-static.yml`), runs in the onboarding QC gate
(`scripts/qc-system-integrity.sh` CHECK X.12), and a client build **refuses to
run** against a drifted repo (`lib-onboarding-state.sh` `oc_repo_consistency_ok`).
If you add/rename a department, role, SOP, or persona and DON'T update every
related source, your commit fails here until you do.

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
