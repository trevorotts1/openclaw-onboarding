# S80-08 — Local rendered pages (L2 local rendered proof)

**Scope:** local rendered proof only (doc 18 level L2). Static HTML generated
deterministically from the S80 adapter bundles and copy fixtures. Nothing here
is installed, live, or capable of charging: the native action is the guarded
placeholder binding from the bundles (`action_id: null`,
`status: pending_s80_06`), labelled as such in a banner on every page.

## How it is built

- `render_pages.py` (stdlib only) consumes the three adapter bundles and, for
  each bundle, the copy fixture the bundle itself names in
  `result.artifacts[0].path`. The renderer refuses to run if the copy fixture
  disagrees with the bundle's `cta_map` (CTA text or action ref) or with the
  bundle `action_binding`, so the HTML cannot silently diverge from the
  adapter contract.
- Each page instance renders 8 states as separate static files:
  `default`, `processing`, `payment-failed`, `payment-pending`,
  `authentication-required`, `expired-context`, `one-click-unavailable`,
  `suppressed` (already-owned/incompatible disposition: safe final thank-you
  route, no charge action, no CTA, no disclosure).
- U2 is rendered once per entry context — `upsell2-from-upsell-1/` and
  `upsell2-from-downsell-1/` are separate files, so the D1-path copy
  difference (acknowledgement names the downsell at its own terms; the U1
  offer name appears nowhere) is visible in the artifacts, not just asserted.
  The two U2 `suppressed.html` files are byte-identical by design: both entry
  paths suppress to the same canonical thank-you route with no
  path-specific copy.
- State behaviour follows the bundles' `page_plan.states`:
  processing shows a spinner and disables every CTA (single-flight guard);
  payment-pending also disables CTAs and states it is neither acceptance nor
  decline; payment-failed keeps the page recoverable with CTAs enabled and
  states no charge was made; expired-context and one-click-unavailable block
  the paid action (CTAs disabled) and offer the safe no-charge continuation;
  the decline control is present on every offer state, declares
  `data-charges="false"`, and targets the bundle's decline page.
- Every CTA is followed immediately by the bundle's disclosure text, verbatim
  (U1: one-time USD 67.00 wording; U2: USD 47.00 today then monthly, 3
  payments total), including next to the primary (section 1) CTA.
- Layout: responsive CSS, bright neutral TEST ONLY styling (warm paper
  background, blue accent, varied section tints/geometry, numbered reasons
  list, full-width tap targets and a `prefers-reduced-motion` rule on
  mobile). **No brand is invented:** final brand/design tokens come from the
  S71/S63 shared system at integration (spec 10 §8, doc 16) and are NOT
  applied here.
- One recorded judgement call: the U1 bundle names no final thank-you page
  ID, so the U1 suppressed page routes to the bare `thank_you` role marker
  (`#safe-final-thank-you`) instead of an invented page ID. The U2 bundles do
  name `TEST-THANK_YOU`, and their suppressed pages route to it.

## Verification (all run locally, 2026-10-15)

- `python3 render_pages.py` — renders 24 state files + `index.html` +
  `manifest.json`. A second run produced byte-identical hashes for every
  output: **deterministic**.
- `python3 check_pages.py` — **PASS**: all assertions hold for 3 page
  instances x 8 states. Asserted per page: exactly 8 sections in the
  profile's order (number + key); CTA count == section count == 8; all CTA
  action refs identical and equal to the bundle's; CTA texts equal to the
  bundle `cta_map`; disclosure verbatim as the element immediately following
  every CTA; decline control present, visible, `data-charges="false"`,
  bundle target; entry-context acknowledgement blocks present and the other
  path's absent; processing/payment-pending/expired-context/
  one-click-unavailable states render all CTAs disabled; suppressed state
  contains no action ref and no buttons and carries the safe thank-you
  route; on the D1-path U2 default page the U1 offer name "Deep Work
  Library" is absent, and present on the U1-path page.
