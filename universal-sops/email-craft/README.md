# Email-Craft SOP Cluster (`universal-sops/email-craft/`)

The SHARED, cross-department procedure for how any department discovers and drives the **Email Engine (Skill 50)** end to end: intake -> select -> generate -> QC -> deploy (draft-only) -> human approve.

This cluster is the `universal-sops` face of the capability. It does NOT re-implement the engine. The authoritative machine spine lives in the skill:

- `50-email-engine/EMAIL-MANIFEST.json` — phase order (P1->P4) + every `AF-EMAIL-*` gate code.
- `50-email-engine/tools/prove-email.py` — the fail-closed, model-free floor prover (the SACRED battery).
- `50-email-engine/run_email_engine.py` — the deterministic orchestrator (front-door-nonce gated by `email-engine-entry.sh`); issues the delivery PROCESS-CERTIFICATE only on a full pass.
- `50-email-engine/email-library/` — the Email Superlibrary (13 frameworks + 4 buyer-types + 4 objectives + 12 persona styles + 3 named sequences), each a paired `.json` + `.md`.
- `50-email-engine/tools/email_matcher_cli.py` — the deterministic matcher (`--match "<request>"`).

## Files

| File | What it governs |
|---|---|
| `EMAIL-PIPELINE-MANIFEST.json` | The shared pipeline manifest (phases, owning roles, SOP refs, gate codes). |
| `SOP-EMAIL-01-INTAKE.md` | Lock the brief in ONE block; six required fields; no split intake. |
| `SOP-EMAIL-02-SELECT.md` | Route the brief to framework / buyer-type / objective / persona / sequence. |
| `SOP-EMAIL-03-GENERATE.md` | Author corpus-faithful copy against the selected structure. |
| `SOP-EMAIL-04-QC.md` | Run the fail-closed floor prover; bounce failures back by AF code. |
| `SOP-EMAIL-05-DEPLOY.md` | Draft-only Skill-44 handoff + the human approval gate + certificate. |
| `MASTER-EMAIL-QC-AUTOFAIL-RULESET.md` | The auto-fail table every email/sequence is measured against. |

## SACRED law (from `SOURCE-EMAIL-CORPUS.md`)

- Word band 150-300 per email; the 3-B Plan is < 150. A logged client-exact override wins and is recorded on the certificate.
- Exactly 2 A/B subject lines; preview count is sequence-declared (Convert&Flow master = 1, high-ticket = 2).
- Convert&Flow subjects: 8-12 words, `{{contact.first_name}}` in the first 40 chars, no pricing. High-ticket subjects: 80-87 rendered chars, exactly one purposeful emoji, first name present.
- The founder's real name signs every email (never a placeholder).
- A persona style is adopted for TONE ONLY; the person is NEVER named or quoted.
- Sequences: landing-page = 10 emails, high-ticket / buyer-type = 12; each slot's framework matches the SACRED map.

## Flexibility = guide-not-rule

Every framework/persona/sequence is a GUIDE and a RESOURCE, never a rule. Honor an explicit owner choice above any default; author net-new only when nothing fits; never block on preference. But the SACRED bands above are enforced by `prove-email.py` and are not opinions — a violation is a hard, named auto-fail.

## Client-runtime rule (binding)

The shipped engine on a client box NEVER uses Anthropic / `claude-*` models or operator keys. Generation + adversarial verify run on the CLIENT's own strongest configured provider; the deterministic gates (`email_matcher.py`, `prove-email.py`) are provider-neutral Python and run identically everywhere.
