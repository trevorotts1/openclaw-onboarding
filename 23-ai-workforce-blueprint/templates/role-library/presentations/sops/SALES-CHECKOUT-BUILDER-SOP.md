# SOP -- Sales Page + Checkout Page (client-elected upsell)  [Wave C build target]

**Cluster:** Presentations -- additional deliverable, client-elected. Part of the department's "15"
deliverable tier; for the exact count arithmetic (10 -> 12 -> 15) link
`DEPT/DEPARTMENT-COUNTS-CANONICAL.md` -- do not restate the numbers here.
**Status as of this SOP (RUN 2, 2026-08-19):** **PARTIALLY LANDED, mid-build.** While this SOP was
being written, Unit C1 landed all three phases into `PIPELINE-MANIFEST.json` (manifest_version 51)
and Unit C2 landed `sales_checkout_builder.py` on disk -- both confirmed present in this worktree at
the time of this revision. Still PENDING: `phase_verifiers.py` entries, `AF-U-*` autofail-registry
rows (the manifest's `gate_codes` cite them; `PIPELINE-MANIFEST.autofails[]` does not yet declare
them), `MASTER-QC-AUTOFAIL-RULESET.md` Section-5 rows, and tests. This SOP does **not** audit
`sales_checkout_builder.py`'s internal implementation (that is C2's/C4's job) -- "landed" here means
"the file exists," not "verified correct." See
[STATUS -- LIVE vs PENDING](#7-status-live-vs-pending-verified-2026-08-19) for the itemized,
re-verified breakdown. Nothing in this document should be read as "a client can get this today" --
the branch is not yet QC'd, tested, or wired for real dispatch.
**Phase ids (LANDED, `PIPELINE-MANIFEST.json` manifest_version 51):** `P-U-SALES-BUILD` (order 8.75),
`P-U-CHECKOUT-BUILD` (order 8.76), `P-U-FORM-CHECKOUT` (order 8.77) -- matching the `P-U-SALES-*` /
`P-U-CHECKOUT-*` / `P-U-FORM-CHECKOUT` id families that `DEPT/intake/upsell-questions.json` already
promises by name (its `want_sales_checkout` `resolverHint`, quoted verbatim in
[SECTION 1](#1-the-waiver-mechanic-quoted-verbatim-from-upsell-questionsjson)). Unit C1 chose the
`-BUILD` suffix over this SOP's earlier `-PAGE` draft naming; this revision follows the landed ids.
**Owning role (LANDED):** `media-librarian-ghl-updater` -- confirmed in the manifest entries; the same
role that already owns the department's only other GHL-push deliverable, `P9.6-WEBINAR-VIDEO`
(`WEBINAR-BUILDER-SOP.md`). `sop_refs` on all three phases point at `media-librarian-ghl-updater-sops.md`
SOP 9.9, which in turn points here and to `VSL-BUILDER-SOP.md`.
**Executor (LANDED on disk, PENDING verification):** `DEPT/scripts/sales_checkout_builder.py`
-- confirmed present in this worktree; the manifest wires it as
`python3 scripts/sales_checkout_builder.py --mode sales|checkout|form-checkout --run-dir {run_dir}`
(one script, three `--mode` invocations, one per phase). This SOP's author did not create, edit, or
audit this file -- it is Unit C2's exclusively, per the work order's file-ownership rule.
**Push mechanism:** `06-ghl-install-pages/tools/ghl_rest_canvas.py` (Skill 6; net-new funnel/page
create + autosave, token-id-authenticated REST -- see §3.4 for an operating caveat on HOW its
network calls actually execute that C2 must resolve, if it has not already, inside the executor).
**Proven-by-hand template:** `~/Downloads/GAUNTLET-LOOP-WORK/LOOP2C-VSL-SALES-CHECKOUT-WEBSITE.md`
(Loop 2C, COMPLETE 2026-08-07 -- one client's sales/checkout/VSL pages, built and render-verified by
hand). This SOP documents the proven FLOW only. Per the fleet-wide no-client-names rule, that client's
copy, funnel id, and branding are correctly kept out of this repo and are NOT reproduced here.

---

## 0. THE DELIVERABLE

Two client-elected pages ride on **one** client answer. When the client says yes to
`want_sales_checkout`, the department builds and pushes a **sales page** and a **checkout page** as a
pair -- they are asked, waived, and (once Wave C lands) built together, never independently. The
pages live on the client's own GHL/Convert-and-Flow location as a real, published funnel -- not a
local mockup and not a description of what a page could contain. Design and copy are brand-locked to
the SAME intake record (`working/copy/intake.json`) the deck itself uses, so the pages read as part of
the same offer, not a bolt-on.

**Default is YES.** Unlike most intake questions, this is not a neutral ask -- `upsell-questions.json`
calls it "a standard upsell deliverable," defaulted to build unless the client explicitly opts out.
See §1 for the exact waiver mechanic that governs a "no."

## 1. THE WAIVER MECHANIC (quoted verbatim from `upsell-questions.json`)

Source: `DEPT/intake/upsell-questions.json` v1.0.0, question `want_sales_checkout` (order 7.6) and its
conditional follow-up `sales_checkout_declined_reason` (order 7.61). The SAME question also lives at
orders 7.6/7.61 in `DEPT/intake/deck-intake-questions.json` v1.5.0. Quoted exactly, not paraphrased:

> **Prompt:** "Do you need me to create a sales page and a checkout page to go along with your
> presentation? (yes / no)"
>
> **Help:** "Default YES. The sales page + checkout page is a standard upsell deliverable and one of
> the engine's fail-closed gates. A 'no' is recorded as a CLIENT WAIVER with the client's own words --
> it is never inferred from silence and never written by the assistant. A 'no' gates OUT the
> sales+checkout branch entirely."
>
> **resolverHint:** "Default 'yes' when the owner says 'whatever you recommend' or does not answer.
> Only an explicit 'no' opens the follow-up. Never mark 'no' on the client's behalf; never summarise
> their reason -- the follow-up answer is stored VERBATIM as the waiver's client_request_quote. A 'no'
> gates OUT the sales+checkout branch (deck-only or VSL-only run); a 'yes' enables the
> `P-U-SALES-* / P-U-CHECKOUT-* / P-U-FORM-CHECKOUT` phases."

If the answer is "no," the follow-up (`sales_checkout_declined_reason`, order 7.61) is asked and is
itself `required: true, block_gate: true`:

> **Prompt:** "Understood -- no sales page or checkout page. In your own words, why don't you want it?
> (I record this verbatim so nobody later has to guess.)"
>
> **Help:** "Asked ONLY when want_sales_checkout is 'no'. The answer is stored word-for-word as the
> waiver's client_request_quote. There is no default and no assistant-authored fallback: an empty
> answer must be re-asked."

`waiver_field_mapping.sales_checkout` pairs the two: `{"toggle": "want_sales_checkout", "reason":
"sales_checkout_declined_reason"}`.

**The mechanic, stated plainly:**
1. **Default is YES.** No answer, or a non-committal answer ("whatever you recommend"), resolves to
   YES -- the pages get built.
2. **A "no" is a waiver, not a skip.** It must carry the client's own words as
   `client_request_quote`. The assistant never writes the reason FOR the client and never summarises
   it -- it is stored verbatim.
3. **Silence is NOT consent to decline.** The only way to NOT get these pages is an explicit "no"
   followed by a non-empty, client-authored reason. An unanswered question defaults to YES (build),
   never to a silent no-build.
4. **An empty decline reason blocks `--complete`.** `sales_checkout_declined_reason` is `block_gate:
   true` -- a recorded "no" with no reason is exactly the self-authored-waiver failure mode this
   mechanism exists to prevent, and the intake cannot close without it.

**KNOWN GAP (verified in this worktree, not yet fixed -- flagging honestly, not silencing it):**
`DEPT/intake/interview-app/bridge/intake_writer.py`'s flat-answers fallback path (used when the
frontend sends a raw `{qid: value}` answer map rather than a pre-shaped `intake` object) routes a
question's answer to `pre_presentation_capture` only if its resolved field name is listed in
`PRE_CAPTURE_FIELDS`. That set currently reads `PRE_CAPTURE_FIELDS = {"WANT_SALES_CHECKOUT",
"WANT_VSL_PAGE"}` -- it does **not** include `SALES_CHECKOUT_DECLINED_REASON` or
`VSL_PAGE_DECLINED_REASON`, so on that code path the waiver's verbatim reason lands under
`deck_brief.SALES_CHECKOUT_DECLINED_REASON` instead of
`pre_presentation_capture.SALES_CHECKOUT_DECLINED_REASON`, which is where
`upsell-questions.json`'s own `storeTarget` says it belongs. Whether this actually bites in
production depends on which payload shape the deployed interview app sends (a pre-shaped `intake`
object bypasses `ID_TO_FIELD`/`PRE_CAPTURE_FIELDS` entirely and is not affected). **Before any
executor reads the waiver off `pre_presentation_capture`, confirm which path production uses and, if
it is the flat-answers fallback, add both `*_DECLINED_REASON` keys to `PRE_CAPTURE_FIELDS`.** This is
a mapping-location bug, not a data-loss bug -- the verbatim quote is captured and written somewhere in
`intake.json` either way; only its section may be wrong.

## 2. WHEN IT RUNS

**Gate:** `pre_presentation_capture.WANT_SALES_CHECKOUT == "yes"` in `working/copy/intake.json` (per
§1's known gap, confirm the section before relying on the read). A "no" with its recorded waiver gates
the whole branch OUT. Quoting the landed manifest's own `routing_note` for `P-U-SALES-BUILD` (identical
shape on the other two, each pointing back to `SALES_CHECKOUT_DECLINED_REASON`) verbatim, since it is
now the authoritative description, not this SOP's earlier proposal: *"DEFERS (no-op: writes
`working/upsell/sales.html.SKIPPED` with the waiver reason and exits 0, produces no page, pushes
nothing to GHL) unless `intake.json` `pre_presentation_capture.WANT_SALES_CHECKOUT == 'yes'`... mirroring
the P-CONVERTER / P-SP-* conditional-executor pattern"* -- the same conditional pass-through shape the
manifest already uses for `P-CONVERTER` and the four `P-SP-*` signature-only phases (see
`DEPARTMENT-COUNTS-CANONICAL.md` §2 "31 -- executes on a standard deck"). `P-U-CHECKOUT-BUILD` and
`P-U-FORM-CHECKOUT` gate on the SAME `WANT_SALES_CHECKOUT` flag (one client answer covers all three
phases, per §0) and each declares its own `.SKIPPED` no-op artifact when waived.

**No video dependency.** Unlike the VSL page (`VSL-BUILDER-SOP.md` §2), the sales and checkout pages
do not need the webinar video and have no ordering dependency on `P9.6-WEBINAR-VIDEO`. They DO need
the deck's brand system locked (palette, typography, logo -- set by `PF-DESIGN`, order 4.5) and the
intake record's offer/CTA/price fields, all of which exist well before assembly.

**Landed placement:** `P-U-SALES-BUILD` order **8.75**, `P-U-CHECKOUT-BUILD` order **8.76** (runs after
`P-U-SALES-BUILD` per its own `routing_note`), `P-U-FORM-CHECKOUT` order **8.77** (runs after
`P-U-CHECKOUT-BUILD`, wiring the payment/lead-capture fields into the funnel step the prior phase
created). All three sit between `P9.5-NOTES-SYNC` (order 8.7) and `P9.2-GHL-UPLOAD` (order 8.9) --
i.e. **before**, not after, the deck's own GHL media-library upload, since they push to a different
GHL surface (funnel pages, via `ghl_rest_canvas.py`) than `P9.2-GHL-UPLOAD` does (the deck's media
library, via `ghl_media_push.py`) and have no ordering need to wait on it. This corrects this SOP's
earlier draft, which proposed placing them after 8.9 -- Unit C1's landed order floats are the
authoritative sequence; verify directly against the manifest before relying on either draft's
reasoning.

## 3. THE PIPELINE (four steps, templating Loop 2C -- verified against the landed executor's actual code)

The proven-by-hand flow (Loop 2C, §header) is: **copy -> Kie.ai design -> HTML -> GHL funnel push.**
This SOP's earlier draft (written before C2's script landed) proposed this as four steps split across
three separate phase invocations selected by a `--mode` flag. **That guess was wrong -- corrected here
against the real, on-disk `sales_checkout_builder.py` (read in full for this revision, not assumed):**