- Negative control: tampering one CTA action ref in `upsell1/default.html`
  made `check_pages.py` FAIL with the exact mismatch; re-running the
  renderer restored the file and the check PASSed again. The checker bites.
- **Screenshots: `not_run`.** No headless browser exists in this environment
  (checked: no chromium/chrome/headless_shell/wkhtmltoimage binaries, no
  Playwright module or browser cache), and installing one is outside this
  task's authority. No screenshots were fabricated. Desktop/mobile visual
  comparison against mockups remains open (see pending list).

## Files and hashes (SHA-256)

### Inputs (read in full; not modified)

| File | SHA-256 |
|---|---|
| `adapters/fixtures/expected-bundle-upsell1.testonly.json` | `c6cb5f3710ecc949459541922800b9160b6b0b4b67d4d2b6dcc3d5e2f577769e` |
| `adapters/fixtures/expected-bundle-upsell2-from-upsell1.testonly.json` | `ae57da8b7a177694e732635b2d1f2651406d9e071a27203dd11def81e9653d6a` |
| `adapters/fixtures/expected-bundle-upsell2-from-downsell1.testonly.json` | `81292bb4333c750e0f4552aa837a9a66f09af489a129f06b9befb12bebff8b3c` |
| `80-signature-upsell/fixtures/copy-upsell1-public.valid.json` | `ad2eaff4f90d1e7c201aed9c713e46de3cf7d213257717eb504db421c74cab13` |
| `80-signature-upsell/fixtures/copy-upsell2-public.valid.json` | `56735f9a571af1226443777cc22464e5aa77a24e7cd2db47df02490f43734530` |
| `80-signature-upsell/profiles/upsell-profile.json` (profile v1.4.0) | `c7bf8fa0b625dd8f6a67a0ed4bd496f77fd84fc8cc581ef93aefc4eecac47f2a` |

The copy fixture hashes equal the `source_hash` values recorded inside the
bundles themselves — the renderer consumed exactly the copy the adapters
validated.

### Produced (all under `rooms/S80/work/pages/`)

