---
name: avatar-alchemist
description: Turns one completed brand-intake interview into the full brand-intelligence package — 40 generators across 7 subsystems (Avatar Core, Awareness, Bios, Tone, Facebook Ads with 13 ad sets, Booking Bots, Landing/Hero) → 16 named deliverables (37 documents), delivered as labeled markdown in ~/Downloads. Fully local: no n8n, no Airtable, no Google Drive, no Slack/Gmail — the client's own model providers only, never Anthropic. A Book/Brand version selector runs FIRST: version=brand runs this 40-stage pipeline; version=book routes to the separate Avatar Alchemist Book skill (53) or parks fail-closed "book-skill-not-available". Every process rule is a fail-closed Python prover with a negative test; a run cannot claim "done" without a signed provenance certificate. Trigger with "run avatar alchemist", "brand intelligence package", "build my avatar documents", or "avatar alchemist for <brand>".
version: 1.1.2
---

# Avatar Alchemist — Brand Intelligence Engine (Skill 52)

The OpenClaw conversion of the 233-node "Avatar Alchemist Brand Intelligence" n8n
workflow. It replaces **192 plumbing nodes** (40 Airtable reads, 37 Drive nodes, 16
HTML converters, 16 base64 nodes, 16 Doc-copy REST calls, Slack, Gmail, the webhook)
with **baked prompt assets + a local artifact store + one Python foreman + a labeled
drop into `~/Downloads`**. The 41 LLM calls become **40 skill stages** run by sub-agents
on the **client's own providers** (the disconnected `o3` orphan is dropped).

> The 40-generator method captured in `MASTERDOC.md` is **SACRED** — never floored,
> reordered, or reinterpreted. Every rule below is machine-enforced by a fail-closed
> prover, never advisory.

## What this skill produces / owns

- `MASTERDOC.md` — the anonymized canonical IP: the 7 subsystems, all 40 generators, the
  per-artifact bands, the 13 restored ad-set categories, and the Book/Brand selector.
- `AA-PIPELINE-MANIFEST.json` — the digest-verified 40-stage DAG (waves, deps, floors,
  deliverables) — the single source of truth for the foreman and the content prover.
- `AVATAR-MANIFEST.json` — the fail-closed enforcement phases (`P-AV-*`) + auto-fail codes
  (`AF-AV-*`); every code has a negative fixture.
- `prompts/<40 stage dirs>/{system.md, methodology.md, user.md}` — the 40 baked generators,
  provider-agnostic, grouped by subsystem, each mapped to its deliverable.
- `intake/{intake-schema.json, INTAKE-TEMPLATE.md}` — the version selector (question 0) +
  both question sets.
- `scripts/` — the foreman (`aa_director.py`), the provers, the packager, the negative suite.
- `entry.sh` — the ONLY sanctioned front door (deps → bypass-scan incl. egress-scan →
  env-credential-name scan → hash-pin → nonce + per-run foreman signing key). `aa_director.py`
  RE-VERIFIES all of this in-process at dispatch regardless of the nonce's provenance.

## The 7 subsystems / 40 generators (see MASTERDOC.md for the full spec)

| Subsystem | Generators | Count |
|---|---|---|
| (a) Avatar Intelligence Core | Q1–30 · Q31–32 · Rewrite Avatar · Answer-9-Questions | 4 |
| (b) Awareness System | Problem/Solution/Product-Aware + 3 pt2 shopping-behavior | 6 |
| (c) Bios | Brand Bio · Product Bio | 2 |
| (d) Tone System | Blended Tone + 4 tone styles (**shared-utils/tone-writing-core**) | 5 |
| (e) Facebook Ad System | 13 ad sets · Audience Generator · Top-39 · Headline/Primary-Text | 16 |
| (f) Booking Bots | Bot Prep · Booking · Post-Booking · Rescheduling | 4 |
| (g) Landing / Hero | Hero page · Landing image prompts · Image Prompt Writer (39) | 3 |

The tone subsystem is the canonical **shared tone/writing core** at
`shared-utils/tone-writing-core/` — the same module skills 53 (Book) and 54 (Anthology)
reference. This skill bakes a lockstep copy and proves it with `verify_tone_core_sync.py`.

## How it runs — one governed path, never a second build path

```
bash 52-avatar-alchemist/entry.sh <RUN_DIR>            # deps → bypass-scan → egress-scan →
                                                        # env-cred-scan → hash-pin → nonce + key
cp <intake.json> <RUN_DIR>/intake.json                 # required: the version gate reads this
python3 52-avatar-alchemist/scripts/aa_director.py \    # foreman: waves → sub-agents → gates
        --run-dir <RUN_DIR> --nonce <RUN_DIR>/.entry-nonce   # add --apply-repairs to opt into R1–R6
```
`aa_director.py` refuses in code (exit 4) to dispatch the brand pipeline for `version=book` —
the version gate is code-coupled to `<RUN_DIR>/intake.json`, not a documented convention.

1. **Gate 0** — `aa_intake_gate.py` proves the intake + the Book/Brand version selector.
   `version=book` routes to skill 53 or parks `book-skill-not-available` (never the brand pipeline).
2. **Foreman** — `aa_director.py` schedules the 40 stages in 20 dependency waves computed
   from the DAG (peak 5 simultaneous authors; `--fast-ads` collapses the ad tail as a
   documented fidelity trade-off, OFF by default), throttled to `min(slots, provider_cap)`,
   dispatching one sub-agent per stage with ONLY its 3 prompt files + resolved deps.
