# Avatar-Craft SOP Cluster (`universal-sops/avatar-craft/`)

The SHARED, cross-department procedure for how any department discovers and drives the **Avatar Alchemist
Engine (Skill 52 — Avatar Alchemist)** end to end: one completed brand-intake interview
-> a Book/Brand version selector -> 40 generators across 7 subsystems -> 16 named deliverables (37
documents) -> a labeled local delivery bundle + a signed provenance certificate.

This cluster is the `universal-sops` face of the capability. It does NOT re-implement the engine. The
authoritative machine spine lives in the skill:

- `52-avatar-alchemist/AA-PIPELINE-MANIFEST.json` — the digest-verified 40-stage DAG (waves, deps,
  floors, deliverables) — the SINGLE SOURCE OF TRUTH for the foreman and the content prover.
- `52-avatar-alchemist/AVATAR-MANIFEST.json` — the fail-closed enforcement phases (`P-AV-*`) + the
  `AF-AV-*` auto-fail table; every code has a negative fixture in `scripts/test_aa_preflight.py`.
- `52-avatar-alchemist/scripts/aa_intake_gate.py`, `aa_build_check.py`, `aa_delivery_gate.py`,
  `aa_gate_integrity_check.py`, `test_aa_preflight.py` — the fail-closed, model-free, stdlib-only
  provers (each with a built-in `--self-test` + golden/attack fixtures). They MEASURE the stripped
  text and the artifact bytes; a model's self-reported count is NEVER trusted.
- `52-avatar-alchemist/scripts/aa_director.py` — the deterministic foreman: it walks the 40-stage
  DAG in dependency waves, dispatches one sub-agent per stage with ONLY its 3 prompt files + resolved
  deps, and runs the content + delivery gates. It refuses to run without the one-time nonce minted by
  the front door.
- `52-avatar-alchemist/entry.sh` — the ONE sanctioned front door (DEPS -> BYPASS-SCAN -> HASH-PIN
  -> NONCE), fail-closed.
- `52-avatar-alchemist/MASTERDOC.md` — the SACRED IP (the 7 subsystems, all 40 generators, the
  per-artifact bands, the 13 restored ad-set categories, and the Book/Brand selector).
- `52-avatar-alchemist/prompts/<40 stage dirs>/{system.md, methodology.md, user.md}` — the 40 baked
  generators, provider-agnostic, grouped by subsystem, each mapped to its deliverable.
- `52-avatar-alchemist/intake/{intake-schema.json, INTAKE-TEMPLATE.md}` — the version selector
  (question 0) + both question sets.

<!-- CRAFT_INTENT_TRIGGERS_V1 -->
## Intent triggers

This craft cluster (`universal-sops/avatar-craft/`) is the execution playbook for the skill(s) below. A specialist reaches for it when the client's plain-language request matches any of these intents — the client never has to name the skill or type its slash command. Source of truth: `23-ai-workforce-blueprint/skill-department-map.json` (Layer D).

| Skill | Reach for this craft when the client says… |
|---|---|
| **52** avatar-alchemist | "build my brand avatar" · "a brand intelligence package" · "who is my customer" · "define my ideal customer" |

Dept-scoped: only the task department's craft is offered. Operate the owning skill per the SOPs in this cluster **before** authoring by hand. Rule-Zero paid-call approval (USD announce + budget cap) still applies. Doctrine: `universal-sops/native-skill-invocation.md`.
<!-- END CRAFT_INTENT_TRIGGERS_V1 -->

## The ONE way in

A brand-intelligence package is built by running, and ONLY by running, the canonical fail-closed front
door, which mints the one-time nonce the foreman requires:

```
bash 52-avatar-alchemist/entry.sh <RUN_DIR>            # deps -> bypass-scan -> hash-pin -> nonce
python3 52-avatar-alchemist/scripts/aa_director.py \   # foreman: waves -> sub-agents -> gates
        --run-dir <RUN_DIR> --nonce <RUN_DIR>/.entry-nonce
```

Running the LLM stages by hand around the front door is the UNGOVERNED path and is refused: the foreman
has no valid nonce and no gate-integrity check, and hand-rolling an Airtable/Drive/Slack/Gmail/n8n
uploader is exactly the plumbing this engine replaced. Delivery is a labeled LOCAL bundle in
`~/Downloads/`. The `AA-GATE-HASHES.json` pin makes the foreman refuse to run against a modified
manifest or prover (anti-lie LIVE-gate).

## Files

| File | What it governs |
|---|---|
| `SOP-AVATAR-01-BRAND-INTELLIGENCE-PACKAGE.md` | What the brand-intelligence package is, when to build it, the Book/Brand selector + the two intake sets, and the full gate contract (`P-AV-*` phases + every `AF-AV-*` code). |

The auto-fail ruleset and phase manifest are NOT duplicated here — they live authoritatively in
`52-avatar-alchemist/AVATAR-MANIFEST.json` (the `P-AV-*` phases + the `AF-AV-*` table) and
`52-avatar-alchemist/AA-PIPELINE-MANIFEST.json` (the 40-stage DAG). This SOP points at them so there
is exactly one source of truth.