| File | SHA-256 |
|---|---|
| `render_pages.py` | `0b4e16a357e6d0bce08fe09f81182e77a2a70f99762e9e4bcb7ea7d010e084bb` |
| `check_pages.py` | `383ade378bc9a2c1c8db9574cd3d7fc8ac3503bde158f4a1f6362dcad02d7521` |
| `manifest.json` | `34b30262fe323edaada1cec926b96e5b648466bdb619d355e3942c6b1bb2404b` |
| `index.html` | `256694b1b54fc820cd8f2b52c4cc63299784fe59bc602801294eb08ebf8c87c6` |
| `upsell1/default.html` | `76a0f0e600e739e2f47d1d91dc3b56ee9a81fcb41113caaf5ebc6791e202cb60` |
| `upsell1/processing.html` | `9f3719503e5aa4dcbf8265191826fc4aa2048ea58e3f4ac2f247e206516b4d8f` |
| `upsell1/payment-failed.html` | `6b2b6bee75731aa9f64d1cd17c327ebae00c22d50bd71cf2a081679252a02326` |
| `upsell1/payment-pending.html` | `d038ce2322cddc6667ee1763074623c29485d7314fc19e76127a4cfdb3aac7db` |
| `upsell1/authentication-required.html` | `cca402cb23bca2a90e0cd0361e4ee0597ca85c984088bc7f2cde14d8f3696f31` |
| `upsell1/expired-context.html` | `7280cedcd26296842dcb315de39a7da459e7d2c36478664327eaffc2fc6a936b` |
| `upsell1/one-click-unavailable.html` | `a73282376b8b8c824f0da1302afb09464f98ed6b9fceb99d0eaa946bc17b44b9` |
| `upsell1/suppressed.html` | `79f5f6c5448921c36984ce4acb9bfe067e96828a33fe0d2cd90e3abb92810276` |
| `upsell2-from-upsell-1/default.html` | `740652a6682b8b1d326dac5b11f3919fe4f83a459985d393f1d065ee51fd3ed5` |
| `upsell2-from-upsell-1/processing.html` | `70c2d446e5ff768657ba6e0178ed64d5a4aa8bd35da4dfc5bde3aee088c0afea` |
| `upsell2-from-upsell-1/payment-failed.html` | `96b5e5b4d934dc2047ac15b8c31a44c79de50b6e4f2483142ef5ca34d91cbdb3` |
| `upsell2-from-upsell-1/payment-pending.html` | `468ed230e2107c98ee404bf10d5769e8ec106b736264d158427d4df2a66057eb` |
| `upsell2-from-upsell-1/authentication-required.html` | `a8d67984d668dc3f958d033d9619f1c8a4afbc9edf58dcb2ac425b424e740ab8` |
| `upsell2-from-upsell-1/expired-context.html` | `0d0fd8d829661d6bb0a37105eea755f2ae683f56d60365555357f3edfe0bf59c` |
| `upsell2-from-upsell-1/one-click-unavailable.html` | `12593d2c35caa68462dd05279fe62ed8444d7f6d2f7a0f143d05af567c0fc682` |
| `upsell2-from-upsell-1/suppressed.html` | `23c60c109e4179f68f7d6de2c8ee2d9700172b8a1d565961176ec2f94a98e7f8` |
| `upsell2-from-downsell-1/default.html` | `1f858d8141b60ca437af78d71a3162c693d71cc89b32f90d4a756f44cb2e4dd1` |
| `upsell2-from-downsell-1/processing.html` | `eca812daff6596470093d2bfe556dd3393e5ef5dda8f4a8465e6f8af2324f358` |
| `upsell2-from-downsell-1/payment-failed.html` | `6f4ea3154f5d18bead70ee75dc2838be14a691f9ec43284158c499c015d6c8f7` |
| `upsell2-from-downsell-1/payment-pending.html` | `383ff73898f89a30e49d24f3e8e1acb38c7250500083d963175c2930b50125df` |
| `upsell2-from-downsell-1/authentication-required.html` | `ee3c37eed888cdbd61f4140f7a1560a38b099258ff375cd5b6fa8a9a289718be` |
| `upsell2-from-downsell-1/expired-context.html` | `898f09de6e4f51160a4c9e6e2905cbc51e65b1064853d83b7421c125a3c7de48` |
| `upsell2-from-downsell-1/one-click-unavailable.html` | `0120ca925f560647881655b740e62c456afed2aadce32ee2231df0bb0041774e` |
| `upsell2-from-downsell-1/suppressed.html` | `23c60c109e4179f68f7d6de2c8ee2d9700172b8a1d565961176ec2f94a98e7f8` |

## Honest pending list

- **S80-06 native binding (pending):** the real Skill 6 native product-bound
  one-click action, action ID/settings, amount-versus-native read-back and
  the native configuration screenshot are all still outstanding. Every CTA
  here names the guarded placeholder `native-one-click:TEST-ONLY-U1` /
  `native-one-click:TEST-ONLY-U2` with `action_id: null`, exactly as the
  bundles record it.
- **Brand tokens (pending):** final brand/design tokens and imagery come
  from the S71/S63 shared brand and image system at integration; the neutral
  TEST ONLY styling here is a placeholder and must not ship as the brand.
- **Desktop/mobile mockups and rendered-vs-mockup comparison (pending):**
  spec 10 §8 requires actual mockups and a comparison review. Screenshots are
  `not_run` in this environment (no headless browser; see Verification), so
  the visual comparison has not happened at any level yet.
- **L3/L4 state proof (S80-09, pending):** the states rendered here are
  static L2 representations. Installed behaviour — double click, refresh/back,
  delayed/failed payment, authentication challenge, expired native context,
  already-owned suppression, route traversal to the same U2 and to final
  thank-you — is proven only at S80-09 in an installed test location with
  sandbox payment, and stays `not_run` until then.
- **Independent review (pending):** this build has not been independently
  reviewed; review must be by a session that did not author it.

