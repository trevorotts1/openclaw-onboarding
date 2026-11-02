---
name: signature-upsell
assigned_skill: 80
description: Builds BOTH Signature upsell page instances of a Signature Launch from one reusable skill — Upsell 1 (U1, offered after a verified original purchase) and Upsell 2 (U2, one canonical page offered after a verified accepted U1 or Downsell 1 purchase) — as two distinct, separately built and separately tested deliverables. Owns the derived eight-section upsell copy profile (owner 12-section format minus sections 8–11, section 12 replaced by the "7 Reasons To Commit To Your ____ Future" section renumbered as section 8, a CTA in EVERY section), the deterministic copy validator and substantive review rubric, the U1/U2 production adapters and route state machine, and a TEST ONLY local page renderer (U1 and U2 are design deliverables: there is no production HTML builder). Eligibility is proven purchase only: a bump alone never qualifies for U2 and a client-side claim such as acceptedU1=true is never purchase proof. Every CTA invokes the same guarded native product-bound one-click action with the exact amount and terms disclosed adjacent; S80's side of that binding is built and independently reviewed at interface level (S80-06), while the native install itself is provisioned through Skill 6 and still pending (see Status).
version: 0.2.4
---

# Signature Upsell 1 + Upsell 2 (Skill 80, slug signature-upsell)

One reusable skill that produces **two distinct page instances** — Signature
Upsell Page 1 and Signature Upsell Page 2 — each with its own page ID, offer,
copy, adapters, fixtures, rendered states, and independent review. U2 is never
an afterthought or a renamed copy of U1; it is independently built and
independently tested (acceptance A12). This skill does not replace Skill 49:
Skill 49 owns the sacred 12-section main-page system and its derived chain;
Skill 80 is the standalone Signature Launch upsell skill with
verified-purchase eligibility, exact disclosure, and native one-click binding.

