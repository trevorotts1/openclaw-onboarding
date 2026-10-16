# SOP -- VSL (Video Sales Letter) Page

**Cluster:** Presentations -- additional deliverable, client-elected (opt-in). Part of the
department's "15" deliverable tier; for the exact count arithmetic link
`DEPT/DEPARTMENT-COUNTS-CANONICAL.md` -- do not restate the numbers here.
**Status (2026-10-14, FIX-PLAN Item 23):** **LANDED, single design.** The executor
`DEPT/scripts/vsl_builder.py` exists and is the ONE VSL page design this department ships
(the Wave C executor). Its registered verifier is `phase_verifiers._verify_upsell_vsl_build`;
its autofail row is `AF-U-VSL-BUILD`; its test coverage lives in
`DEPT/scripts/tests/test_upsell_verifiers.py` and `test_upsell_intake_shape.py`. The earlier
Gauntlet page-assembly design is RETIRED: its files are archived byte-identical in
`presentations/archive/vsl-gauntlet/` and its one reusable idea is preserved, without
authority, in `VSL-GAUNTLET-SPEC-NOTE.md` (same directory as this SOP). Do not build to the
retired design.
**Phase id (LANDED):** `P-U-VSL-BUILD`, order **8.93** -- matching the `P-U-VSL-*` id family
that `DEPT/intake/upsell-questions.json` already promises by name (its `want_vsl_page`
`resolverHint`, quoted verbatim in [SECTION 1](#1-the-waiver-mechanic-quoted-verbatim-from-upsell-questionsjson)).
The manifest version is read live from `PIPELINE-MANIFEST.json`; this SOP does not pin it.
**Owning role (LANDED):** `media-librarian-ghl-updater` -- confirmed in the manifest entry; the
same role that already owns the department's only other GHL-push deliverable,
`P9.6-WEBINAR-VIDEO` (`WEBINAR-BUILDER-SOP.md`), whose output this phase directly depends on
(§2). `sop_refs` points at `media-librarian-ghl-updater-sops.md` SOP 9.9, which in turn points
here.
**Executor (LANDED):** `DEPT/scripts/vsl_builder.py` -- invoked by the manifest as
`python3 scripts/vsl_builder.py --run-dir {run_dir}` (no `--mode` flag). It builds the whole
page itself: copy, Kie.ai hero design, HTML with the viewer gate (§4), and hosts the hero
image through `ghl_media`. Offline smoke form: `--skip-design --no-push` (no nonce, no GHL
write of any kind). `--selftest` runs its deterministic offline self-test.
**Install mechanism (NOT the builder):** the funnel install is a separate phase,
`P-U-GHL-VSL` (order 6.4), executed by `DEPT/scripts/ghl_external_installer.py` (PRES-011):
it emits the install plan, a delegated Skill 6 execution lands the page (net-new create,
one funnel per client per run, reusing this run's verified sales funnel when one exists),
and the phase completes only on the installer's own `validate_receipt()` (adapter
funnel/page IDs + matching-location readback + ops-ledger provenance), recorded at
`working/vsl/ghl_build_receipt.json`. The gate form object is likewise a separate phase,
`P-U-FORM-GATE` (order 5.6, Skill 44, contract `DEPT/scripts/vsl-gate-form-spec.json`).
The builder emits NO push plan and verifies NO push receipt: an earlier builder-side plan +
receipt path was retired with the Gauntlet design (Item 23) because it duplicated this
install path and was enforced by no registered verifier.
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
(`SALES-CHECKOUT-BUILDER-SOP.md`), the client must actively say yes. There is exactly ONE VSL
page per elected run (no a/b variants; the two-variant requirement belonged to the retired
design and is preserved only in the spec note).

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
  (`WEBINAR-BUILDER-SOP.md` §6). The VSL page's build cannot start until that video exists --
  there is nothing to embed before it does.
- **Landed manifest order: 8.93** -- confirmed in the live `PIPELINE-MANIFEST.json`, between
  `P9.6-WEBINAR-VIDEO` (8.92) and `P7-TELEPROMPTER` (8.95). The manifest's own `routing_note` for
  this phase states the reasoning, quoted verbatim: *"VIDEO DEPENDENCY: order 8.93 is deliberately
  AFTER P9.6-WEBINAR-VIDEO (order 8.92) -- vsl_builder.py's verify_video_dependency() resolves
  working/delivery/{deck_slug}-WEBINAR.mp4 via build_webinar_video.py's own WEBINAR_FILENAME_TEMPLATE
  and fails closed (AF-VSL-NO-VIDEO) if it is absent, so this phase must never run before P9.6."*
- **Fail-closed on a missing video.** The executor's check is over the LOCAL artifact, not the
  ledger: `verify_video_dependency()` requires `working/delivery/{deck_slug}-WEBINAR.mp4` to exist
  AND pass `ghl_media.verify_video()`'s local probe (non-empty, inside the 500MB v3 ceiling, real
  MP4 `ftyp` box). If `WANT_VSL_PAGE == "yes"` but the video is absent or broken, `P-U-VSL-BUILD`
  FAILS LOUD (executor exit 5, `AF-VSL-NO-VIDEO`), never silently builds a page with a missing/broken
  video embed and never falls back to a placeholder video. The hosted url for the embed is then
  resolved from the ledger's `webinar_mp4` record (with a deck-slug cross-check warning); when no
  hosted url exists yet, the build proceeds with a local reference plus a loud warning, because
  hosting is P9.6's concern and the hard gate is the video's existence.
- **No such dependency exists for the sales/checkout pair** -- see `SALES-CHECKOUT-BUILDER-SOP.md`
  §2. Do not accidentally serialize the sales/checkout branch behind `P9.6` too; only the VSL page
  needs it.

## 3. THE PIPELINE (landed, templating Loop 2C)

One executor, `vsl_builder.py`, under the single `P-U-VSL-BUILD` phase (mirroring
`WORKBOOK-BUILDER-SOP.md`'s single-phase/multi-internal-step precedent), followed by the two
PRES-011 install phases. In order:

1. **COPY.** The builder generates the long-form VSL page copy itself
   (`build_vsl_copy`, written to `working/vsl/copy/vsl.md`) from the run's own locked sources:
   `intake.json`'s brief fields (offer, transformation promise, audience, CTA, objection, proof,
   hook seed) -- never authored fresh, never read from the Path A agent phases' fragment files.
2. **DESIGN (Kie.ai only -- no alternative provider, ever, no partial-verification passes).** The
   builder authors the hero design prompt from the brand palette in `intake.json` and renders it
   through Kie.ai (or reuses `working/vsl/renders/` under `--skip-design`). The rich-prompt gate
   is KIE rule 12 through the shared `prompt_gate` enforcer plus the builder's own content
   assertion (every required content string present, wireframe directives refused); the retired
   fixed char band no longer exists anywhere in this pipeline.
3. **HTML** assembled by the builder into `working/vsl/html/vsl.html`: the design mirrored, the
   video embed (the `webinar_mp4` GHL url from §2), and the viewer gate (§4) built into the page
   structure, not bolted on after. The page carries the run's own `ZHC-VSL-BUILDER`
   `deck_slug=<slug>` marker, which is what the phase verifier checks.
4. **INSTALL (`P-U-GHL-VSL`, NOT this executor).** `ghl_external_installer.py` installs
   `working/vsl/html/vsl.html` into the client's funnel through the Skill 6 canonical
   page-install path (the `ghl_rest_canvas.py` sequence executed in a delegated live session),
   under the PRES-011 receipt discipline described in the header. The gate form and its tag
   workflow are installed by `P-U-FORM-GATE` (Skill 44) from
   `DEPT/scripts/vsl-gate-form-spec.json`. A built page with no verified install receipt is a
   page that is NOT live; never report it as installed.

## 4. THE VSL VIEWER GATE

Loop 2C's proven design (source: `~/Downloads/GAUNTLET-LOOP-WORK/LOOP2C-VSL-SALES-CHECKOUT-WEBSITE.md`
§"THE FEATURE"): the VSL page has a **gate inside the [180s, 480s] window (roughly 3-8 minutes
into the video)**, forcing the viewer to submit **first name / email / cell** before the video
continues. This is a viewer-facing lead-capture mechanic -- do not confuse it with the
`block_gate` waiver terminology used in §1 (intake-side consent gates); this section is about the
PUBLISHED PAGE's own behavior, not the build pipeline's gating.

