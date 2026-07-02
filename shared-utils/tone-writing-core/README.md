# Shared Tone / Writing Core

**Stable repo path:** `shared-utils/tone-writing-core/`
(A normal top-level `shared-utils/` module on `main` after skill 52 merges.)

The **single canonical home** for the blended-tone engine, the four tone-style analyzers,
and the shared writing rails. It exists so the writing skills stay **separate skills** (Trevor's
directive — never consolidated) while the tone/writing IP lives in **one place** instead of being
duplicated three times.

## Consumers

| Skill | Uses this core for |
|---|---|
| **52 Avatar-Intelligence (BRAND)** | the tone subsystem (`04..08`) that produces `Tone_Doc` and feeds bios/bots/ads/hero |
| **53 Book-Writer** | the same blended tone + 4 styles + rails, applied to the book pipeline |
| **54 Anthology-Writer** | the same core, sibling of 53 |

Each skill **bakes a lockstep copy** of the five tone prompt dirs into its own `prompts/` for a
self-contained run; this directory is the **source of truth** those copies must match. The
build-time check `verify-tone-core-sync.py` (shipped with each consumer) fails closed if a
consumer's baked tone stage drifts from the canonical copy here.

## Contents

- `tone-core-manifest.json` — provider-agnostic contract: the 5 tone stages (tiers, deps, floors)
  + the writing-rails ids. **Zero Anthropic model ids** — the client's own TIER-A/B models resolve
  these at runtime (fleet client-sovereignty rule).
- `writing-rails.md` — the shared writing rails every writing skill enforces (markdown-only, no
  bracketed text, tone fidelity, N/A auto-pick, grade-level analysis, cultural/gender relevance,
  per-platform usage guidance, stripped-word floors).
- `prompts/04-tone-style-1 … 08-blended-tone/{system.md, methodology.md, user.md}` — the canonical
  baked tone prompt assets (R1 applied to `08-blended-tone`: it consumes the four tone-style
  ANALYSIS documents `artifact.04..07`, not raw names).

## The tone chain (R1-repaired)

```
04 tone-style-1 ┐
05 tone-style-2 ├─► 08 blended-tone ("The {First} {Last} Tone", >=3000 stripped words)
06 tone-style-3 ┤        ▲ R1: receives the four ANALYSIS docs, not just the names
07 tone-style-4 ┘
```

Each style stage: grade-level analysis first ("communicates at the 10th-grade / PhD level"), then a
`[TONE]` explanation + mimic-without-plagiarizing instructions + one example paragraph; on `N/A`
the stage MUST auto-pick a real, well-known person in harmony with the avatar's 32 answers.

## How a consumer references it

1. Manifest key: `"shared_tone_core": "shared-utils/tone-writing-core"` (see 52's
   `AA-PIPELINE-MANIFEST.json`).
2. Bake the five tone dirs into the skill's own `prompts/` (lockstep copy).
3. Run `verify-tone-core-sync.py` at build/CI time to prove the copy matches this canonical source.

**Provider rule (binding):** on a client box everything here resolves to the **client's own
providers** — never Anthropic, never operator keys.
