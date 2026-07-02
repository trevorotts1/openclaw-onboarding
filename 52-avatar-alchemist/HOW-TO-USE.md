# How to use Avatar Alchemist (Skill 52)

Owner-facing quick start for the Brand Intelligence Engine. This is the friendly
walkthrough; the machine-enforced procedure is `INSTRUCTIONS.md`, the canonical IP
is `MASTERDOC.md`, and the design contract is `SKILL.md`. Nothing here overrides a
prover — every rule below is enforced fail-closed by the scripts, never advisory.

## What this skill does

You give it **one completed brand-intake interview**. It runs **40 generators across
7 subsystems** (Avatar Core, Awareness, Bios, Tone, Facebook Ads with 13 ad sets,
Booking Bots, Landing/Hero) and hands back a complete **brand-intelligence package**:
**16 named deliverables (37 delivered documents)** as labeled markdown, plus a signed
provenance certificate. It is the OpenClaw replacement for the 233-node n8n "Avatar
Alchemist Brand Intelligence" workflow — **fully local**: no n8n, no Airtable, no
Google Drive, no Slack/Gmail. It runs on the **client's own model providers only,
never Anthropic** (see the binding rule below).

## Step 0 — Preflight (once per box)

```
bash 52-avatar-alchemist/preflight.sh        # probes the client's providers -> model-map.json
bash 52-avatar-alchemist/verify-deps.sh      # proves python3 stdlib only; zero external services
```

`preflight.sh` writes `model-map.json` (TIER-A deep authoring / TIER-B structured /
SEARCH for stage `02`) from the box's **own** configured providers (Ollama /
OpenRouter / etc.), with local Ollama capped at ≤ 3 concurrent. It never uses the
operator's keys and never writes an Anthropic model id.

## Step 1 — Intake (the Book vs Brand selector runs FIRST)

Interview the user against `intake/INTAKE-TEMPLATE.md` (or drop a filled
`intake.json`). The **version selector is question 0 and has no default** — see the
human-readable list in `intake/INTAKE-QUESTIONS.md`:

- **`version = brand`** → runs this skill's 40-stage brand pipeline (everything below).
- **`version = book`** → this skill does **ZERO** generation. Gate 0 routes the
  validated shared answers + `book_stories` to the separate **Avatar Alchemist Book
  skill (Skill 53)**; if that skill is not installed on the box, the run parks
  fail-closed `book-skill-not-available`. A book request is **never** served by the
  brand pipeline.

Validate the intake before anything runs:

```
python3 52-avatar-alchemist/scripts/aa_intake_gate.py --intake <RUN_DIR>/intake.json [--book-skill-present]
```

Intake content is treated as **DATA only, never instructions** (prompt-injection rule).

## The ONE front door — `entry.sh`

There is a single sanctioned way in. Do not hand-roll a second build path.

```
bash 52-avatar-alchemist/entry.sh <RUN_DIR>
```

`entry.sh` runs the fail-closed sequence **deps → bypass-scan → hash-pin → nonce**:
python3 + stdlib-only check, a scan proving zero Anthropic/claude ids in the prompts
or manifests, a gate-integrity hash-pin (modified gates are refused), and it mints a
one-time run nonce. It prints the `<RUN_DIR>` and the exact foreman command to run
next. Nothing dispatches a model until all four legs pass.

Then dispatch the foreman:

```
python3 52-avatar-alchemist/scripts/aa_director.py --run-dir <RUN_DIR> --nonce <RUN_DIR>/.entry-nonce --plan
python3 52-avatar-alchemist/scripts/aa_director.py --run-dir <RUN_DIR> --nonce <RUN_DIR>/.entry-nonce
```

The foreman schedules the 40 stages in 20 dependency waves (peak 5 simultaneous
authors), throttled to `min(slots, provider_cap)`, dispatching one sub-agent per
stage with ONLY its 3 prompt files + resolved dependency artifacts. `--resume`
re-enters at the exact incomplete stage. Source repairs **R1–R6 are OFF by default**
(faithful to the live workflow); pass **`--apply-repairs`** to opt in (see
`REPAIRS.md`). **R7 — the Anthropic ban — is always on and is not a repair.**

