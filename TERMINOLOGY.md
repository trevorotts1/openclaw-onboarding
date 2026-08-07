# Terminology — Required Reading for All Agents

This file defines terms that are used across the entire onboarding system. Read this before installing or QC'ing any skill.

---

## GHL / Convert and Flow / GoHighLevel

These names all refer to the SAME platform:
- **GHL** = GoHighLevel (abbreviation)
- **Convert and Flow** = Trevor's white-labeled version of GoHighLevel (client-facing name)
- **GoHighLevel** = the underlying platform

**Backend equivalence:** `app.convertandflow.com`, `app.gohighlevel.com`, and `leadconnectorhq.com` are the same platform regardless of white-label domain. The API host is `https://services.leadconnectorhq.com`; the SPA shell host is `https://app.convertandflow.com` (or the client's own white-label origin). GHL = Convert & Flow = Go High Level — one credential, one platform.

**CRITICAL: GHL does NOT use API keys. It uses Private Integration Tokens (PITs).**

When you see any of these in config files, env vars, or instructions, they ALL mean the same thing — the **LOCATION** Private Integration Token (prefix `pit-`):

| Env-var name | Notes |
|---|---|
| `GOHIGHLEVEL_API_KEY` | **Preferred** — matches `openclaw.json`, `wire-ghl-env.sh`, `ghl_media.py` |
| `GHL_API_KEY` | Legacy short alias |
| `GHL_PIT` | Canonical short alias |
| `GHL_TOKEN` | Alternate alias |
| `GHL_PRIVATE_INTEGRATION_TOKEN` | Explicit full-name alias |
| `PRIVATE_INTEGRATION_TOKEN` | Bare PIT alias |
| `GHL_PRIVATE_TOKEN` | Shortened private-token alias |
| `PIT_TOKEN` | Short PIT alias |
| `GHL_PIT_TOKEN` | Combined PIT alias |
| `GOHIGHLEVEL_LOCATION_PIT` | Explicit LOCATION-PIT name |
| `GHL_LOCATION_PIT` | Explicit LOCATION-PIT short alias |

These are one credential. Every resolver (Python `_PIT_ENV_NAMES`, bash `${GOHIGHLEVEL_API_KEY:=${GHL_API_KEY:-...}}` chains, `wire-ghl-env.sh`) must scan all 11 in the order above (first non-empty wins). **Never conflate with Agency PITs.**

There are TWO types of PIT — keep them SEPARATE:

| Type | Env-var names | Use |
|---|---|---|
| **Location PIT** (the canonical set above) | `GOHIGHLEVEL_API_KEY`, `GHL_API_KEY`, … (11 aliases) | Day-to-day work within a specific location: contacts, media uploads, surveys, funnels, etc. Media uploads **require** the Location PIT. |
| **Agency PIT** | `GOHIGHLEVEL_AGENCY_PIT`, `GOHIGHLEVEL_CONVERTANDFLOW_AGENCY_PIT`, `GHL_AGENCY_PIT` — see the warning below, these are **not** aliases | Agency-wide operations across all sub-accounts. **An Agency PIT 401s on media and location-scoped calls — never merge it into the Location set.** |

> ⚠ **The three agency names above are NOT aliases of one another.** Verified by live read-only
> probes on 2026-08-03: each of `GOHIGHLEVEL_AGENCY_PIT`, `GHL_AGENCY_PIT` and
> `GOHIGHLEVEL_CONVERTANDFLOW_AGENCY_PIT` holds a **different, independently live** agency token.
> All three authenticate against the same agency, so any one of them works for an agency call, but
> they are three separate credentials and rotating one does not rotate the others. **Picking a
> canonical one is an owner decision — do not consolidate, merge, or delete them.**
>
> `GOHIGHLEVEL_AGENCY_API_KEY` was previously listed here as a fourth agency alias. That was wrong
> twice over: it was never a `pit-` token (it held a legacy v1 JWT), and the value was **dead** —
> it returned `401 Invalid JWT`. It was removed from both credential stores on 2026-08-03 and must
> not be reintroduced as an agency-PIT name.

### Where the authoritative value lives

`~/.openclaw/secrets/.env` is **authoritative**. The `env.vars` block in `~/.openclaw/openclaw.json`
holds **copies**, and the copies are what rot — they go stale after a rotation, or get seeded with a
short placeholder that then silently shadows the live credential. A placeholder fails as
`401 Invalid Private Integration token`, which reads like a broken token rather than a missing one.

A location-PIT config-copy sweep on 2026-08-03 found several alias names in `openclaw.json`
env.vars (`GHL_API_KEY`, `GHL_PIT`, `GHL_TOKEN`, `GHL_PIT_TOKEN`, `GHL_PRIVATE_INTEGRATION_TOKEN`,
`GHL_PRIVATE_TOKEN`, `GHL_LOCATION_PIT`, `GOHIGHLEVEL_LOCATION_PIT`) holding that placeholder
rather than a real token, and removed them. **A later full recursive re-scan of the entire
`openclaw.json` tree (not just the top-level `env.vars` block — every `mcp.servers.*.env`, every
nested config path) on 2026-08-03 confirmed zero placeholder-shaped GHL credential copies remain
anywhere in config.** That sweep fixed today's instance; it did not fix the underlying resolver
behavior — a resolver that walks the 11-name chain and takes the first non-empty name will pick up
the NEXT placeholder that gets seeded there just as readily. See "Resolver algorithm" below for the
code-level fix that closes the class of bug, not just today's occurrence.

**Rule: resolve GHL credentials from `secrets/.env`; validate with an authed read before trusting
any name.**

Diagnostic distinction, both observed live: a value that is not a real token returns
`401 Invalid Private Integration token`, whereas a real token that merely lacks reach returns
`403 Forbidden resource` or `401 The token is not authorized for this scope`. **A 403 means the
token is genuine** — do not "fix" it by swapping in a different name.

### Resolver algorithm — placeholder shapes to SKIP, not just document

A doctrine paragraph does not stop a resolver from picking up a placeholder the next time one gets
seeded into `openclaw.json` env.vars (which the gateway process inherits into its live environment
at launch, indistinguishable there from a legitimately-set env var). The fix has to live in the
resolver code, not only in this file. A GHL credential resolver MUST:

1. **Treat a candidate value as a placeholder — and SKIP it, never return it — when it is:**
   shorter than 20 characters (a real PIT/refresh token is far longer); OR begins `pit-abc` /
   `PIT-ABC` (the literal documentation example); OR begins `changeme` / `xxx` / `your-` / `your_`
   (any case); OR ends `_here` / `-here` (any case); OR is wrapped in angle brackets (`<...>`).
2. **Keep scanning remaining aliases in the live environment** when a candidate is placeholder-shaped
   — do not stop at the first non-empty hit if it is a placeholder.
3. **Fall through to a direct read of `secrets/.env`** (and the other canonical env stores) once every
   live-env alias is exhausted (empty or placeholder-shaped), before declaring the credential missing.

The reference implementation is `38-conversational-ai-system/scripts/check-ghl-pit-liveness.sh`'s
`_is_placeholder()` (bash) — proven in production against this exact false-alarm. The same three
shapes are ported (not reinvented) into every Python GHL credential resolver in this repo:
`06-ghl-install-pages/tools/ghl_media.py`, `48-facebook-ad-generator/tools/ghl_media.py`,
`06-ghl-install-pages/tools/ghl_bulk_workflow_enroll.py`, and
`44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/utils/ghl_client.py` each carry
a `_is_placeholder()` matching it. Any NEW GHL credential resolver added to this repo must do the
same — copy the shape rules from one of the four files above, do not invent new ones.

### Company id is an identifier, not a secret

`GHL_COMPANY_ID` and `GOHIGHLEVEL_CONVERTANDFLOW_COMPANY_ID` do hold the same value as each other.
Both were found holding a wrong short value and were corrected on 2026-08-03.

Verify a company id with `GET /companies/{companyId}` — a wrong id returns 403 and the right id
returns 200 with the agency name. **Do not verify it with `GET /locations/search?companyId=...`:**
that endpoint returns 200 even when the companyId is wrong, because the token's own agency is used
regardless, so it cannot detect a bad id.

**Firebase Refresh Token** — `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` — is a THIRD, separate GoHighLevel credential. It is NOT a PIT and is never part of the 11-alias Location PIT set. It is used exclusively for browser-session authentication in Skill 06 and Skill 44 (the builder mints a Firebase `id_token` from this refresh token to reconstruct the SPA session without a UI login). Keep it in its own env-var slot; never merge it into the Location or Agency PIT sets and never confuse it with either.

**Rules:**
- When talking to clients, ALWAYS say "Convert and Flow." Never say "GoHighLevel."
- When talking to agents or in technical docs, "GHL" is acceptable shorthand.
- Never tell a client they need an "API key" for GHL. The correct term is "Private Integration Token" or "PIT."
- Media uploads require the Location PIT, not the Agency PIT.
- The "API key" in GHL settings IS the `pit-` Private Integration Token — one credential, many alias names.

---

## Department Identity Contract (PRD item 1.5)

**`department_id` == canonical slug, everywhere.**

A canonical department slug is:
- all lowercase
- words separated by **hyphens** (no underscores, no spaces)
- **no `dept-` prefix** (the `id` field in `departments.json` keeps `dept-` for legacy Command Center compatibility, but the DB value — the one stored in `workspaces.id`, `persona_selection_log.department_id`, `persona_assignment.department_id`, and passed to `--department` on every script call — is always the bare slug)
- **no `-dept` suffix**

Examples of canonical slugs: `marketing`, `sales`, `billing-finance`, `general-task`, `project-architecture-office`

**This contract is enforced by `shared-utils/canonical_slug.py`** (`canonical_dept_slug()`), which is the Python equivalent of `src/lib/routing/canonical-slug.ts` in the Command Center (`canonicalDeptSlug()`). Both functions MUST produce the same output for the same input.

**Every Python script that reads, writes, or passes a department id MUST route it through `canonical_dept_slug()`:**

| Script | Where it applies |
|---|---|
| `persona-selector-v2.py` | Normalises `--department` arg immediately after `parse_args()` |
| `seed-workspaces.py` | Normalises `raw_id` from `departments.json` before DB insert |
| `sync-md-content-to-db.py` | Normalises agent_key before DB lookup |
| `build-workforce.py` | Normalises `dept_id` in `generate_departments_json()` before writing `slug` field |

**Failure modes this contract prevents:**
- Stickiness rows written under `dept-marketing` never found when reading under `marketing`
- `seed-workspaces.py` and `sync-md-content-to-db.py` producing different ids for the same department from the same build-state
- The selector receiving a UUID from `tasks.ts` when `workspace.slug` is what it needs

**CI grep guard:** the following pattern must produce zero results outside `archive/` and `shared-utils/canonical_slug.py` itself (it detects any script that hard-strips the prefix without using the shared function):

```
grep -rn 'raw_id\[5:\]\|\.removeprefix("dept-")\|re\.sub.*\^dept-' --include="*.py" .
```

**Schema note:** `departments.json` emits `"id": "dept-{slug}"` (with the prefix) for legacy CC compatibility, **and** `"slug": "{slug}"` (bare canonical form). The Command Center's `migrations.ts` and TypeScript components key on `slug`; Python scripts key on the bare `slug` field or strip via `canonical_dept_slug()`. Never store a `dept-` prefixed string in any DB `id` column.

---

## Persona — three distinct meanings (do NOT conflate)

The word **persona** means three unrelated things across the onboarding system. Conflating them is a real, recurring defect (F4.5). Always resolve which one a passage means before acting.

| # | Concept | Canonical name to use | What it actually is | Where it appears |
|---|---|---|---|---|
| 1 | **`dept_label` / `workspace_hint`** | `dept_label` (display) / `workspace_hint` (routing) | A department-head **display name** and a **routing hint** — NOT a coaching persona. Used only to resolve which workspace/department a task belongs to. | The `persona` key in the `/api/tasks/ingest` payload (`SOP-00-Owner-Task-Routing.md`); the `"persona": "dept-<slug>"` / `"qc-specialist-<slug>"` label baked onto `agents` rows by `add-department.sh`; the static kanban ingest labels used by skills 49/53/56/57 (`persona="Book Writer"`, etc.). |
| 2 | **Coaching / leadership persona** (canonical) | **coaching persona** | One of the 81 personas in the `coaching-personas` library, **matched per task, at runtime** by the 5-layer persona selector. This is the ONLY concept `persona-matching-protocol.md` governs. | `23-ai-workforce-blueprint/persona-matching-protocol.md`; `persona-selector-v2.py`; `templates/persona-library/*.md`; `tasks.persona_id` / `persona_assignment` / `persona_selection_log`. |
| 3 | **Buyer / customer persona (avatar)** | **avatar** (or "buyer persona") | The customer/audience profile a piece of copy is written FOR — a target-market model, not a voice the agent adopts. | Skill 52 (Avatar Alchemist) customer avatars; "Big Bold Who" copy sections in skills 49/56. |

**The load-bearing rule (concept 1 vs concept 2):** *Coaching personas are NOT assigned to departments.* A department has a `dept_label`; the coaching persona is chosen **per task, at runtime**, and is **never hardcoded** and **never derived from a department**. Any doc that says "this department's persona is X" is describing a `dept_label` (concept 1), not a coaching persona (concept 2).

**The load-bearing rule (concept 2 vs concept 3):** an **avatar** (concept 3) is WHO the work is for; a **coaching persona** (concept 2) is the voice/methodology the doer works IN. Skill 52's customer-avatar model must never be routed through the coaching-persona selector, and vice versa.

The ingest `persona` key (concept 1) is a documented routing hint — renaming it in doctrine text does **not** change the API; the key name stays for back-compat.

---

## Funnel template library / Automation template library (template-first)

**Funnel template library** — the 38 proven funnel templates shipped by Skill 6 at
`06-ghl-install-pages/funnel-templates/` (categories: buyer, event, lead, retention-followup,
traffic-advanced). Each encodes a `pageStructure`, `copyFramework`, `skill44Widgets`, persona/`books`,
and `whenToUse`/`doNotUseWhen`. Selected by the **funnel matcher** (`tools/funnel_matcher.py`, STEP 0
of every build via `v2_dispatcher.py`).

**Automation template library** — the 28 proven email/SMS/multichannel sequences shipped by Skill 44
at `44-convert-and-flow-operator/automation-templates/`. Selected by the **automation matcher**
(`_matcher/automation_matcher.py`, INSTRUCTIONS Step 0.4). Shared matcher core: `_matcher/flex.py`.

**Funnel→automation link map** — `44-.../automation-templates/_links/funnel-to-automation.json`:
maps each funnel template to its recommended downstream follow-up automations, keyed by
`funnel_template_id` (the canonical v2; the category-keyed `…-link-map.json` is the deprecated v1).

**template-first / reuse-before-reinvent** — the standard that funnel/automation work REUSES a proven
template from these libraries before building net-new. **Flexibility = guide-not-rule:** every
template is a GUIDE and a RESOURCE, never a rule — an explicit owner choice is always honored, net-new
is built only when nothing fits, and the matcher never blocks a build.

**FAB-QC** — the Funnel-&-Automation Build-Quality gate (≥ 8.5): a library-aware, six-dimension
scorer (`shared-utils/fab_qc.py`, rubric `universal-sops/funnel-automation-build-quality-rubric.md`)
that overlays the mechanical floors (ghl_verify for funnels, WF-1..21 for automations).
