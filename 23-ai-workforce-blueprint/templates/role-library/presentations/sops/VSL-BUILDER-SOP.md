# SOP -- VSL (Video Sales Letter) Page [Wave C build target]

**Cluster:** Presentations -- additional deliverable, client-elected (opt-in). Part of the
department's "15" deliverable tier; for the exact count arithmetic link
`DEPT/DEPARTMENT-COUNTS-CANONICAL.md` -- do not restate the numbers here.
**Status as of this SOP (RUN 2, 2026-08-19):** **PARTIALLY LANDED.** While this SOP was being written,
Unit C1 landed `P-U-VSL-BUILD` into `PIPELINE-MANIFEST.json` (manifest_version 51, order 8.93 --
identical to this SOP's own earlier proposed value). `DEPT/scripts/vsl_builder.py` (Unit C3) does
**not** exist in this worktree as of this revision -- still genuinely PENDING, unlike the sales/
checkout pair (`SALES-CHECKOUT-BUILDER-SOP.md`, whose executor landed but does not yet match its own
manifest entry -- see that SOP's §3/§7 for a verified, unresolved manifest/executor CLI mismatch this
unit found and flagged, not fixed). See
[STATUS -- LIVE vs PENDING](#7-status-live-vs-pending-verified-2026-08-19) for the itemized breakdown.
**Phase id (LANDED, `PIPELINE-MANIFEST.json` manifest_version 51):** `P-U-VSL-BUILD`, order **8.93**
-- matching the `P-U-VSL-*` id family that `DEPT/intake/upsell-questions.json` already promises by
name (its `want_vsl_page` `resolverHint`, quoted verbatim in
[SECTION 1](#1-the-waiver-mechanic-quoted-verbatim-from-upsell-questionsjson)).
**Owning role (LANDED):** `media-librarian-ghl-updater` -- confirmed in the manifest entry; the same
role that already owns the department's only other GHL-push deliverable, `P9.6-WEBINAR-VIDEO`
(`WEBINAR-BUILDER-SOP.md`), whose output this phase directly depends on (§2). `sop_refs` points at
`media-librarian-ghl-updater-sops.md` SOP 9.9, which in turn points here.
**Executor (PENDING, Unit C3):** `DEPT/scripts/vsl_builder.py` -- named in
`CONTROL/MASTER-WORK-ORDER-20260818.md` Wave C (C3) and in the manifest's own `executor.cmd`
(`python3 scripts/vsl_builder.py --run-dir {run_dir}`, no `--mode` flag, unlike the sales/checkout
executor's mismatched wiring). Confirmed absent from this worktree at the time of this revision (see
§7). This SOP's author does not create, edit, or stub this file -- C3 owns it exclusively per the work
order's file-ownership rule.
**Push mechanism:** `06-ghl-install-pages/tools/ghl_rest_canvas.py` (same mechanism as the sales/
checkout pages -- see `SALES-CHECKOUT-BUILDER-SOP.md` §3 step 4 for how the landed sales/checkout
executor actually resolved the Cloudflare-WAF caveat this SOP originally flagged as open: a delegated
plan + receipt pattern, not a live in-process browser drive. C3 should follow the same pattern for
consistency, though this SOP does not assert it will.).
**Proven-by-hand template:** `~/Downloads/GAUNTLET-LOOP-WORK/LOOP2C-VSL-SALES-CHECKOUT-WEBSITE.md`
(Loop 2C, COMPLETE 2026-08-07 -- one client's VSL page, built and render-verified by hand, gate
included). This SOP documents the proven FLOW only. Per the fleet-wide no-client-names rule, that
client's copy, funnel id, and branding are correctly kept out of this repo and are NOT reproduced
here.

---

## 0. THE DELIVERABLE

A **VSL (video sales letter) page** is a single long-form landing page built AROUND the department's
own webinar video (`{deck_slug}-WEBINAR.mp4`, produced and GHL-hosted by `P9.6-WEBINAR-VIDEO`,
`WEBINAR-BUILDER-SOP.md`) -- not a new video, a page that presents the existing one with a
conversion mechanic layered on top (§4). It is opt-in: unlike the sales/checkout pair
(`SALES-CHECKOUT-BUILDER-SOP.md`), the client must actively say yes.

## 1. THE WAIVER MECHANIC (quoted verbatim from `upsell-questions.json`)

Source: `DEPT/intake/upsell-questions.json` v1.0.0, question `want_vsl_page` (order 7.7) and its
conditional follow-up `vsl_page_declined_reason` (order 7.71). The SAME question also lives at orders
7.7/7.71 in `DEPT/intake/deck-intake-questions.json` v1.5.0. Quoted exactly, not paraphrased:

> **Prompt:** "Would you like a VSL page, a video sales letter page, to go along with this? (yes /
> no)"
>
> **Help:** "Default NO -- a VSL page requires the video to exist (see the VSL video dependency: the
> VSL page references the hosted webinar/video, so a video must be produced before the page build).
> Default stays 'no' unless the owner explicitly opts in. A 'yes' is a fail-closed gate; a 'no' is
> recorded as a CLIENT WAIVER with the client's own words -- it is never inferred from silence and
> never written by the assistant. A 'no' gates OUT the VSL branch entirely."
>
> **resolverHint:** "Default 'no' (video must exist for a VSL page). Only an explicit 'yes' opens the
> VSL branch; a 'no' opens the follow-up. Never mark 'no' on the client's behalf; never summarise
> their reason -- the follow-up answer is stored VERBATIM as the waiver's client_request_quote. A
> 'yes' enables the `P-U-VSL-*` phases which wait on the video (V1) before the page build."

If the answer is "no" (the default path when the client is not asked or does not opt in explicitly is
simply "no page built" -- see below), and if "no" was an EXPLICIT answer, the follow-up
(`vsl_page_declined_reason`, order 7.71) is asked and is itself `required: true, block_gate: true`:

> **Prompt:** "Understood -- no VSL page. In your own words, why don't you want it? (I record this
> verbatim so nobody later has to guess.)"
>
> **Help:** "Asked ONLY when want_vsl_page is 'no'. The answer is stored word-for-word as the waiver's
> client_request_quote. There is no default and no assistant-authored fallback: an empty answer must
> be re-asked."

`waiver_field_mapping.vsl_page` pairs the two: `{"toggle": "want_vsl_page", "reason":
"vsl_page_declined_reason"}`.

**The mechanic, stated plainly -- note the inverted default vs. the sales/checkout pair:**
1. **Default is NO.** This is the ONE upsell question where silence does NOT default to build --
   because the VSL page has a hard dependency (§2) the sales/checkout pair does not have.
2. **An explicit "no" is still a waiver, not a bare skip** -- it carries the client's own words as
   `client_request_quote`, same discipline as §1 of the sales/checkout SOP. The default-no path (no
   answer at all) does not require a reason; an EXPLICIT decline does.
3. **A "yes" is a fail-closed gate.** Opting in commits the run to the video dependency in §2 --
   the phase cannot silently degrade to "page without video."
4. **An empty decline reason (when "no" was explicit) blocks `--complete`,** identical to the
   sales/checkout mechanic.

**Silence is NOT consent either way** -- it is simply the (documented, deliberate) default for THIS
question specifically, unlike `want_sales_checkout` where silence defaults to build. Do not conflate
the two questions' defaults; they are intentionally opposite, and `upsell-questions.json` says so
explicitly in each question's own `help` text quoted above.

## 2. THE VIDEO DEPENDENCY -- MUST run after `P9.6-WEBINAR-VIDEO`

This is the one hard sequencing rule Trevor's work order calls out by name (`MASTER-WORK-ORDER-
20260818.md` Wave C, unit C3: "VSL builder -- same shape, gated on want_vsl_page, MUST run after
P9.6 (video dependency)").

- **Why:** the VSL page embeds/links the produced webinar video. `P9.6-WEBINAR-VIDEO` (order 8.92,
  `WEBINAR-BUILDER-SOP.md`) is what produces `{deck_slug}-WEBINAR.mp4` and uploads it to GHL, writing
  the result into `working/checkpoints/media_library.json` as a `webinar_mp4` record carrying
  `ghl_media_id`, `ghl_url` (the public GCS url), `size_bytes`, and `uploaded_at`
  (`WEBINAR-BUILDER-SOP.md` §6). The VSL page's build cannot start until that record exists --
  there is nothing to embed before it does.
- **Landed manifest order: 8.93** -- confirmed in `PIPELINE-MANIFEST.json` manifest_version 51,
  between `P9.6-WEBINAR-VIDEO` (8.92) and `P7-TELEPROMPTER` (8.95), matching this SOP's own earlier
  proposed value exactly. The manifest's own `routing_note` for this phase states the reasoning in the
  same terms this SOP used, quoted verbatim: *"VIDEO DEPENDENCY: order 8.93 is deliberately AFTER
  P9.6-WEBINAR-VIDEO (order 8.92) -- the VSL page references the hosted `{deck_slug}-WEBINAR.mp4` that
  phase produces, so this phase must never run before it."*
- **Fail-closed on a missing video.** If `WANT_VSL_PAGE == "yes"` but `media_library.json` carries no
  `webinar_mp4` record (e.g. `P9.6` failed its own `AF-WEBINAR-SIZE` gate), `P-U-VSL-BUILD` must FAIL
  LOUD, never silently build a page with a missing/broken video embed and never fall back to a
  placeholder video.
- **No such dependency exists for the sales/checkout pair** -- see `SALES-CHECKOUT-BUILDER-SOP.md`
  §2. Do not accidentally serialize the sales/checkout branch behind `P9.6` too; only the VSL page
  needs it.

## 3. THE PIPELINE (proposed, templating Loop 2C)

Same four-stage shape as the sales/checkout pair (`SALES-CHECKOUT-BUILDER-SOP.md` §3), with the video
embed and the gate (§4) as VSL-specific additions, proposed as internal steps inside one
`vsl_builder.py` executor under the single `P-U-VSL-BUILD` phase (not split into multiple manifest
phases, mirroring `WORKBOOK-BUILDER-SOP.md`'s single-phase/multi-internal-step precedent):

1. **COPY.** Long-form VSL page copy from the same locked sources as the deck and the sales page
   (`intake.json`, `price_ladder.json` for price -- never authored fresh) plus the deck's own hook/
   proof/story arc so the VSL reads as a continuation of the presentation, not a separate pitch.
2. **DESIGN (Kie.ai, gpt-image-2 or the client's routed Agnes tier -- no alternative provider, ever,
   no canary passes).** Same **9,000-18,000 stripped-char** rich-prompt band as the sales/checkout
   pages (`SALES-CHECKOUT-BUILDER-SOP.md` §3 step 2) -- not Loop 2C's looser 5,000-19,000 research
   band. Brand palette + logo from `intake.json`, logo I2I only.
3. **HTML** that mirrors the design, with the video embed (the `webinar_mp4` GHL url from §2) and the
   gate mechanic (§4) built into the page structure, not bolted on after.
4. **GHL FUNNEL PUSH (`06-ghl-install-pages/tools/ghl_rest_canvas.py`)** -- identical mechanism and
   the SAME Cloudflare-WAF / agent-browser-eval operating caveat as the sales/checkout pages
   (`SALES-CHECKOUT-BUILDER-SOP.md` §3.4). Unit C3 must resolve that caveat the same way C2 does for
   the sales/checkout executor -- ideally the SAME resolution, since both executors call the same
   push mechanism.

## 4. THE VSL VIEWER GATE

Loop 2C's proven design (source: `~/Downloads/GAUNTLET-LOOP-WORK/LOOP2C-VSL-SALES-CHECKOUT-WEBSITE.md`
§"THE FEATURE"): the VSL page has a **gate at roughly 3-8 minutes into the video** (timed to land
"after the first big revelation"), forcing the viewer to submit **email / first name / cell** before
the video continues. This is a viewer-facing lead-capture mechanic -- do not confuse it with the
`block_gate` waiver terminology used in §1 (intake-side consent gates); this section is about the
PUBLISHED PAGE's own behavior, not the build pipeline's gating.

- **Build the gate INTO the page/video presentation**, not as an afterthought -- Loop 2C's own rule,
  carried forward.
- The exact timestamp is content-dependent (tied to where the "first big revelation" actually lands
  in THIS client's video) -- `vsl_builder.py` must derive it from the actual `webinar_timing.json`
  track (§2's dependency) rather than hardcoding a fixed second count, since talk length and pacing
  vary deck to deck.
- The captured lead fields (email / first name / cell) are the checkout-form-adjacent capability
  described in `SALES-CHECKOUT-BUILDER-SOP.md` §4 -- Unit C3 should confirm with C2 whether this reuses
  the same `universal-sops/form-craft/` engine or a lighter native GHL capture element, and record
  that decision when the executor lands (this SOP does not assert which one ships).
- **QC with Playwright headless** (staged/live where possible) is Loop 2C's own stated QC approach for
  this page type -- "never clobbering client work." Whatever this department's own render-verify
  convention turns out to be for the phase (Unit C4's job), it must never touch a live client page
  destructively during a test run; operator-account testing only (§5).

## 5. RULES

- **Kie.ai is the image provider. No alternative, ever, no exceptions, no canary passes.**
- **No client names, funnel ids, or branding in this repo.** Loop 2C's real VSL page is the proof
  this flow works; it stays out of the fleet-wide repo per the no-client-names rule.
- **Never print a credential value.** Same discipline as `SALES-CHECKOUT-BUILDER-SOP.md` §5.
- **Never fabricate or fake the video embed.** If the dependency in §2 is unmet, FAIL the phase --
  never link a placeholder, stock, or wrong-deck video.
- **Never overwrite an existing client GHL page or funnel** -- same `ghl_rest_canvas.py` net-new
  create discipline as the sales/checkout pages.
- **Operator credits for tests; never a client.** A sample VSL build, once an executor exists, runs on
  the operator's own GHL location and against a sample run's own webinar video -- never a client's.
- **The waiver record is the client's own words**, exactly as §1 requires.

## 6. VERIFY

**No executor exists in this worktree to run this against (verified 2026-08-19 -- see §7).** As with
`SALES-CHECKOUT-BUILDER-SOP.md` §6, a placeholder command that cannot be run would itself misstate a
capability that does not exist. When Unit C3 lands `vsl_builder.py`, this section is the place to add
the operator-smoke invocation (a `--run-dir <sample> --out ~/Downloads/... --no-upload`-style dry run
against a sample run dir that already has a `webinar_mp4` record from a completed `P9.6` phase), with
explicit pass criteria: the gate timestamp falls inside the sample's actual "first big revelation"
window per `webinar_timing.json`, the video embed resolves to a real, reachable GHL url, and the page
does not exist before the run and does exist (once) after it.

## 7. STATUS -- LIVE vs PENDING (RUN 2, re-verified 2026-08-19 after C1 landed the phase mid-unit)

| Claim | Status | Evidence |
|---|---|---|
| The client is asked "would you like a VSL page?" | **LIVE** (deployed interview app / repo question bank) | `DEPT/intake/upsell-questions.json` v1.0.0; `DEPT/intake/deck-intake-questions.json` v1.5.0 orders 7.7/7.71. NOT live on the operator Mac Mini department (Wave D, separate unit) -- the live box's question bank is v1.2.0/50q with no upsell questions (`CONTROL/FABLE-TRUTH.md` §6). |
| The answer is captured and stored | **LIVE** in the repo interview-app bridge | `DEPT/intake/interview-app/bridge/intake_writer.py` maps `want_vsl_page` -> `WANT_VSL_PAGE`; see `SALES-CHECKOUT-BUILDER-SOP.md` §1's KNOWN GAP (identical mapping caveat applies to `VSL_PAGE_DECLINED_REASON`). |
| A `P-U-VSL-BUILD` phase exists in the manifest | **LIVE** (landed mid-unit by C1) | `PIPELINE-MANIFEST.json` manifest_version 51, order 8.93, confirmed present and read in full for this revision. |
| An executor script exists | **PENDING** | `find DEPT -iname "vsl_builder.py"` -> no result in this worktree (re-checked for this revision). |
| A verifier / test exists | **PENDING** | No `P-U-` entries in `DEPT/scripts/phase_verifiers.py`; no `test_vsl*` file under `DEPT/scripts/tests/`; no `AF-U-VSL-BUILD` row in `PIPELINE-MANIFEST.autofails[]` (the phase's own `gate_codes` cites it; the registry does not yet declare it) or in `MASTER-QC-AUTOFAIL-RULESET.md`. |
| `P9.6-WEBINAR-VIDEO` (the video this phase depends on) exists and is enforced | **LIVE** | `P9.6-WEBINAR-VIDEO`, order 8.92, in `PIPELINE-MANIFEST.json`; `DEPT/scripts/build_webinar_video.py` + `WEBINAR-BUILDER-SOP.md`. |
| `ghl_rest_canvas.py` (the push mechanism) exists and is merged | **LIVE** | `06-ghl-install-pages/tools/ghl_rest_canvas.py`, present in this worktree. |
| The sales/checkout sibling executor's manifest wiring is trustworthy as a precedent | **NO -- verified broken, see `SALES-CHECKOUT-BUILDER-SOP.md` §3/§7** | The landed `sales_checkout_builder.py` has no `--mode` flag; its manifest entries' executor commands crash on dispatch. C3 should NOT assume the sibling phases are a working reference implementation to copy uncritically. |
| The flow (VSL page + gate) has been proven end-to-end, by hand, once | **LIVE (historical), not repeatable from this repo alone** | Loop 2C, COMPLETE 2026-08-07, render-verified, gate built in. Client-specific artifacts correctly excluded from this repo. |

**Plain statement:** a client who answers "yes" today gets the question asked, the answer recorded,
the manifest phase declared (order 8.93, correctly sequenced after `P9.6-WEBINAR-VIDEO`) -- and still
nothing built, because `vsl_builder.py` does not exist yet. This SOP is the design for what Unit C3
still has to land; Unit C1's manifest wiring for this specific phase is already done.

## 8. HANDBACK (proposed schema, once built)

`working/checkpoints/upsell.json` (proposed -- C3's to finalize; note the sales/checkout sibling
landed as `working/checkpoints/sales_checkout.json` instead of a shared `upsell.json`, per
`SALES-CHECKOUT-BUILDER-SOP.md` §8 -- C3 should decide deliberately whether to match that filename
convention or use its own) should record: the HTML source path, the design image URL(s), the embedded
video's
`ghl_url` (cross-referenced against `media_library.json`'s `webinar_mp4` record so a QC pass can
confirm the VSL page embeds THIS run's video, not a stale one), the resolved gate timestamp and its
source window in `webinar_timing.json`, the GHL `funnel_id`/`page_id`/url `ghl_rest_canvas.py`
returns, and the waiver record (`want_vsl_page` value +, if explicitly "no," the verbatim
`client_request_quote`).