## SACRED law (from `52-avatar-alchemist/MASTERDOC.md`)

- The 7 subsystems, all 40 generators, their ORDER, the per-artifact bands, and the 13 restored ad-set
  categories are SACRED — never floored, reordered, or reinterpreted. Every rule is machine-enforced by
  a fail-closed prover, never advisory.
- **Version selector runs FIRST:** question 0 is Book vs Brand (`AF-AV-VERSION-UNSET` /
  `AF-AV-VERSION-MISMATCH`). `version=brand` runs the 40-stage pipeline; `version=book` routes to the
  separate Avatar Alchemist Book skill (53) or PARKS fail-closed `book-skill-not-available`
  (`AF-AV-BOOK-SKILL-MISSING`) — it is NEVER served by the brand pipeline.
- **Measured counts (self-report ignored):** exactly 39 image prompts / top-39 (3x13) (`AF-AV-COUNT-39`);
  12 + 12 + 12 headlines (`AF-AV-COUNT-HEADLINE`); 10 ads per set (`AF-AV-ADCOUNT`); the 5,000-19,000
  stripped-char image-prompt band (`AF-AV-IMG-BAND`); no repeated artist/photographer token
  (`AF-AV-UNIQUE-ARTIST`); the 13 restored ad-set categories (`AF-AV-ADSET-CAT`); bot-doc structure
  (`AF-AV-BOTDOC`); the 12-section hero page (`AF-AV-HERO-12`); per-artifact stripped-word floors
  (`AF-AV-FLOOR`); zero unresolved placeholders (`AF-AV-PLACEHOLDER`).
- **Provenance:** 40/40 foreman-attested receipts whose sha256 matches the artifact bytes
  (`AF-AV-PROVENANCE`); no `~/Downloads` write below 40/40 (`AF-AV-DELIVER-INCOMPLETE`); an independent
  QC >= 8.5; a signed provenance certificate issued only on a full pass. **No signed certificate = not
  done.**
- **Client-exact overrides win:** a client-stated exact target (e.g. an explicit word count) is honored
  verbatim and logged on the certificate — never floored, capped, or substituted (fleet-wide absolute
  law).

## Relationship to Product Bio (Skill 55) — cross-linked, NEVER merged

Skill 52 (Avatar Alchemist) carries its OWN "Product Bio" prompt — a strategic product-messaging
specialist inside its brand-intelligence pipeline. Skill 55 is the STANDALONE master-brain Product Bio
generator (10 sections / 6,000-7,000 words / 24 closes). **Do not merge or deduplicate the two
prompts.** A change to either product-bio prompt MUST flag the sibling skill for review. Routing: a
standalone master-brain bio -> Skill 55; a full brand-intelligence package (its embedded bio ships with
it) -> Skill 52.

## Command Center registration (operator action)

The Command Center surfaces this capability as ONE `sops` row so the Triad Rule auto-resolves a "brand
intelligence package" / "avatar alchemist" request to it. NO schema change (a job is a `tasks` row).
Because the mission-control repo is a separate submodule not reachable from the skill worktree,
inserting/refreshing the row is an OPERATOR action at CC install/update time — via
`32-command-center-setup/scripts/add-sop.sh` (or the dashboard `POST /api/sops/import-role-library`).
Suggested row:

- `slug`: `avatar-brand-intelligence-package`
- `name`: `Avatar Alchemist: build the full brand-intelligence package`
- `department`: `marketing`
- `task_keywords`: `avatar alchemist, brand intelligence, brand intelligence package, build my avatar,
  avatar documents, brand voice, tone doc, awareness levels, booking bots, hero landing page`
- `success_criteria`: signed provenance `PROCESS-CERTIFICATE.json` present (40/40 attested, content gate
  PASS, QC >= 8.5); 16 named deliverables assembled; Book/Brand selector honored; labeled local bundle
  in `~/Downloads/`.

## Flexibility = guide-not-rule

The engine is a GUIDE and a RESOURCE for how a department fulfils a brand-intelligence request; honor an
explicit owner choice (logged on the certificate). But the SACRED bands above are enforced by the
provers and are not opinions — a violation is a hard, named `AF-AV-*` auto-fail.

## Client-runtime rule (binding)

The shipped engine on a client box NEVER uses Anthropic / `claude-*` models or operator keys. The 40 LLM
stages run on the CLIENT's own configured provider chain (`52-avatar-alchemist/preflight.sh` probes
the box and writes `model-map.json`: TIER-A deep authoring / TIER-B structured / SEARCH for stage 02).
The deterministic gates (`aa_*.py`) are provider-neutral Python and run identically everywhere;
`G-NOANTHROPIC` (`AF-AV-NOANTHROPIC`) hard-fails any run whose resolved model id matches
`/anthropic|claude/i`. The tone subsystem (stages 04-08) is the canonical **shared tone/writing core**
at `shared-utils/tone-writing-core/`; the skill bakes a lockstep copy and proves it with
`scripts/verify_tone_core_sync.py`.