- **`sales_checkout_builder.py` takes NO `--mode` argument.** Its only flags are `--run-dir`,
  `--skip-design`, `--no-push`, `--selftest`. A single invocation builds copy, design, and HTML for
  **BOTH** the sales AND checkout pages together, writing everything under
  `working/sales-checkout/{copy,renders,html}/` (not `working/upsell/`, which is what the manifest's
  `produces_artifact` fields currently say -- see the CRITICAL GAP callout below) and recording the
  run in `working/checkpoints/sales_checkout.json`.
- **⚠️ CRITICAL, VERIFIED GAP (Wave C manifest/executor mismatch, found while writing this SOP):** the
  landed `PIPELINE-MANIFEST.json` wires all three phases to
  `python3 scripts/sales_checkout_builder.py --mode sales|checkout|form-checkout --run-dir {run_dir}`.
  Confirmed by direct test against the script's actual `argparse` parser: `--mode sales` raises
  `error: unrecognized arguments: --mode sales` and exits 2 -- **every one of the three manifest
  executor commands as currently written would crash on dispatch.** This is a real defect between
  Unit C1's manifest and Unit C2's script (each landed independently, concurrently, while this SOP was
  being written -- neither could see the other's exact interface). This SOP does not fix it (both
  files are outside this unit's scope); it is reported to the orchestrator alongside this SOP (see this
  unit's final report) so C1/C2 reconcile the CLI before Wave E's live test. **Do not dispatch these
  phases as currently wired.**
- **`P-U-FORM-CHECKOUT` has no implementation anywhere yet.** `sales_checkout_builder.py` contains zero
  form/payment-field logic (verified: no match for "form" or "checkout_form" anywhere in the file).
  §4 remains a design proposal, not a status report of existing code.

The four steps, as the landed script actually implements them (single invocation, both pages):

1. **COPY.** `build_sales_copy()` / `build_checkout_copy()` resolve copy from `working/copy/intake.json`
   (offer name, transformation promise, audience, CTA, final price, primary objection) via the script's
   own `resolve_brief()` -- the same intake fields the deck's copy already uses. No fabricated
   testimonial or proof -- `brief.get("PROOF_ASSETS")` is passed through as-is, never invented.
2. **DESIGN (Kie.ai, one T2I call per page -- `sales-hero` + `checkout-hero`, via the shared
   `run_kie_generate` helper).** The script enforces its OWN rich-prompt band via
   `_assert_prompt_band()` and a content-in-prompt assertion (`assert_content_in_prompt`) before any
   image call -- confirm the exact floor/ceiling constants inside `sales_checkout_builder.py` match the
   department's **9,000-18,000 stripped-char** band (`PROMPT_CHAR_FLOOR`/`PROMPT_CHAR_CEILING` in
   `DEPT/scripts/build_deck.py` / `DEPT/scripts/prompt_gate.py`, the same band `WORKBOOK-BUILDER-
   SOP.md` §2 step 3 uses) rather than Loop 2C's looser 5,000-19,000 research band -- this SOP's author
   did not re-derive the script's own constant values for this revision. The hero renders are hosted
   via `ghl_media.upload_media()` (the SAME bare-REST media path `WEBINAR-BUILDER-SOP.md` uses, NOT
   `ghl_rest_canvas.py`) so the page HTML embeds a real GHL media URL, never a local file path.
