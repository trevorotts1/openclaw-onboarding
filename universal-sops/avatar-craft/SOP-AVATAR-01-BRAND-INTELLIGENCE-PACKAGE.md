# SOP-AVATAR-01: BUILD THE BRAND-INTELLIGENCE PACKAGE

**Cluster:** Avatar-Craft Rules (`universal-sops/avatar-craft/`)
**Master authority:** `52-avatar-intelligence/AVATAR-MANIFEST.json` (`P-AV-*` phases + the `AF-AV-*` table) + `52-avatar-intelligence/AA-PIPELINE-MANIFEST.json` (the 40-stage DAG) + `52-avatar-intelligence/MASTERDOC.md` (the SACRED IP)
**Owning department:** Marketing
**Owning roles:** Brand Positioning Specialist (drives the front door), routed by the Chief Marketing Officer
**Canonical entry:** `52-avatar-intelligence/entry.sh` (then the foreman `scripts/aa_director.py`)
**Gates this SOP satisfies:** AF-AV-INTAKE-INCOMPLETE, AF-AV-VERSION-UNSET, AF-AV-VERSION-MISMATCH, AF-AV-BOOK-SKILL-MISSING, AF-AV-STAGE-MISSING, AF-AV-FLOOR, AF-AV-COUNT-39, AF-AV-COUNT-HEADLINE, AF-AV-ADCOUNT, AF-AV-IMG-BAND, AF-AV-UNIQUE-ARTIST, AF-AV-ADSET-CAT, AF-AV-BOTDOC, AF-AV-HERO-12, AF-AV-PLACEHOLDER, AF-AV-NOANTHROPIC, AF-AV-PROVENANCE, AF-AV-DELIVER-INCOMPLETE

---

## 0. WHAT THIS ARTIFACT IS

The **brand-intelligence package** is the full Avatar Alchemist output: from ONE completed brand-intake
interview, 40 generators across 7 subsystems produce 16 named deliverables (37 documents), delivered as
labeled markdown in `~/Downloads/`. The 7 subsystems:

| Subsystem | Generators | Count |
|---|---|---|
| (a) Avatar Intelligence Core | Q1-30, Q31-32, Rewrite Avatar, Answer-9-Questions | 4 |
| (b) Awareness System | Problem/Solution/Product-Aware + 3 pt2 shopping-behavior | 6 |
| (c) Bios | Brand Bio, Product Bio | 2 |
| (d) Tone System | Blended Tone + 4 tone styles (**shared-utils/tone-writing-core**) | 5 |
| (e) Facebook Ad System | 13 ad sets, Audience Generator, Top-39, Headline/Primary-Text | 16 |
| (f) Booking Bots | Bot Prep, Booking, Post-Booking, Rescheduling | 4 |
| (g) Landing / Hero | Hero page, Landing image prompts, Image Prompt Writer (39) | 3 |

Both artifacts and their receipts ship as a labeled LOCAL bundle in `~/Downloads/` with a signed
`PROCESS-CERTIFICATE.json`. The tone subsystem (stages 04-08) is the canonical shared tone/writing core
at `shared-utils/tone-writing-core/`; the skill bakes a lockstep copy proven by
`scripts/verify_tone_core_sync.py`.

## 1. WHEN TO BUILD IT

Build it when a client needs the full brand-intelligence package — the avatar, awareness levels, brand
voice/tone, bios, the Facebook ad system, booking bots, and the hero/landing page — off one completed
brand-intake interview. If the request is for a STANDALONE master-brain Product Bio (10 sections /
6,000-7,000 words / 24 closes) only, that is **Skill 55 (Product Bio)**, not this skill. Routing
disambiguation: full brand-intelligence package (its embedded bio ships with it) -> Skill 52; standalone
master-brain bio -> Skill 55. The two are cross-linked and NEVER merged.

## 2. THE INTAKE + BOOK/BRAND SELECTOR (P-AV-INTAKE, turn-gated)

Ask the intake in a SINGLE message, never one-question-per-turn. **Question 0 is the version selector:
Book or Brand.** The selected version determines which question set is answered:

- `version=brand` -> the brand question set -> this 40-stage pipeline.
- `version=book` -> routes to the separate Avatar Alchemist Book skill (53); if no Book route resolves,
  the run PARKS fail-closed `book-skill-not-available` (`AF-AV-BOOK-SKILL-MISSING`) — it is NEVER served
  by the brand pipeline.

`aa_intake_gate.py` proves the intake and the selector: any required field missing/empty/boilerplate is
`AF-AV-INTAKE-INCOMPLETE`; a version that is unset or not exactly `book|brand` is `AF-AV-VERSION-UNSET`;
an answered question set that mismatches the selected version is `AF-AV-VERSION-MISMATCH`. Never
fabricate an intake answer — client words only; return the gap list and STOP if a required field is
missing. The intake spec + both question sets are `52-avatar-intelligence/intake/intake-schema.json` +
`INTAKE-TEMPLATE.md`. A self-attested "intake complete" flag is never trusted: the gate reads the actual
fields.

## 3. THE GATE CONTRACT (P-AV-* — enforcement, not description)