> **STATUS — READ THIS FIRST.** This is a **packaging candidate** (version in
> the frontmatter above and in `skill-version.txt`) for owner batch approval.
> It is merged to main, but it is **NOT production-ready.**
>
> **U1 and U2 are DESIGN DELIVERABLES ONLY.** This skill produces approved
> copy, adapter bundles, wireframes and mockups. It has **no production HTML
> builder**: `components/pages/render_pages.py` renders three fixed TEST ONLY
> bundles, consumes no brand tokens and no Skill 71 image map, and refuses to
> run without `--test-only` (exit 2, message points here). No step in this
> skill turns an approved upsell design into a page a client can publish; a
> production renderer that consumes the bundle, the brand tokens and the
> Skill 71 image map is future work and is not claimed anywhere below.
>
> What is proven is local only:
> L0 schema/static checks, L1 deterministic tests, and L2 local rendered
> pages. What is **NOT** yet proven, stated plainly:
>
> - **S80-06 binding is BUILT at interface level; the native install is
>   PENDING.** The extra-offer binding core (`components/binding/`) implements
>   S80's side of the S79/S06 shared interface (DRAFT, fixture level), is
>   wired into every adapter bundle and rendered page, and is independently
>   reviewed (binding-core review findings F1–F8 all verified CLOSED in the
>   integration review). Every bundle carries a `native_binding` record with
>   `binding_status: interface_conformant_pending_s06` and
>   `native_action_id: null`; every result carries
>   `native_action.action_id: null` with `verified_by: s80_06_binding` (the
>   interface-level binding — NOT a Skill 6 provisioned live action, which
>   the schema records as `verified_by: skill_06` at L3). No native action
>   ID exists. The native product-bound one-click action, its product/price
>   association, the successful-purchase redirect, and the native
>   configuration screenshot are provisioned and verified through Skill 6;
>   that install is gated on S06 answers to open questions Q1–Q6, formally
>   requested in `CR-S80-001` (S80 → S06, cc S79, 2026-10-16). Until then
>   every rendered CTA binds the interface-conformant binding ref and
>   cannot charge anything.
> - **L3 (installed GHL test location) and L4 (native sandbox payment) are
>   `not_run`.** S80-09 installed purchase tests have not run; they require
>   the S06 native install and an approved test location.
> - **Screenshots are `not_run`.** A Chromium binary and a Playwright cache
>   exist in the build environment, but neither produced a screenshot file
>   when invoked headlessly; no screenshot was fabricated. The spec §8
>   mockup-vs-render screenshot comparison remains open.
> - **Brand tokens and final imagery are not in the rendered pages here.**
>   Wireframes and mockups (desktop and mobile, review PDFs, overview boards,
>   Design Board for the page role) come from Skill 71's page-type runner
>   (`71-blackceo-signature-page/scripts/run_page_type.py`, spec
>   `71-blackceo-signature-page/references/copy-specs/upsell-v6.json`),
>   called by Skill 49's `49-signature-funnel/scripts/upsell_wrapper.py
>   --bridge-config`. The HTML pages in this skill use
>   neutral TEST ONLY styling and carry no images; no brand was invented.
> - All shipped fixtures are **TEST ONLY**. No production copy may be trusted
>   on a validator PASS alone: deterministic checks enforce evidence
>   *structure*; the *truth* of a referenced record is proven at S49 /
>   S80-06 / S44 read-back, and story/proof judgment belongs to the
>   substantive rubric review.

## The derived eight-section profile

Source: the owner's 12-section landing format. The upsell profile
(`components/80-signature-upsell/profiles/upsell-profile.json`, profile
`signature-upsell-eight-section` v1.4.0) derives exactly eight sections:

- Original sections 1–7 are retained: 1 Big Bold Claim, 2 Big Bold Pain 1,
  3 Big Bold Pain 2, 4 Big Bold Pain 3, 5 Big Bold Why, 6 Big Bold Who,
  7 Big Bold What.
- Original sections 8–11 are **excluded by name** (The Big Bold Benefit 1/2/3,
  The Big How To) and never reappear.
- Original section 12 is **replaced** by "7 Reasons To Commit To Your
  ____________ Future", renumbered as section 8, holding seven substantive,
  mutually distinct reasons.

Rules that override main-page conventions for this profile:

- **A CTA in EVERY section, including Who (6) and What (7).** The main-page
  no-CTA rules for those sections do not apply here (owner's explicit upsell
  instruction, spec §2/§4).
- The offer is clear from the start: the offer is named early in section 1.
- Scarcity/FOMO language is permitted **only from verified facts** with
  structured evidence references. Invented countdowns, disappearing
  discounts, invented testimonials, and fabricated proof are validator
  violations, never style choices.
- U2 copy must be genuinely distinct from U1 (a different incremental
  outcome), and its acknowledgement text must be truthful on both entry
  paths: a buyer who arrived via Downsell 1 is never told they bought the
  full U1 package.

## Eligibility law (proven purchase only)

- **U1** requires a **verified original purchase**.
- **U2** requires a verified original purchase **plus** a verified accepted
  **U1 or D1** purchase. U2 has ONE canonical page ID and one approved offer
  mapping, entered with entry context `from_upsell_1` or `from_downsell_1`
  taken from verified journey state.
- A **bump alone does NOT qualify** for U2.
- A **client-side claim is NOT proof**: `acceptedU1=true`, an asserted
  "verified" flag, or evidence references pointing at client claims are
  rejected by schema and adapters. Qualifying purchases must carry a
  `verification_source` from the adapter/native enum
  (`native_purchase_ledger`, `provider_event_readback`,
  `s44_event_adapter`), and the request's stated source must equal the
  verified journey record's source.
- Already-owned or incompatible entitlements are **suppressed** or routed to
  a safe thank-you — never a duplicate charge.

## Route law (doc 02 §4, enforced by the routing state machine)

- U1 paid → U2 if enabled, else final thank-you. U1 declined → D1 if enabled.
  D1 paid → the **same** U2 (same canonical page ID). U2 accepted-and-paid or
  declined → final thank-you.
- **Never** show U2 after both U1 and D1 are declined. Decline-both
  terminates at thank-you.
- U1 and D1 are mutually exclusive: never both purchased.
- A **failed, pending, or requires-action payment is neither acceptance nor
  decline** and traverses no paid edge. Tab close is abandonment, never a
  decline.
- U1 disabled ⇒ D1 and U2 cannot remain enabled. U2 disabled leaves no
  orphan edge.

## One-click and disclosure rules

- All CTAs on a page invoke the **same guarded native product-bound one-click
  action** (Skill 6). No custom fetch to an invented charge endpoint; no
  fabricated payment token from an opt-in.
- Adjacent to the action, the page discloses the **exact amount** (rendered
  from integer minor units with per-currency exponents), the currency, and
  one-time vs recurring terms in words that match the terms exactly.
- A processing state disables repeat triggering (single-flight attempt
  guard). A visible decline action routes **without charging**. Nothing
  purchases on page load, scroll, timer, or close.
- Failure, pending, authentication-required, expired context, unavailable
  product, and already-owned states are all handled explicitly; a blocked
  page emits **no charge action**.

## Layout of this package

The code resolves its collaborators by sibling directory, so the four
verified components are kept in their exact sibling layout under
`components/` — no verified source file was edited for packaging:

- `components/80-signature-upsell/` — core: `profiles/` (the derived
  profile), `schemas/` (upsell request/result schemas, `assigned_skill`
  const 80), `scripts/validate_upsell_copy.py` (stdlib-only validator, exit
  0 pass / 2 violation / 3 fail-closed), `references/` (substantive review
  rubric R1–R10), `fixtures/`, `tests/`, `BUILD-NOTES.md` (build record with
  Appendices A–D: the D, R2, R3, R4 repair passes).
- `components/adapters/` — `routing_state.py` (doc 02 §4 state machine),
  `upsell1_adapter.py`, `upsell2_adapter.py`, `adapter_common.py`,
  `produce.py` (deterministic bundle production), journey fixtures, expected
  bundles, tests (including `tests/test_binding_wiring.py`, the S80-06
  wiring + binding-module reconciliation tests), `BUILD-NOTES-ADAPTERS.md`.
- `components/pages/` — `render_pages.py` (TEST ONLY deterministic renderer:
  bundles in, HTML out; requires `--test-only`, refuses non-test_only bundles
  and refuses to run if a copy fixture disagrees with its bundle),
  `check_pages.py` (L2 assertions), the 24 rendered state HTML files
  (3 instances × 8 states), `index.html`, `manifest.json`,
  `BUILD-NOTES-PAGES.md`.
- `components/binding/` — the S80-06 extra-offer binding core:
  `extra_offer_binding.py` (interface-level implementation of S80's side of
  the S79/S06 shared interface: verified-parent gating, read-back-confirmed
  paid, capability-gated one-click presentation, no-rollback discipline),
  `fixture_driver.py` (TEST ONLY scripted native driver — never a
  production path), `test_binding.py` (50 L1 tests), `BUILD-NOTES-BINDING.md`
  (build record + F1–F8 repair appendix).
- `examples/` — the example result bundles (U1; U2 from U1; U2 from D1) and
  one example request per instance, byte-identical to the verified fixtures.
- `verify.py` — the package verification entry point (below).

## Pipeline (end to end, design deliverables)

Run once per instance (`upsell_1`, then `upsell_2`; separate invocations).
Skill 49 dispatch normally drives these steps; the commands are shown so an
agent can follow the chain by hand. Commands are run from the repo root; file paths named in prose are relative to the skill folder (`80-signature-upsell/`).

1. **Copy.** Author the eight-section copy document for the instance from the
   derived profile above (`components/80-signature-upsell/profiles/upsell-profile.json`).
   U2 copy must be a different incremental outcome from U1.
2. **Validator.** Run the deterministic validator on the copy. It must exit 0;
   exit 2 is a violation and 3 is fail-closed, and neither may be waived. U2 is
   also run with `--compare` against the U1 copy, and every run takes
   `--binding-manifest` (see How to run).
   `python3 80-signature-upsell/components/80-signature-upsell/scripts/validate_upsell_copy.py <copy.json> --binding-manifest <manifest.json>`
3. **Wrapper.** Skill 49's `49-signature-funnel/scripts/upsell_wrapper.py`
   (`--slot upsell_1|upsell_2`)
   enriches the S49 page-request, calls this skill's
   `components/adapters/produce.py`, and projects the page-result. It takes
   `--request`, `--result`, `--launch`, `--copy`, `--journey`, `--produce`, and
   optionally `--route-graph`, `--enrichment`, `--bridge-config`.
   `python3 49-signature-funnel/scripts/upsell_wrapper.py --slot upsell_1 --request <request.json> --result <result.json> --launch <launch.json> --copy <copy.json> --journey <journey.json> --produce 80-signature-upsell/components/adapters/produce.py`
4. **Journey source.** The `--journey` file is the verified journey state
   (trusted-adapter purchase records with an adapter-enum
   `verification_source`). It comes from the native purchase ledger, provider
   event read-back or the S44 event adapter, never from a client claim and never
   typed in by hand. At design time the real guard is not evaluated: record
   that fact, do not assert a verified purchase.
5. **Wireframes and mockups.** With `--bridge-config`, the wrapper hands the
   page to Skill 71's page-type runner
   (`71-blackceo-signature-page/scripts/run_page_type.py`, spec
   `71-blackceo-signature-page/references/copy-specs/upsell-v6.json`) for
   desktop and mobile wireframes and mockups. Without it none are made and the
   wrapper says so on stderr; the result must not read as a finished design.
6. **Review.** An independent session (not the author) scores the copy against
   the substantive rubric in `components/80-signature-upsell/references/`
   (R1–R10), and `python3 80-signature-upsell/verify.py` runs the package
   checks. A validator PASS is never a substitute for the review.

The chain ends at an approved design and a result bundle. Publishing is a
separate, approved step handled by Skill 6 (native install) and the page build
that consumes these designs; this skill does not do it.

## How to run

Validator (run from the skill root):

```bash
python3 -m unittest discover -s components/80-signature-upsell/tests
python3 components/80-signature-upsell/scripts/validate_upsell_copy.py --self-test
python3 components/80-signature-upsell/scripts/validate_upsell_copy.py components/80-signature-upsell/fixtures/copy-upsell1-public.valid.json \
    --binding-manifest components/80-signature-upsell/fixtures/binding-manifest.testonly.json
