# Social-Media-Craft SOP Cluster (`universal-sops/social-media-craft/`)

The SHARED, cross-department procedure for how any department discovers and drives the **Social Media in a Box (Skill 57)** engine end to end: intake -> run (the ONE front door) -> creative interjection -> verify -> engage-report. It supersedes Skill 35 (`social-media-planner`).

This cluster is the `universal-sops` face of the capability. It does NOT re-implement the engine. The authoritative machine spine lives in the skill:

- `57-social-media-in-a-box/SOCIAL-MANIFEST.json` — the SINGLE SOURCE OF TRUTH: phase order (P0->P8 + the fold/creative/defer phases) + every `AF-SM-*` gate code.
- `57-social-media-in-a-box/scripts/prove_bands.py` — the fail-closed, model-free SACRED-bands floor prover (reads `config/bands.json`, never hardcodes).
- `57-social-media-in-a-box/scripts/validate_contract.py` — per-platform JSON contract + em-dash + JSON-safety gate.
- `57-social-media-in-a-box/scripts/preflight_gate.py` — the fail-closed readiness gate (credits/balance/PIT/status + C2 live connected-accounts reconcile).
- `57-social-media-in-a-box/scripts/scrub_gate.py` — client-name + secret + pinData + zero-Anthropic output screen.
- `57-social-media-in-a-box/scripts/build_manifest.py` — the signed process certificate (proves ZERO Anthropic per run; override + client-copy verbatim gates).
- `57-social-media-in-a-box/scripts/ledger.py` — local SQLite media + de-dup ledger (NO n8n, NO Airtable at runtime).
- `57-social-media-in-a-box/run_social_media.py` — the deterministic orchestrator, front-door-nonce gated by `social-media-entry.sh`; walks the phases IN ORDER with no skips.
- `57-social-media-in-a-box/social-media-entry.sh` — the ONE sanctioned entry (same DEPS / BYPASS-SCAN / HASH-PIN gates, run-scoped nonce, signed certificate).
- `57-social-media-in-a-box/modes.md` — the sixteen user-facing modes.

<!-- CRAFT_INTENT_TRIGGERS_V1 -->
## Intent triggers

This craft cluster (`universal-sops/social-media-craft/`) is the execution playbook for the skill(s) below. A specialist reaches for it when the client's plain-language request matches any of these intents — the client never has to name the skill or type its slash command. Source of truth: `23-ai-workforce-blueprint/skill-department-map.json` (Layer D).

| Skill | Reach for this craft when the client says… |
|---|---|
| **35** social-media-planner | "post my content this week" · "run my social" · "schedule posts" · "plan my social calendar" |
| **57** social-media-in-a-box | "run my social week end-to-end" · "a week of content" · "a full week of posts across all platforms" |

Dept-scoped: only the task department's craft is offered. Operate the owning skill per the SOPs in this cluster **before** authoring by hand. Rule-Zero paid-call approval (USD announce + budget cap) still applies. Doctrine: `universal-sops/native-skill-invocation.md`.
<!-- END CRAFT_INTENT_TRIGGERS_V1 -->

## Files

| File | What it governs |
|---|---|
| `SOCIAL-PIPELINE-MANIFEST.json` | The shared pipeline manifest (SOP phases, owning roles, SOP refs, gate codes) — the SOP-facing mirror of `SOCIAL-MANIFEST.json`. |
| `SOP-SOCIAL-01-INTAKE.md` | Normalize the owner's ask (theme / brief / override / client-copy) into the right slot — never negotiate, never floor/cap a stated number. |
| `SOP-SOCIAL-02-RUN.md` | The ONE front door + the mode-selection table; preflight expectations; PODCAST_DEFERRED-style graceful skips. |
| `SOP-SOCIAL-03-CREATIVE-INTERJECTION.md` | The M1-M4 creative modes, the twelve injection points, override logging, and the FORM-vs-CONTENT law. |
| `SOP-SOCIAL-04-VERIFY.md` | The certificate + live GHL post-listing = the only `done`; advisory voice-report triage; de-dup block handling (re-post token). |
| `SOP-SOCIAL-05-ENGAGE-REPORT.md` | The read-only `engage` cadence, anomaly-report routing, and the (v0.5.0) memory-core Dreaming feed. |
| `MASTER-SOCIAL-QC-AUTOFAIL-RULESET.md` | The auto-fail table every run is measured against — the SOP-facing mirror of the engine's `autofails`. |

## The one-sentence law (from `MASTERDOC.md` §4.0)

> **Provers freeze the FRAME, never the PICTURE.** The client owns every word, angle, image, and mood inside the frame; the engine proves only that the frame (shape, size, count, safety, de-dup, provenance) held.

## SACRED law

- SACRED bands (`config/bands.json`) are the DEFAULT floor; a logged client-exact override wins and is recorded on the process certificate. A client-exact number is NEVER floored or capped (the client gets EXACTLY what they ask for).
- The publisher physically cannot run without a complete signed manifest that proves ZERO Anthropic for that run; `done` is claimed ONLY from the certificate PLUS a live GHL post-listing verify (never the poster's own return value).
- GHL-direct is the only sanctioned posting path; a hand-rolled poster in a run directory is `AF-SM-POST-BYPASS` (BYPASS-SCAN). Non-GHL add-on channels (`syndicate`, C9) are DEFERRED to v0.4.0 and fail closed until then.
- A silent deviation is the ONLY forbidden deviation: an applied band override with no matching logged entry refuses the certificate (`AF-SM-OVERRIDE-UNLOGGED`); in `client-copy` mode the published bytes must match the supplied copy (`AF-SM-CLIENT-COPY-MUTATED`).

## Client-runtime rule (binding)

The shipped engine on a client box NEVER uses Anthropic / `claude-*` models or operator keys. Generation + adversarial verify run on the CLIENT's own strongest configured provider chain (OpenRouter model + 2 fallbacks / client Gemini vision QC / client Kie.ai media) and the CLIENT's OWN GHL Private Integration Token + social accounts. Every deterministic gate (`prove_bands.py`, `validate_contract.py`, `scrub_gate.py`, `preflight_gate.py`, `build_manifest.py`) is provider-neutral Python and runs identically on every box. There is NO n8n and NO Airtable at runtime.