- **Build the gate INTO the page/video presentation**, not as an afterthought -- Loop 2C's own rule,
  carried forward. The builder emits the gate overlay markup and the pause + seek-block +
  reveal-on-submit mechanic in the page itself.
- **THE GATE RULE (the single rule, stated exactly as `resolve_gate_timestamp()` implements it):**
  the timestamp is DERIVED from the run's own `working/checkpoints/webinar_timing.json` track,
  never hardcoded. Take every slide boundary (`audio_start`) that falls inside [180s, 480s];
  the gate fires at the boundary CLOSEST TO the window midpoint (330s). If no boundary falls
  inside the window but the track's total duration is known, the gate fires at half the total
  duration clamped into the window. If there is no usable track at all, the gate fires at the
  window midpoint (330s). The result always lands inside the band, and the builder records the
  chosen seconds and their source in the phase ledger.
- **The retired alternative:** an earlier design placed the gate relative to the talk's first big
  revelation (the R+20 rule). That rule is RETIRED (Item 23): no run artifact identifies a
  revelation slide, so it could never execute except through its own flagged fallbacks. It is
  preserved, without authority, in `VSL-GAUNTLET-SPEC-NOTE.md`. Do not re-introduce it.
- The captured lead fields (first name / email / cell) are the Skill 44 form-object contract in
  `DEPT/scripts/vsl-gate-form-spec.json` (fields `zhc_vsl_first_name` / `zhc_vsl_email` /
  `zhc_vsl_phone`, all required), installed by `P-U-FORM-GATE` and attached on the install path.
  The page's built-in gate form is the in-page capture mechanic; its consent posture follows the
  department's standing rule (benefit-first copy, every consent box required to proceed,
  unchecked by default). A page whose gate form is a static mock is not a gate.
