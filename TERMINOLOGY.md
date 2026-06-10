# Terminology — Required Reading for All Agents

This file defines terms that are used across the entire onboarding system. Read this before installing or QC'ing any skill.

---

## GHL / Convert and Flow / GoHighLevel

These three names refer to the SAME platform:
- **GHL** = GoHighLevel (abbreviation)
- **Convert and Flow** = Trevor's white-labeled version of GoHighLevel (client-facing name)
- **GoHighLevel** = the underlying platform

**CRITICAL: GHL does NOT use API keys. It uses Private Integration Tokens (PITs).**

When you see any of these in config files, env vars, or instructions, they ALL mean the same thing — a Private Integration Token:
- `GHL_API_KEY`
- `GOHIGHLEVEL_API_KEY`
- `GHL_TOKEN`
- `GHL_PIT`
- `PRIVATE_INTEGRATION_TOKEN`
- `PIT_TOKEN`
- `GOHIGHLEVEL_AGENCY_PIT`

There are TWO types of PIT:
1. **Location PIT** (`GOHIGHLEVEL_API_KEY` / `GHL_API_KEY`) — used for day-to-day work within a specific location (contacts, media uploads, etc.)
2. **Agency PIT** (`GOHIGHLEVEL_AGENCY_PIT`) — used for agency-wide operations across all sub-accounts

**Rules:**
- When talking to clients, ALWAYS say "Convert and Flow." Never say "GoHighLevel."
- When talking to agents or in technical docs, "GHL" is acceptable shorthand.
- Never tell a client they need an "API key" for GHL. The correct term is "Private Integration Token" or "PIT."
- Media uploads require the Location PIT, not the Agency PIT.

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