3. **Content gate** — `aa_build_check.py` enforces stripped-word floors, exact counts (39
   image prompts, 3×13 top-39, 12+12+12 headlines, 10 ads/set), the 5,000–19,000-char
   image-prompt band, the 13 restored ad-set categories (R4 — only under `--apply-repairs`), bot-doc structure, the 12-section
   hero page, zero unresolved placeholders, and **zero Anthropic model ids**.
4. **Delivery gate** — `aa_delivery_gate.py` refuses `~/Downloads` below 40/40 receipts whose
   sha256 match the artifact bytes, requires independent QC ≥ 8.5, and issues the **signed
   provenance certificate**. "Done" is claimed only with the certificate path.

## The provers (fail-closed; `sys.exit(2)` on violation; each carries `--self-test`)

| Prover | Gates | AF codes |
|---|---|---|
| `aa_intake_gate.py` | G0-INTAKE, G0-VERSION | AF-AV-INTAKE-INCOMPLETE / VERSION-UNSET / VERSION-MISMATCH / BOOK-SKILL-MISSING |
| `aa_build_check.py` | G-STAGE, G-FLOOR, G-COUNT, G-IMG-BAND, G-ADSET-CAT, G-BOTDOC, G-HERO-12, G-PLACEHOLDER, G-NOANTHROPIC | AF-AV-STAGE-MISSING / FLOOR / COUNT-39 / COUNT-HEADLINE / ADCOUNT / IMG-BAND / UNIQUE-ARTIST / ADSET-CAT / BOTDOC / HERO-12 / PLACEHOLDER / NOANTHROPIC |
| `aa_delivery_gate.py` | G-DELIVER (provenance + certificate) | AF-AV-PROVENANCE / DELIVER-INCOMPLETE |
| `aa_links_gate.py` | G-LINKS (stage-02 podcast/TED links; **fail-soft**: bounded HTTP + 1 retry → verify or `degraded:search`) | AF-AV-LINKS-MISSING |
| `aa_gate_integrity_check.py` | LIVE-gate hash pinning | (refuses modified gates) |
| `test_aa_preflight.py` | the negative suite (drives all self-tests + lockstep) | proves every gate fails its bad fixture |

## Source repairs are OPT-IN (default = faithful to the live workflow)

The source anomalies **R1–R6** (see `REPAIRS.md`) are **OFF BY DEFAULT** so a run reproduces
Trevor's original **live** Avatar Alchemist workflow output exactly. Pass **`--apply-repairs`** to
`aa_director.py` (or set `intake.apply_repairs=true`) to opt into them; the foreman records the mode
in `RUN-LEDGER.json`, prepends a mode banner to every dispatched stage, and the repair-gated content
invariant **G-ADSET-CAT** (R4, the 13 restored ad-set categories) is enforced only in that mode.
**R7 (the Anthropic ban) is NOT a repair** — it is always enforced on a client box and never reverted.
The shipped golden is a `--apply-repairs` reference run (so it exercises G-ADSET-CAT); a default client
run is faithful-to-live.

## Stage-02 link verification (fail-soft, PRD §7 / O4)

Stage `02-avatar-questions-31-32` emits 10 podcasts + 10 TED talks **with links**. `aa_links_gate.py`
does a **bounded HTTP check (short timeout) + one retry** per link and stamps a **`G-LINKS`** receipt:
every link either **verifies** or the stage is marked **`degraded:search`**. It is **fail-soft** — an
offline / unreachable box degrades and never blocks the run — and fail-closed (`AF-AV-LINKS-MISSING`)
only when the stage-02 artifact is empty. Network is OFF by default (`--online` to actually fetch).

## Client-provider rule (binding)

On a client box the skill uses the **client's own configured providers and keys** — never the
operator's, never Anthropic model ids. `preflight.sh` probes the box and writes `model-map.json`
(TIER-A deep authoring / TIER-B structured / SEARCH for stage `02`); `G-NOANTHROPIC` hard-fails
any run whose resolved model id matches `/anthropic|claude/i`. The client's express model choice
is never substituted. This skill is provider-neutral by construction.

## Downstream handoffs (see INSTRUCTIONS.md)

3 bot docs → **Skill 38** (conversational-ai-system); `Top_39_*` + `Facebook_Headline_*` +
`Facebook_Targeting_Intelligence` → **Skill 48** (facebook-ad-generator); images →
**Skill 47** (movie-producer); GHL delivery → **Skill 6**; `version=book` → **Skill 53** (Book).
Post-certification, `scripts/aa_handoff.py` auto-emits this routing as `HANDOFF.json` +
`HANDOFF.md` in the delivery folder (fail-closed; never re-signs the certificate).

## Relationship to Product Bio (Skill 55) — cross-linked, NEVER merged

This skill (52, Avatar Alchemist) carries its OWN "Product Bio" prompt — a strategic product-messaging
specialist persona inside subsystem (c) of the brand-intelligence pipeline, whose embedded bio ships as
part of the package. Skill 55 (Product Bio) is the **standalone** master-brain generator (10 sections /
6,000–7,000 words / 24 named signature closes + its Google-Docs-importable HTML). **Do not merge or
deduplicate the two prompts.** A change to either product-bio prompt MUST flag the sibling skill for
review. Routing disambiguation: a full brand-intelligence package (its embedded bio ships with it) →
**Skill 52**; a standalone master-brain bio → **Skill 55**. This is the reciprocal of the note already
pinned in `55-product-bio/SKILL.md`. Shared procedure: `universal-sops/avatar-craft/`.

## Prerequisites

- python3 (stdlib only — `verify-deps.sh` proves zero external runtime services).
- The client's own model providers configured on the box (Ollama / OpenRouter / etc.).
