# SOP -- External GHL Installs (P-U-GHL-SALES / P-U-GHL-VSL / P-U-FORM-GATE) [PRES-011]

**Status (PRES-011, 2026-09-09):** LANDED. Executor
`DEPT/scripts/ghl_external_installer.py`; manifest v69 wires the three
phases as script executors with explicit `executor.capability`
(`ghl_page_install` / `ghl_workflow_install`, owning adapter skill06 /
skill44); verifiers `phase_verifiers._verify_ghl_sales_install` /
`_verify_ghl_vsl_install` / `_verify_form_gate_install`; autofails
AF-U-GHL-SALES / AF-U-GHL-VSL / AF-U-FORM-GATE; this SOP. Source-only proof
(QC checks 1-3) in `DEPT/scripts/tests/test_pres011_ghl_external.py` +
module `--selftest`. Live test-location acceptance (QC check 4) is FUTURE
work -- see §8.

## 1. Why this exists

The three phases install into the client's GoHighLevel location -- an
EXTERNAL effect. Before PRES-011 they declared `executor.kind=agent`, so
the dispatcher "completed" them by writing model text to one artifact file.
A JSON-looking receipt with no form, workflow or page behind it passed the
generic presence verifier. Strengthening the gate alone would have turned
false completion into endless retries; the executor is fixed in the same
wave (TODO PRES-011).

## 2. The rule (read first)

1. Models may draft validated PLANS (`ghl_install_plan.json`,
   `gate_form_skill44_plan.json`). Plans never complete anything.
2. Only successful Skill 06 / Skill 44 TOOL RESULTS write execution
   receipts. A plan-emitted result is `pending_external_execution`, never
   complete.
3. Every operation and receipt binds company/presentation(run deck_slug)/
   run_id/GHL location_id/page-form-workflow IDs/input hashes/execution_id/
   timestamp/remote readback. Credentials (PITs, Firebase tokens) NEVER
   enter artifacts -- only the non-secret location_id travels.
4. Remote IDs persist IMMEDIATELY after creation in
   `working/checkpoints/ghl_external_ops.json` (merged, never clobbered),
   with states dispatched/running/remote-created/verified and a resumable
   `next_action`. Kill-resume reuses recorded IDs -- never a duplicate.
5. A receipt with no matching ops-ledger execution (same execution_id +
   same remote IDs) is model text, however perfect-looking, and fails.

## 3. Canonical paths (reused, never reimplemented)

- Skill 06 page-install: `06-ghl-install-pages/tools/ghl_rest_canvas.py`
  (funnel_create/step_create/page_autosave + created_page_id readback;
  the WAF-gated calls run inside a live agent-browser eval, exactly as the
  builders' push plans document), `tools/ghl_builder.py`
  (subaccount_matches location hard gate, may_publish DRAFT default,
  resume_point never-recreate), `tools/ghl_workflow_builder.py`
  (managed-gateway Automations harness for the Tier-4 backstop).
- Skill 44 form/workflow: `caf workflows build --from-plan` under
  WriteLock (existing names refused, never duplicated) +
  `caf workflows list/export/get` readback; PLAN MODE + Step 0.7
  pre-build existence check; DRAFT-only workflows.
- Gate form contract: `DEPT/scripts/vsl-gate-form-spec.json`
  (SKILL44_WIDGET -> FORM: zhc_vsl_email + zhc_vsl_first_name +
  zhc_vsl_phone; Form-Submitted -> zhc_vsl_engaged tag workflow).
- Gate decisions: delegated to `sales_checkout_builder.
  resolve_sales_checkout_gate` / `vsl_builder.resolve_vsl_gate` (the SAME
  functions the page builders' own mains use) -- verifier and executor
  can never drift.

## 4. Phase contracts

- P-U-GHL-SALES (order 6.2, elected on WANT_SALES_CHECKOUT=yes):
  sales.html + checkout.html -> ONE funnel, TWO pages. Receipt
  `working/sales-checkout/ghl_build_receipt.json` (funnel_id +
  sales_page_id + checkout_page_id + readback + bindings).
- P-U-GHL-VSL (order 6.4, elected on WANT_VSL_PAGE=yes): vsl.html -> VSL
  page. Reuses this run's verified sales funnel_id when present (one
  funnel per client, mirroring vsl_builder.resolve_shared_funnel_id).
  Receipt `working/vsl/ghl_build_receipt.json`.
- P-U-FORM-GATE (order 5.6, elected on WANT_VSL_PAGE=yes): gate form +
  tag workflow. Receipts `ecosystem/gate-form.json` +
  `workflows/gate-workflow.json` -- BOTH required. Partial state (form
  created, workflow missing) resumes without duplicating the form.

## 5. Preflight (TODO step 1)

`ghl_external_installer.preflight_check_phase` refuses any external-effect
phase routed to a text writer (`executor.kind=agent/none`, or capability
text_artifact/multi_artifact) with AF-EXTERNAL-TEXT-ROUTING. The manifest
loader (`presentation_job/manifest.py` V6) enforces the same rule at load,
so a bad manifest never reaches a paid dispatch.

## 6. Blockers (phase-scoped; deck work continues)

WRONG_LOCATION (declared vs bound location disagree -- cross-client write,
refused), UNBOUND_LOCATION/MISSING_INPUT (offline plan still emitted,
honestly pending). Executor exits 5 with an actionable receipt; the
verifier surfaces the same code -- never deck failure.

## 7. Board/CEO progress (TODO step 4)

Script phases already emit start/done through the engine's existing
reporter; blockers land as actionable receipts. Bounded repair
escalation: the ops ledger's `next_action` names the exact resume step,
and the dispatcher's existing retry ceiling parks (loudly, with a marker)
instead of looping forever.

## 8. Live acceptance (QC check 4 -- FUTURE, not performed here)

On an authorized TEST GHL location: install sales and VSL separately;
verify rendered content, page IDs, form IDs and client/run binding.
Next action: operator authorizes the test location, runs
`ghl_external_installer.py --run-dir <run> --phase P-U-GHL-SALES`, then
`--phase P-U-GHL-VSL` and `--phase P-U-FORM-GATE` behind a live Skill
06/44 session, and records page/form/workflow IDs + readback in
run/evidence/PRES-011/<SHA>/. Until then check 4 stays open and no
production install is claimed.