python3 components/80-signature-upsell/scripts/validate_upsell_copy.py components/80-signature-upsell/fixtures/copy-upsell2-public.valid.json \
    --compare components/80-signature-upsell/fixtures/copy-upsell1-public.valid.json \
    --binding-manifest components/80-signature-upsell/fixtures/binding-manifest.testonly.json
```

A binding PASS requires the expectation to come from **outside** the copy
(`--expected-action-ref` or `--binding-manifest`); a copy cannot expect its
own invented action ref. `--allow-unverified-binding` is a labeled local
fixture mode only and never reports a binding as verified.

Adapters (run from the skill root):

```bash
python3 components/adapters/produce.py --instance upsell_1 \
    --request <request.json> --copy <copy.json> --journey <journey.json> \
    --out <bundle.json>
```

The adapters test suite runs staged by `verify.py` (below): its routing
differential cross-check resolves the Signature Launch packet by path, and
in a standalone checkout `verify.py` reports that one cross-check NOT RUN —
never silently passed — while every other suite runs.

Binding core (run from the skill root; resolves the adapters as a
sibling directory):

```bash
python3 -m unittest discover -s components/binding   # 50 L1 tests vs the TEST-ONLY fixture driver
```

Pages (run from the skill root):

```bash
python3 components/pages/render_pages.py --test-only   # TEST ONLY: regenerates the fixture HTML deterministically; exits 2 without --test-only
python3 components/pages/check_pages.py    # L2 assertions over 3 instances x 8 states
```

Whole package:

```bash
python3 verify.py         # all suites (validator, adapters incl. wiring,
                          # binding core) + self-test + page checker +
                          # renderer determinism + schema validation of
                          # the examples; exits non-zero on any failure
```

## Result handoff (spec §7)

Each production run returns an upsell result document conforming to
`components/80-signature-upsell/schemas/upsell-result.schema.json`:
instance, page ID, source hash, approved offer mapping, native action
ID/settings, CTA map, disclosure audit, eligibility check, copy validation,
asset/copy/UI hashes, test outcomes by proof level, and independent review.
S49 creates the page request and approved route graph; S06 provisions the
page and native action; S44 maps native purchase events back to the
`upsell_1` / `upsell_2` slots. Worked examples live in `examples/` (example
result bundles and requests, byte-identical to the verified fixtures).

## Proof levels (doc 18)

L0 schema/static · L1 deterministic tests · L2 local rendered browser ·
L3 installed GHL test location · L4 native sandbox payment · L5 approved
production. This candidate stands at **L0–L2 local only**, and the L2 pages are TEST ONLY
fixtures, not a production page. A mocked or local
result never closes a higher-level unit: A10/A12 native and installed
outcomes remain `not_run` until the S06 native install (S80-06 at L3) and
S80-09 produce real evidence.
