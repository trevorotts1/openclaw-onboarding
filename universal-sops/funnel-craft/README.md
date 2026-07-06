# Funnel-Craft SOP Cluster (`universal-sops/funnel-craft/`)

The SHARED, cross-department procedure for how any department discovers and drives the **Signature
Funnel engine (Skill 49)** end to end: intake -> 12-section SACRED copy -> image prompts + images ->
GHL media + funnel build (delegated to Skill 6) -> no-pitch + certificate -> preview + human approve
-> optional 10 promo emails.

This cluster is the `universal-sops` face of the capability. It does NOT re-implement the engine. The
authoritative machine spine lives in the skill:

- `49-signature-funnel/FUNNEL-MANIFEST.json` — the P0..P10 phase spine + every `AF-FUN-*` gate code.
- `49-signature-funnel/scripts/prove_sf_intake.py`, `prove_sf_copy.py`, `prove_sf_prompt_floor.py`,
  `prove_sf_no_pitch.py`, `prove_sf_cert.py` — the five fail-closed, model-free floor provers.
- `49-signature-funnel/run_signature_funnel.py` — the deterministic no-skip orchestrator
  (front-door-nonce gated by `signature-funnel-entry.sh`); issues the signed PROCESS-CERTIFICATE only
  on a full pass.
- `49-signature-funnel/MASTERDOC.md` — the SACRED 12-section copy IP, the derivation rules, the
  Thank-You spec, the 3/5/7 matrix, the image band + Signature Grade Block, and the deliverable
  **labeling grammar**.
- `49-signature-funnel/structure/funnel_structure.json` — the SACRED 12-section contract the copy
  prover loads.

<!-- CRAFT_INTENT_TRIGGERS_V1 -->
## Intent triggers

This craft cluster (`universal-sops/funnel-craft/`) is the execution playbook for the skill(s) below. A specialist reaches for it when the client's plain-language request matches any of these intents — the client never has to name the skill or type its slash command. Source of truth: `23-ai-workforce-blueprint/skill-department-map.json` (Layer D).

| Skill | Reach for this craft when the client says… |
|---|---|
| **49** signature-funnel | "build my funnel" · "build me a landing page" · "an opt-in and upsell chain" · "a full funnel" |

Dept-scoped: only the task department's craft is offered. Operate the owning skill per the SOPs in this cluster **before** authoring by hand. Rule-Zero paid-call approval (USD announce + budget cap) still applies. Doctrine: `universal-sops/native-skill-invocation.md`.
<!-- END CRAFT_INTENT_TRIGGERS_V1 -->

## The ONE way in

A funnel is built by running, and ONLY by running, the canonical fail-closed entry shell:

```
bash 49-signature-funnel/signature-funnel-entry.sh --run-dir <RUN_DIR>
```

Requests route to this engine through the shared **STEP-0 funnel-engine selector**
(`06-ghl-install-pages/funnel-engines/registry.json` + `tools/funnel_engine_selector.py`). A
hand-rolled GHL REST call, a raw Kie `createTask`, or a `python3 run_signature_funnel.py` without the
front-door nonce is the ungoverned path and is refused (`AF-FUN-CANONICAL-BYPASS` / `AF-FUN-FRONT-DOOR`).

## Files

| File | What it governs |
|---|---|
| `FUNNEL-PIPELINE-MANIFEST.json` | The shared pipeline manifest (phases, owning roles, SOP refs, gate codes). |
| `SOP-FUNNEL-01-INTAKE.md` | Lock the brief in ONE block; funnel size (3/5/7); the truth gate; representation never assumed. |
| `SOP-FUNNEL-02-COPY.md` | Author the SACRED 12-section copy across the six page profiles; the derivation rules. |
| `SOP-FUNNEL-03-PROMPTS-IMAGES.md` | 8-block image prompts (5,000–19,000 chars) + Kie generation + provenance. |
| `SOP-FUNNEL-04-BUILD.md` | GHL media + funnel/page build — DELEGATED to Skill 6; the ONE delivery rail. |
| `SOP-FUNNEL-05-CERTIFY.md` | No-pitch (clean Thank-You) + signed certificate + preview/approve + the 10-email offer. |
| `MASTER-FUNNEL-QC-AUTOFAIL-RULESET.md` | The auto-fail table every page/prompt/certificate is measured against. |

## SACRED law (from `MASTERDOC.md`)

- The **12 section names** and every **char/word band** are SACRED — never changed, floored,
  reordered, or reinterpreted. "Never change the name of my page sections."
- Sections 1–4 each **180–225 chars**; Sec 5/6/8/9/10 **≤30 words**; Sec 7 **70–120 words / 5–10
  bullets**; Sec 11 **100–150 words, NO button, steps 1–6 each 89–116 chars, step 7 ≤170**, with the
  share / email-bonus / founder-text / community steps; Sec 12 **exactly 6 labeled parts**, part 2
  starts "I used to be just like you…".
- Derived pages **exclude Sections 8–11** and replace Section 12 with the renumbered Section 8
  ("7 Reasons To Commit To Your ____ Future" for upsells; "When Time Runs Out" for downsells; exactly
  7 items). **After Downsell 2 the funnel NEVER pitches again** — the Thank-You page is clean.
- **Image-prompt band: 5,000–19,000 stripped chars** per prompt; the ~1,290-char Signature Grade Block
  is embedded verbatim in block 4 of every prompt; no em dashes.
- **Truth gate:** every scarcity claim, bonus, founder text, and community is confirmed real at intake.
  The system never fabricates urgency.

## Deliverable labeling grammar (shared with Skill 56 — reciprocal pin)

Every funnel deliverable (copy doc, image prompt, PNG, HTML fragment, preview) is labeled:

```
<client>__<funnel>__<stage>__<type>__vNN
```

`stage ∈ {main, checkout, upsell1, downsell1, upsell2, downsell2, thankyou}`;
`type ∈ {copy, prompt, image, html, preview}`; `vNN` is a zero-padded version (`v01`, `v02`, …).
This grammar is pinned reciprocally in `49-signature-funnel/MASTERDOC.md` §8 and in Skill **56**
(Sales-Page-Assets), which has LANDED and OWNS the grammar (`56-sales-page-assets/structure/labeling-grammar.json`);
its `universal-sops/sales-page-craft/` cluster EXTENDS this funnel-craft cluster for the Direct-Response
asset stack. Do not diverge the two.

## Flexibility = guide-not-rule

The engine is a GUIDE and a RESOURCE for how a department fulfils a funnel request; honor an explicit
owner choice about funnel size and offers. But the SACRED bands above are enforced by the provers and
are not opinions — a violation is a hard, named `AF-FUN-*` auto-fail.

## Client-runtime rule (binding)

The shipped engine on a client box NEVER uses Anthropic / `claude-*` models or operator keys.
Generation + adversarial verify run on the CLIENT's own strongest configured provider; the
deterministic gates (`prove_sf_*.py`, the funnel-engine selector) are provider-neutral Python and run
identically everywhere. Publishing is human-approved (preview URLs + a labeled `~/Downloads/` bundle).