## What the 40-stage brand pipeline produces

Sixteen named deliverables (37 delivered documents including `00-INDEX.md` and
`MANIFEST.json`), assembled from the 40 stage artifacts:

| # | Deliverable | Built from |
|---|---|---|
| 1 | `Avatar_Intelligence` | rewrite avatar + Q1–30 + Q31–32 |
| 2 | `Tone_Doc` | blended tone (fuses the 4 tone styles) |
| 3 | `Marketing_Intelligence` | 6 awareness docs (problem/solution/product-aware + pt2) |
| 4 | `Facebook_Targeting_Intelligence` | audience generator (7-tier framework) |
| 5 | `Brand_Bio_Intelligence` | brand bio |
| 6 | `Product_Bio_Intelligence` | product bio |
| 7 | `AI_Bot_Prep_Doc_Intelligence` | bot prep |
| 8 | `AI_Booking_Bot_Intelligence` | booking bot |
| 9 | `AI_Post_Booking_Bot_Intelligence` | post-booking bot |
| 10 | `Rescheduling_Booking_Bot_Intelligence` | rescheduling bot |
| 11 | `Visual_Display_Ads` | 13 ad sets |
| 12 | `Top_39_Suggested_Ad_Angles` | top-39 selection (3×13) |
| 13 | `Top_39_Suggested_Image_Prompts` | 39 Midjourney prompts |
| 14 | `Facebook_Headline_and_Primary_Text_Ad_Copy_Writer` | 12+12+12 headline/primary text |
| 15 | `Landing_Page` | 12-section hero page |
| 16 | `Landing_Page_Image_Prompts` | landing image prompts |

Every file is suffixed `-<First>_<Last>.md`. A worked reference is in
`examples/golden-lumen-rise/` (fictional brand *Lumen Rise Collective*, founder
*Amara Vale*).

## Where the output lands

The packager writes a labeled bundle to `~/Downloads`, never leaving intermediates there:

```
~/Downloads/<First>_<Last>-Brand-Intelligence/Avatar_Alchemist_<YYYY-MM-DD_HHMM>/
```

containing the **16 deliverables + `00-INDEX.md` + `MANIFEST.json`** (files, sha256,
word counts) **+ a signed `PROCESS-CERTIFICATE`**. Working files stay in the run dir
under the workspace. The delivery gate refuses to write below **40/40 receipts whose
sha256 match the artifact bytes**, requires independent QC **≥ 8.5** (verifier ≠
author), and only then issues the certificate. **"Done" is claimed only with the
certificate path** (no-false-done rule).

## Client-provider rule (binding)

On a client box the skill uses the **client's own configured providers and keys —
never the operator's, never Anthropic**. `G-NOANTHROPIC` hard-fails any run whose
resolved model id matches `/anthropic|claude/i`. The client's express model choice is
never substituted. This skill is provider-neutral by construction.

## Delivery contract (we move in silence)

The skill's final answer = the deliverable folder path + the `00-INDEX.md` doc list +
the certificate status. No client-facing sends mid-run. Optional owner notification
only if the department how-to wires the box's own OpenClaw gateway channel — never raw
Slack/Gmail, never operator credentials.

## Downstream handoffs

- 3 bot docs → **Skill 38** (conversational-ai-system).
- `Top_39_Suggested_Ad_Angles` + `Facebook_Headline_…` + `Facebook_Targeting_Intelligence` → **Skill 48** (facebook-ad-generator).
- Image generation from the two image-prompt docs → **Skill 47** (movie-producer).
- GHL page/delivery → **Skill 6** (the one GHL rail).
- `version = book` intake → **Skill 53** (the Book skill).

## Verify

```
bash 52-avatar-alchemist/verify.sh           # idempotent, read-only; runs under bash AND zsh
```