Every stage is deterministic and fail-closed. A violating artifact is NOT attested, NOT delivered, NOT
certified. Bands are MEASURED on the STRIPPED text and the artifact bytes; a model's self-reported count
is never trusted.

| Phase | Gate | Rule |
|---|---|---|
| P-AV-STAGE | `AF-AV-STAGE-MISSING` | every required brand-pipeline stage produced a non-empty artifact + receipt. |
| P-AV-FLOOR | `AF-AV-FLOOR` | each artifact meets its stripped-word floor. |
| P-AV-COUNT | `AF-AV-COUNT-39` | image-prompt / top-39 artifact carries exactly 39 numbered items (3x13). |
| P-AV-COUNT | `AF-AV-COUNT-HEADLINE` | the headline doc is 12 headlines + 12 short-form + 12 long-form. |
| P-AV-COUNT | `AF-AV-ADCOUNT` | each ad set carries exactly 10 ads. |
| P-AV-IMG-BAND | `AF-AV-IMG-BAND` | image-prompt artifact within the 5,000-19,000 stripped-char band. |
| P-AV-IMG-BAND | `AF-AV-UNIQUE-ARTIST` | no repeated artist/photographer/producer token across image prompts. |
| P-AV-ADSET-CAT | `AF-AV-ADSET-CAT` | each ad-set artifact matches its restored R4 category signature (no "category 2" drift). |
| P-AV-BOTDOC | `AF-AV-BOTDOC` | each bot doc carries the H1 skeleton / XML labels / merge-tag rules. |
| P-AV-HERO-12 | `AF-AV-HERO-12` | the hero page carries all 12 Hero Landing Page System sections. |
| P-AV-PLACEHOLDER | `AF-AV-PLACEHOLDER` | no unresolved template / Make.com token leaked into an artifact. |
| P-AV-NOANTHROPIC | `AF-AV-NOANTHROPIC` | no resolved model id matches `/anthropic|claude/i`; no operator credential name present. |
| P-AV-DELIVER | `AF-AV-PROVENANCE` | 40/40 foreman-attested receipts whose sha256 matches the artifact bytes. |
| P-AV-DELIVER | `AF-AV-DELIVER-INCOMPLETE` | no `~/Downloads` write below 40/40; independent QC >= 8.5; signed certificate issued only on a full pass. |

**Rework loop:** a content-gate failure returns the exact `AF-AV-*` code; a bounded re-author loop
(verifier != author) re-authors the failing stage then re-proves the WHOLE artifact. After the bounded
attempts, hard-escalate to the operator — never silent-pass.

## 4. RUN IT — THROUGH THE ONE FRONT DOOR

```
bash 52-avatar-intelligence/entry.sh <RUN_DIR>
python3 52-avatar-intelligence/scripts/aa_director.py --run-dir <RUN_DIR> --nonce <RUN_DIR>/.entry-nonce
```

The front door runs four fail-closed legs (DEPS -> BYPASS-SCAN -> HASH-PIN -> NONCE) and mints a
one-time nonce. The foreman `aa_director.py` REFUSES to run without that nonce and without a clean
gate-integrity check (`AA-GATE-HASHES.json` pins the manifests + provers; a modified gate is refused).
It schedules the 40 stages in dependency waves, dispatching one sub-agent per stage with ONLY its 3
prompt files + resolved deps, then runs the content + delivery gates. Running the LLM stages by hand
around the front door, or hand-rolling an Airtable/Drive/Slack/Gmail/n8n uploader, is the UNGOVERNED path
and is refused.

## 5. DELIVER (P-AV-DELIVER, local-only)

The deliverable bundle is a labeled folder in `~/Downloads/` — the 16 named deliverables (37 documents),
their receipts, a delivery note, `handoff.json`, and the signed `PROCESS-CERTIFICATE.json` (40/40
attested, content gate PASS, QC >= 8.5, 40-link chain). NO n8n / Airtable / Google Drive / Slack /
Gmail. Any push notification is per-client config through the client's own OpenClaw gateway (never
bypassed), client-silent by default. **No signed provenance certificate = not done.** Downstream
handoffs: 3 bot docs -> Skill 38; `Top_39_*` + `Facebook_Headline_*` + `Facebook_Targeting_Intelligence`
-> Skill 48; image prompts -> Skill 47; GHL delivery -> Skill 6; `version=book` -> Skill 53.

## 6. VERIFY BEFORE CLAIMING DONE

End-to-end proof is from the CLIENT outcome, not the builder's claim: the bundle opens, every deliverable
is present and on-band, and the certificate chain is intact. Self-verify the skill with:

```
bash 52-avatar-intelligence/verify.sh
```

It runs each prover's `--self-test`, exercises the front door + foreman plan, reproduces the golden
BRAND run end-to-end (40/40 invariants + a signed cert), proves the five broken variants each fail closed
with a DISTINCT `AF-AV-*` code, proves `version=book` routes-when-present / parks-when-absent, checks
tone-core lockstep, and runs the no-Anthropic + no-PII scan — idempotent and read-only. Any nonzero exit
= fix and re-run; never guess a missing field or waive a floor.