3. **HTML.** `build_page_html()` assembles `sales.html` / `checkout.html` with a `ZHC-SC-{deck_slug}`
   marker; `_html_content_strings_present()` gates that every content field actually landed in the
   markup (FATAL / `EXIT_VERIFY_FAILED` if not) -- an anti-wireframe check in the same spirit as the
   workbook's OCR content gate (`WORKBOOK-BUILDER-SOP.md` §3), applied to HTML instead of a rendered
   image.
4. **GHL FUNNEL PUSH -- a delegated-receipt pattern, not a live drive.** The script's own docstring
   resolves the exact Cloudflare-WAF caveat this SOP's earlier draft flagged as an open question:
   `06-ghl-install-pages/tools/ghl_rest_canvas.py` is "the glue, not the clicker" -- its `funnel_
   create()`/`step_create()`/`page_autosave()` build the exact REST step (method/path/body/expected
   response) but make no network call themselves. `sales_checkout_builder.py` uses them to write an
   ordered execution plan, `working/sales-checkout/ghl_push_plan.json`, for an agent holding a live
   agent-browser session to execute, then gates the phase on a delegated
   `working/sales-checkout/build_receipt.json` (absence = "plan emitted, awaiting delegated execution,"
   exit 0; a present-but-placeholder/fabricated receipt = a hard failure, exit 4). Per the script's own
   comment, this mirrors an already-established pattern elsewhere in this repo:
   `56-sales-page-assets/run_sales_page_assets.py`'s P9-HANDOFF phase gates the identical way. This
   answers this SOP's earlier open question about the standing rule against OpenClaw browser
   automation -- the executor itself never drives a browser; a separate agent-browser-holding agent
   executes the plan and produces the receipt.