## Correction (independent review defect D-P1, 2026-10-15)

The screenshot gap statement above is corrected on one point of fact: a
Playwright chromium cache (~/.cache/ms-playwright/chromium-1243) and a
Chromium binary (/opt/meta-chromium/chrome) DO exist in this environment.
The independent reviewer invoked both headlessly against a page copy; both
launch, but neither produced a screenshot file. The outcome therefore
stands — screenshots: not_run, none fabricated — with the accurate reason:
"no working headless screenshot path found," not "no browser exists."
The section 8 mockup-vs-render screenshot comparison remains open.

---

## S80-06 binding integration (2026-10-16, appended)

Pages re-rendered against the S80-06-wired bundles. Appended history;
nothing above was rewritten.

- **CTA refs**: every accept CTA now carries
  `data-action-ref="extra-offer-binding:TEST-ONLY-U1"` (upsell 1) /
  `"extra-offer-binding:TEST-ONLY-U2"` (both upsell 2 instances), from the
  bundles' cta_map. Disclosure text after every CTA is unchanged verbatim;
  decline controls unchanged (`href="#"`, `data-charges="false"`).
- **Honest banner**: the offer-page banner no longer says the binding is
  "pending S80-06" with a "guarded placeholder action". It now states the
  accept buttons bind through the S80-06 extra-offer binding,
  interface-conformant with the S79/S06 draft interface, native install
  pending S06 confirmation, no live native action exists yet, and the
  page cannot charge anything. The index page carries the same wording.
  No page claims a live native action.
- **Renderer correspondence rule** (render_pages.py sha256
  2c15fa8bb21962b898121c08f6d6567e1db062c991e458a28dcfb1868bc4b956):
  the copy fixture declares the guarded action in the copy/request-layer
  form `native-one-click:<offer_id>` (the only form the request schema
  and copy validator accept); the renderer derives the expected binding
  ref `extra-offer-binding:<offer_id>` for the same offer_id and refuses
  (SystemExit) unless the bundle plan's action_ref equals it, the plan's
  native_action_ref equals the copy's declared ref, every copy section
  CTA equals the declared ref, and every bundle CTA equals the binding
  ref. All other refusals (disclosure byte-identity, CTA text, section
  counts, journey/route/status agreement) are unchanged.
- **Re-render results**: manifest.json sha256
  2489ece538923468077eb21a75c2dd7e79375980da62db5218581b42e1416f22;
  index.html 96bc4619461bdeb7d3b5d97d65a13a7a1e8f6c382ad077d7af197ef5e3938981.
  Page hashes (sha256): upsell1/default.html
  ad8bf9c43c2939c008795174959c6bc22ff7028c202709168c190eeab91f64ee;
  upsell2-from-upsell-1/default.html
  c446a94491082685ad42b3a16967c2abca64d4d3f48199181ffc4ce1504431bc;
  upsell2-from-downsell-1/default.html
  44fbf4b2fc502cbb26ea72b0a29859c19ca0612be29397a443d5cc0bdac0453d
  (the remaining 21 state files were re-rendered in the same run and are
  covered by the determinism proof below).
- **Checks run 2026-10-16**: check_pages.py **PASS** (3 instances x 8
  states, all assertions incl. per-CTA disclosure adjacency and
  data-charges="false"); renderer determinism — clean re-render of all
  26 outputs (24 pages + index + manifest) byte-identical; negative
  control — one tampered CTA data-action-ref makes the checker FAIL
  (exit 1, names the tampered ref), re-render restores PASS; renderer
  refusal — a scratch-copy bundle with a tampered native_action_ref is
  refused with "bundle native_action_ref mismatch" (scratch removed).
- **Honest residual**: unchanged from the sections above — screenshots
  still `not_run`, section 8 mockup comparison still OPEN, brand tokens
  still pending S71/S63, and L3/L4 `not_run`. The binding shown on these
  pages is interface-conformant at fixture level only; native_action_id
  is null pending S06 Q1–Q6 and no live native action exists.
