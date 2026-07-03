# SOP-SOCIAL-01: NORMALIZE THE ASK — NEVER NEGOTIATE, NEVER FLOOR/CAP

**Cluster:** Social-Media-Craft Rules (`universal-sops/social-media-craft/`)
**Master authority:** `SOCIAL-PIPELINE-MANIFEST.json` + `57-social-media-in-a-box/SOCIAL-MANIFEST.json` + `MASTER-SOCIAL-QC-AUTOFAIL-RULESET.md`
**Owning role:** Content Marketing Strategist (Marketing); the Director of Social Media owns the run it feeds
**Stage:** intake (feeds P1-PLAN / P2-CONTENT / P2-BRIEF / P2-INGEST)
**Produces:** `working/plan/plan.json` (themeOfWeek), and when the client steers: `working/creative/brief.json`, `working/creative/overrides.json`, `working/creative/client-copy/*.json`
**Gates this stage satisfies (downstream):** AF-SM-PLAN-INCOMPLETE, AF-SM-OVERRIDE-UNLOGGED, AF-SM-CLIENT-COPY-MUTATED

---

## 0. WHY THIS SOP EXISTS

Every creative ask the owner makes — a theme, a hook, an exact caption length, a finished post to run verbatim — is captured into a SLOT the engine already understands, in the owner's own words, without negotiation. The engine freezes the FRAME (shape, size, count, safety), never the PICTURE. Intake's only job is to route the ask to the right slot so the client gets EXACTLY what they asked for, provably.

## 1. THE NORMALIZE-NEVER-NEGOTIATE FLOW (§4.3)

The client interjects in natural language on any channel. The agent normalizes; it never talks the client out of the ask, never requires field names, and never floors or caps a stated number.

| The owner's ask | Slot it becomes | Notes |
|---|---|---|
| "This week's theme is X" / a queued list / "surprise me" | `themeOfWeek` (I1) / `themeQueue` (I2) / `wildcard` | Any non-empty answer is valid; wildcard is a seeded-deterministic pick. |
| "Do it THIS way this week" — hooks, angles, arc, voice, visuals | `working/creative/brief.json` (I4/I5) | Verbatim-preserved; consumed through the un-hashed CREATIVE BRIEF slots. |
| An EXACT number — "captions at 2,200 chars", "5 slides", "no hashtags" | `working/creative/overrides.json` with the client's EXACT numbers | NEVER floored/capped. Must be logged or P6 refuses the certificate (`AF-SM-OVERRIDE-UNLOGGED`). |
| A finished post / supplied media to run as-is | `working/creative/client-copy/*.json` (I6) | Runs VERBATIM (`--mode client-copy`, M3); the engine packages/certifies but never authors. |
| Per-platform voice, art direction, series length, CTA/keyword | `platformVoice` / `artDirection` etc. (I8/I9/I11/I12) | All optional; defaults reproduce today exactly. |

## 2. "JUST THIS WEEK OR FROM NOW ON?" — ASKED ONCE

For any override or creative steer, ask the scope question exactly once: a **run-level** ask auto-reverts after this run; a **config-level** ask persists in the client config. Record the scope on the override entry so the certificate can log it.

## 3. LOG THE CLIENT-EXACT ASK

Every numeric or creative override is written to `working/creative/overrides.json` as an entry carrying **who asked**, the **verbatim ask**, and the **scope** (run / config). Deviation itself is free; a SILENT deviation is the only forbidden deviation. The engine measures against whichever bound applies and requires the log to exist.

## 4. VERIFY BEFORE ADVANCING

The plan is locked when `working/plan/plan.json` carries a non-empty `themeOfWeek` and (for a full week) a `plannerSheetId`. Never invent a missing theme — return the gap to the owner and STOP. Creative slots are validated downstream at P3 (bands) and P6 (override logging + client-copy verbatim); a self-attested "captured" flag is never trusted.