Every step above is FAIL CLOSED on its own gate (`EXIT_BUILD_FAILED` on a kie.ai failure,
`EXIT_VERIFY_FAILED` on the HTML content gate, `EXIT_GATE_BLOCKED` on a bad waiver, `EXIT_USAGE` on a
missing canonical-entry nonce -- `_verify_entry_nonce()` refuses a hand-rolled direct invocation from
spending kie.ai money or touching a client's GHL funnel, exactly like `build_deck.py`'s own nonce
check). This SOP's author read the script to write the above; it has not been executed end-to-end (no
sample run dir with a matching `intake.json` was built for this unit) -- treat the description as
verified-by-reading, not verified-by-running.

## 4. THE CHECKOUT FORM -- `P-U-FORM-CHECKOUT`

`upsell-questions.json`'s promise names `P-U-FORM-CHECKOUT` as its own id family, distinct from
`P-U-CHECKOUT-*` -- there is no further design note anywhere in this worktree or the Downloads working
copy beyond that one string (verified: searched both trees, the only two hits are the resolverHint
text quoted in §1 and this department's own `DEPARTMENT-COUNTS-CANONICAL.md`). This SOP's proposal,
stated as a proposal and not a fact:

**Verified as of this revision: `sales_checkout_builder.py` (Unit C2's landed script) contains no
form/payment-field logic at all** -- searched the full 1,377-line file for "form"/"checkout_form" and
found none. `P-U-FORM-CHECKOUT`'s manifest entry (`working/upsell/checkout_form.json`,
`AF-U-FORM-CHECKOUT`) currently names no real implementation anywhere in this worktree. Everything
below remains this SOP's design proposal, not a status report:

The checkout **page** (its layout, copy, and visual design) is built by the same COPY -> DESIGN ->
HTML -> PUSH pipeline as the sales page (§3). The checkout **form** -- the payment/lead-capture fields
embedded on that page -- is a different capability with its own existing, already-built,
cross-department engine: `universal-sops/form-craft/` (`06-ghl-install-pages/tools/
ghl_form_builder.py`, the GHL native FORM engine; `06-ghl-install-pages/qc-built-form.sh` its
independent QC gate). That cluster's own README describes itself as "the SHARED, cross-department
procedure for how any department discovers and drives the GHL native FORM engine ... end to end."

**Proposed:** `P-U-FORM-CHECKOUT` hands the field spec (fields needed: name, email, phone, payment --
whatever the offer requires, resolved from `intake.json`, never invented) to the form-craft cluster
via the department's own `universal-sops/cross-dept-request-template.md` mechanism, rather than
Presentations re-implementing native-form construction. This keeps the checkout PAGE (visual, ours)
and the checkout FORM (transactional, form-craft's) as two gates with two different failure surfaces
-- exactly why the promise names them as two separate id families. Unit C1/C2 may choose differently;
this SOP records the design reasoning so that choice is made deliberately, not by omission.

## 5. RULES

- **Kie.ai is the image provider. No alternative, ever, no exceptions, no partial-verification passes.** Same rule
  as every other image-producing phase in this department.
- **No client names, funnel ids, or branding in this repo.** Loop 2C's real pages are the proof this
  flow works; they stay out of the fleet-wide repo per the no-client-names rule. A build run's working
  files belong in the run directory / the client's own GHL, never committed here.
- **Never print a credential value.** `KIE_API_KEY` and the GHL `token-id` are read exactly as the
  existing `kie_generate.py` / `seed-ghl-auth.py` do -- never echoed into a transcript or a file this
  SOP's build could touch.
- **Brand palette + logo come from `intake.json`, never invented.** Logo rides `input_urls` (I2I) --
  never T2I a logo, matching `WORKBOOK-BUILDER-SOP.md` §6.
- **Price numbers come from `price_ladder.json`, never authored by the copy step** -- same rule
  `slide-copywriter-sops.md` §5 already enforces for the deck.
- **Never overwrite an existing client GHL page or funnel.** `ghl_rest_canvas.py`'s net-new
  create-funnel / create-step primitives exist precisely so a build creates its OWN funnel and pages
  at matching slugs instead of clobbering a template (the module's own docstring, §header "point 3").
- **Operator credits for tests; never a client.** A sample sales/checkout build, once an executor
  exists, is built and pushed on the operator's own GHL location, never a client's.
- **The waiver record is the client's own words.** No assistant-authored decline reason, ever
  (§1).

## 6. VERIFY

`sales_checkout_builder.py` carries its own offline self-test:

```bash
cd DEPT/scripts && python3 sales_checkout_builder.py --selftest
```

This SOP's author did not run this command as part of this unit (out of scope -- verifying C2's script
is C4's/QC's job, not this SOP-writing unit's); it is named here because it exists in the file
(`ap.add_argument("--selftest", ...)`, `_selftest()`), not because this SOP confirms it passes. For an
end-to-end operator smoke build against a real sample run directory (once the manifest/executor
mismatch in §3 is reconciled and the phase can actually dispatch):

```bash
python3 scripts/sales_checkout_builder.py --run-dir <sample-run-dir> --no-push
```

`--no-push` per the script's own help text is "offline smoke build: copy+design+HTML only, no nonce
required, no GHL push plan/receipt steps" -- the safe operator-credits-only path, mirroring
`WORKBOOK-BUILDER-SOP.md` §7 / `WEBINAR-BUILDER-SOP.md` §5's `--no-upload`-style dry run. Expect: both
`working/sales-checkout/html/{sales,checkout}.html` written, the content-string gate passing on both,
and `working/checkpoints/sales_checkout.json` recording a `built` (not `deferred`/`waived`/
`fail_closed`) status.

## 7. STATUS -- LIVE vs PENDING (RUN 2, re-verified 2026-08-19 after C1/C2 landed concurrently)

| Claim | Status | Evidence |
|---|---|---|
| The client is asked "sales page + checkout page?" | **LIVE** (deployed interview app / repo question bank) | `DEPT/intake/upsell-questions.json` v1.0.0; `DEPT/intake/deck-intake-questions.json` v1.5.0 orders 7.6/7.61. NOT live on the operator Mac Mini department (Wave D, separate unit) -- the live box's question bank is v1.2.0/50q with no upsell questions (`CONTROL/FABLE-TRUTH.md` §6). |
| The answer is captured and stored | **LIVE** in the repo interview-app bridge | `DEPT/intake/interview-app/bridge/intake_writer.py` maps `want_sales_checkout` -> `WANT_SALES_CHECKOUT`; see §1's KNOWN GAP for the declined-reason section caveat. |
| A phase (`P-U-SALES-BUILD` / `P-U-CHECKOUT-BUILD` / `P-U-FORM-CHECKOUT`) exists in the manifest | **LIVE** (landed mid-unit by C1) | `PIPELINE-MANIFEST.json` manifest_version 51, orders 8.75/8.76/8.77, confirmed present and read in full for this revision. |
| An executor script exists on disk | **LIVE** (landed mid-unit by C2) | `DEPT/scripts/sales_checkout_builder.py`, 1,377 lines, confirmed present and read in full for this revision. |
| The manifest's executor command actually runs the script | **FAILS -- verified defect, not yet reconciled** | The manifest calls `--mode sales\|checkout\|form-checkout`; the script's argparse has no `--mode` flag at all -- direct test: `--mode sales` raises `unrecognized arguments` and exits 2. See §3's CRITICAL GAP callout. |
| `P-U-FORM-CHECKOUT` has any real implementation | **PENDING** | Zero form/payment logic anywhere in `sales_checkout_builder.py` (verified, full-file search); no other script implements it. §4 is a design proposal only. |
| A verifier / test exists | **PENDING** | No `P-U-` entries in `DEPT/scripts/phase_verifiers.py`; no `test_sales*`/`test_checkout*` file under `DEPT/scripts/tests/`; no `AF-U-*` rows in `PIPELINE-MANIFEST.autofails[]` (the phases' own `gate_codes` cite `AF-U-SALES-BUILD` etc., but the registry does not yet declare them) or in `MASTER-QC-AUTOFAIL-RULESET.md`. |
| `ghl_rest_canvas.py` (the push mechanism) exists and is merged | **LIVE** | `06-ghl-install-pages/tools/ghl_rest_canvas.py`, present in this worktree, 2,369 lines. |
| The flow has been proven end-to-end, by hand, once | **LIVE (historical), not repeatable from this repo alone** | Loop 2C, COMPLETE 2026-08-07, render-verified. Client-specific artifacts correctly excluded from this repo. |

**Plain statement:** the manifest and the executor both exist now, but they do not currently agree
with each other on the calling convention -- as wired right now, dispatching any of the three phases
crashes before it does any work. This is closer to done than "nothing built" (this SOP's RUN 1
assessment), but it is not yet a working branch, and `P-U-FORM-CHECKOUT` specifically has no
implementation to crash into -- it simply doesn't exist yet. Flagged to the orchestrator alongside
this SOP's delivery so C1/C2 can reconcile before Wave E's live test.

## 8. HANDBACK

Verified from the landed script (not a proposal): `working/checkpoints/sales_checkout.json` (via
`_record_ledger()`) records, per run: `deck_slug`, the `gate` decision object (`decision` one of
`defer`/`build`/`waived`/`fail_closed`, plus `detail` and, when waived, `quote`), and once built --
`sales_copy`/`checkout_copy` paths, `sales_render`/`checkout_render` PNG paths, and the HTML output
paths. The GHL push side is recorded separately: `working/sales-checkout/ghl_push_plan.json` (the
ordered REST steps awaiting delegated execution) and `working/sales-checkout/build_receipt.json` (the
delegated agent's proof the push actually happened -- absence is "not yet executed," not a failure).
**Discrepancy to flag, not silently resolve:** the manifest's `produces_artifact` fields for these
three phases currently say `working/upsell/sales.html` / `working/upsell/checkout.html` /
`working/upsell/checkout_form.json` -- a different directory than the script's real
`working/sales-checkout/` output. This is the same class of drift as the `--mode` mismatch above (§3,
§7) and should be reconciled by the same C1/C2 pass, not patched here.
