# MASTER EMAIL QC AUTO-FAIL RULESET

**Cluster:** Email-Craft Rules (`universal-sops/email-craft/`)
**Enforced by:** `50-email-engine/tools/prove-email.py` (fail-closed, model-free, stdlib-only) + `50-email-engine/run_email_engine.py` (P4 process integrity)
**Master authority:** `50-email-engine/EMAIL-MANIFEST.json` (this table is its SOP-facing mirror)

Every generated email and every sequence is measured against the table below. A violation is a HARD auto-fail: the prover `sys.exit(2)` with the named code, and the copy is NOT unlocked for deploy. The prover is a MEASURER, not an agent self-score. Bands are SACRED (from `SOURCE-EMAIL-CORPUS.md`); a logged client-exact `word_band_override` wins over a default band and is recorded on the process certificate.

## Section 1 — The auto-fail table

| AF code | Stage | Level | Trigger |
|---|---|---|---|
| `AF-EMAIL-TYPE-MISMATCH` | P0/P1 | brief | brief `skill` != `email-engine`, or an unknown `sequence_position`/type. |
| `AF-EMAIL-INTAKE-SPLIT` | P0 | brief | intake not delivered in ONE block (`asked_all_at_once` not true / `one_question_per_turn` true / multiple block ids). |
| `AF-EMAIL-BRIEF-INCOMPLETE` | P0 | brief | any of the six required brief fields missing/empty, or an invalid `objective`. |
| `AF-EMAIL-FRAMEWORK-UNKNOWN` | P1/P3 | email | `framework` is not one of the 13 canonical ids. |
| `AF-EMAIL-FRAMEWORK-INCOMPLETE` | P2/P3 | email | a supplied `sections[]` does not match the framework's declared part count (PASTOR = 6, Million Dollar Sales = 12). |
| `AF-EMAIL-OBJECTIVE-INVALID` | P1/P3 | email | `objective` is not exactly one of promotional/abandoned-cart/upsell/downsell. |
| `AF-EMAIL-PERSONA-INVALID` | P1/P3 | email | `persona_style` is set but is not one of the 12 canonical styles. |
| `AF-EMAIL-PERSONA-NAMED` | P3 | email | a persona person's name is present in the copy (styles adopt tone/rhetoric only; the person is NEVER named or quoted). |
| `AF-EMAIL-BUYERTYPE-MAP` | P3 | sequence | in a 12-email sequence a slot's framework or buyer_type breaks the buyer-type -> email# -> framework map, or an invalid buyer_type. |
| `AF-EMAIL-SEQUENCE-MAP` | P3 | sequence | in the 10-email landing-page sequence a slot's framework breaks the landing-page map. |
| `AF-EMAIL-SEQUENCE-LENGTH` | P3 | sequence | landing != 10 / high-ticket|buyer-type != 12 emails, or `e_slot` values are not the contiguous set 1..N. |
| `AF-EMAIL-SUBJECT-COUNT` | P3 | email | not exactly two non-empty A/B subject lines. |
| `AF-EMAIL-PREVIEW-COUNT` | P3 | email | preview count != the sequence's declared count (Convert&Flow master = 1 / high-ticket = 2). |
| `AF-EMAIL-WORDBAND` | P3 | email | body outside 150-300 words (or outside a logged client-exact override); the 3-B Plan must be < 150. |
| `AF-EMAIL-CTA-COUNT` | P3 | email | fewer than 1 CTA (or fewer than 3 for the landing-page PASTOR emails E1-E3). |
| `AF-EMAIL-SUBJECT-CHARBAND` | P3 | email | Convert&Flow subject outside 8-12 words or contains a pricing token; high-ticket subject outside 80-87 rendered chars or not exactly one emoji. |
| `AF-EMAIL-FIRSTNAME-PLACEMENT` | P3 | email | `{{contact.first_name}}` not placed in a subject (first 40 chars for Convert&Flow; present for high-ticket). |
| `AF-EMAIL-FORMAT` | P3 | email | more than 4 emoji in the body, or a paragraph runs more than 3 sentences without a break. |
| `AF-EMAIL-SIGNATURE-PLACEHOLDER` | P3 | email | a placeholder signature token is present, or the founder's actual name is absent from the close. |
| `AF-EMAIL-DISRUPTIVE-MISSING` | P3 | email | a high-ticket appointment email carries no disruptive element. |
| `AF-PROCESS-INTEGRITY` | P4 | sequence | deploy requested without a signed process certificate (`signed:true` + `signed_by`), or a phase was skipped. |
| `AF-EMAIL-DEPLOY-UNAPPROVED` | P4 | sequence | deploy attempted without explicit logged human approval (draft-only; nothing sends without approval). |
| `AF-EMAIL-SEND-BYPASS` | entry | run-dir | a hand-rolled email sender is present in the run directory (a direct GHL/SMTP send outside the sanctioned draft-only handoff). |

## Section 2 — How to run it

```
python3 50-email-engine/tools/prove-email.py <emails.json | email.json | brief.json> [--json] [--kind email|sequence|intake]
python3 50-email-engine/tools/prove-email.py --self-test
```

Exit 0 = PASS. Exit 2 = one or more auto-fails. Exit 3 = usage/IO (still fail-closed).

## Section 3 — Independence + client-runtime

Every QC stamp is written by a reviewer who is not the author (verifier != author). The prover itself is provider-neutral Python and calls no model and no email provider — it runs identically on the operator box and on a client box. The shipped engine on a client box NEVER uses Anthropic / `claude-*` models or operator keys; generation + adversarial verify run on the client's own strongest configured provider.