- **QC with Playwright headless** (staged/live where possible) is Loop 2C's own stated QC approach for
  this page type -- "never clobbering client work." Whatever this department's own render-verify
  convention turns out to be for the phase (Unit C4's job), it must never touch a live client page
  destructively during a test run; operator-account testing only (§5).

## 5. RULES

- **Kie.ai is the image provider. No alternative, ever, no exceptions, no partial-verification passes.**
- **No client names, funnel ids, or branding in this repo.** Loop 2C's real VSL page is the proof
  this flow works; it stays out of the fleet-wide repo per the no-client-names rule.
- **Never print a credential value.** Same discipline as `SALES-CHECKOUT-BUILDER-SOP.md` §5.
- **Never fabricate or fake the video embed.** If the dependency in §2 is unmet, FAIL the phase --
  never link a placeholder, stock, or wrong-deck video.
- **Never overwrite an existing client GHL page or funnel** -- installs are net-new creates on
  the PRES-011 path, one funnel per client per run.
- **Operator credits for tests; never a client.** A sample VSL build runs on the operator's own
  GHL location and against a sample run's own webinar video -- never a client's.
- **The waiver record is the client's own words**, exactly as §1 requires.

## 6. VERIFY

Offline, deterministic, no spend:

```bash
python3 scripts/vsl_builder.py --selftest
python3 scripts/ghl_external_installer.py --selftest
python3 -m pytest scripts/tests/test_upsell_verifiers.py scripts/tests/test_upsell_intake_shape.py
```

Operator smoke against a sample run dir that already carries a real P9.6 video artifact:

```bash
python3 scripts/vsl_builder.py --run-dir <sample> --skip-design --no-push
```

Pass criteria: exit 0; `working/vsl/html/vsl.html` exists and carries the run's own
`ZHC-VSL-BUILDER deck_slug=<slug>` marker and a real `<video>` element; the gate timestamp
recorded in `working/checkpoints/vsl.json` falls inside [180s, 480s] and matches the §4 rule
against the sample's `webinar_timing.json`; `phase_verifiers.verify("P-U-VSL-BUILD", <sample>)`
passes. The install side verifies separately: `P-U-GHL-VSL` passes only on the installer's
`validate_receipt()` over `working/vsl/ghl_build_receipt.json`.

## 7. STATUS -- LIVE vs PENDING (re-verified 2026-10-14 for FIX-PLAN Item 23)

| Claim | Status | Evidence |
|---|---|---|
| The client is asked "would you like a VSL page?" | **LIVE** (deployed interview app / repo question bank) | `DEPT/intake/upsell-questions.json` v1.0.0; `DEPT/intake/deck-intake-questions.json` v1.5.0 orders 7.7/7.71. NOT live on the operator Mac Mini department (Wave D, separate unit) -- the live box's question bank is v1.2.0/50q with no upsell questions (`CONTROL/FABLE-TRUTH.md` §6). |
| The answer is captured and stored | **LIVE** in the repo interview-app bridge | `DEPT/intake/interview-app/bridge/intake_writer.py` maps `want_vsl_page` -> `WANT_VSL_PAGE`; see `SALES-CHECKOUT-BUILDER-SOP.md` §1's KNOWN GAP (identical mapping caveat applies to `VSL_PAGE_DECLINED_REASON`). |
| A `P-U-VSL-BUILD` phase exists in the manifest | **LIVE** | Live `PIPELINE-MANIFEST.json`, order 8.93, correctly sequenced after `P9.6-WEBINAR-VIDEO`. |
| An executor script exists | **LIVE** | `DEPT/scripts/vsl_builder.py` (the Wave C executor); `--selftest` passes offline. |
| A verifier / test exists | **LIVE** | `phase_verifiers._verify_upsell_vsl_build` is registered for `P-U-VSL-BUILD`; `AF-U-VSL-BUILD` is declared in the manifest's `autofails[]` and in `MASTER-QC-AUTOFAIL-RULESET.md`; coverage in `test_upsell_verifiers.py` (the elected build is produced by ACTUALLY RUNNING the builder) and `test_upsell_intake_shape.py`. |
| `P9.6-WEBINAR-VIDEO` (the video this phase depends on) exists and is enforced | **LIVE** | `P9.6-WEBINAR-VIDEO`, order 8.92, in `PIPELINE-MANIFEST.json`; `DEPT/scripts/build_webinar_video.py` + `WEBINAR-BUILDER-SOP.md`; the dependency is enforced by the executor and re-checked by the verifier via `verify_video_dependency()`. |
| The install path exists and is verified | **LIVE** | `P-U-GHL-VSL` + `P-U-FORM-GATE` execute via `ghl_external_installer.py` (PRES-011); completion requires `validate_receipt()` (adapter IDs + matching-location readback + ops-ledger provenance). The delegated Skill 6 / Skill 44 execution itself is staffed per run, as with the sales funnel. |
| The Gauntlet VSL design is a current alternative | **RETIRED** (2026-10-14) | Archived byte-identical in `presentations/archive/vsl-gauntlet/`; design preserved without authority in `VSL-GAUNTLET-SPEC-NOTE.md`; Guard B patterns `vsl-gauntlet-*` lint its values against silent return. |
| The flow (VSL page + gate) has been proven end-to-end, by hand, once | **LIVE (historical), not repeatable from this repo alone** | Loop 2C, COMPLETE 2026-08-07, render-verified, gate built in. Client-specific artifacts correctly excluded from this repo. |

**Plain statement:** a client who answers "yes" gets the question asked, the answer recorded,
the manifest phase declared (order 8.93, correctly sequenced after `P9.6-WEBINAR-VIDEO`), the page
built by `vsl_builder.py`, and the funnel install executed and receipt-proven by `P-U-GHL-VSL`.
There is one VSL design; this SOP is its doctrine.

## 8. HANDBACK (landed schema)

The build phase records into `working/checkpoints/vsl.json` (merged, never clobbered):
`deck_slug`, the gate resolution, `video_path` + `video_hosted`, the resolved
`gate_timestamp` (seconds + source, per §4), `vsl_copy` / `vsl_render` / `vsl_html` paths,
`built_at`, and a `status` (`deferred` / `waived` / `fail_closed` / `video_missing` /
`design_failed` / `html_content_gate_failed` / `built_offline_no_push` / `built`).

The install phase's proof is separate and lives at `working/vsl/ghl_build_receipt.json`
(owned by `P-U-GHL-VSL`): the adapter funnel/page IDs, the matching-location readback, and
the ops-ledger provenance that `ghl_external_installer.validate_receipt()` checks. The
waiver record (`want_vsl_page` value +, if explicitly "no," the verbatim
`client_request_quote`) is carried in the phase ledger's `gate` object.
