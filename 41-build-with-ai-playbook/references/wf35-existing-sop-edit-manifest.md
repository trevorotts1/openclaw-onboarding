# WF35-CP01 — Existing SOP and Skill 41 reconciliation edit manifest

**Status:** frozen interface checkpoint (WF35-CP01). Published before the content edits so
dependent lanes can read the exact target set, the canonical authority for each edit, and the
owning source path. A later change to this set is WF35-CP02 with a migration note and the
affected-consumer list.

**Scope boundary:** this lane owns ONLY the existing conversational / form / funnel / website
SOPs, the standing funnel-and-automation build-quality rubric, the Skill 44 workflow
checklist / quality-rubric / timing references, and Skill 41 doctrine. It creates **no**
competing SOP cluster: WF16 owns the single canonical GHL operations cluster and its README.
This lane does not write `36-ghl-mcp-setup/GHL-LOOKUP-SOP.md`,
`38-conversational-ai-system/references/GHL_AI_LAYERS.md`, or
`38-conversational-ai-system/protocols/voice-phone-protocol.md`.

**Authority for every row:** Document 1 revision 3.0 §32.2 (rows 1, 3-9, 11-13), §32.3, §5.3,
§5.4, §5.5, §17.5 B22, §19.1 WF35. Executable route facts are read from
`44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py`
(frozen operation registry) and `.../public/adapter.py` (`PublicGhlAdapter.call`,
`PublicGhlAdapter.dispatch`). No route fact in this manifest is inferred from an HTTP verb.

## Route vocabulary frozen for this lane

| Route class (registry literal) | Meaning used in every edited document |
|---|---|
| `public_direct` | Supported public REST row; the adapter sends it only when the `(operation_id, tenant)` capability record allows it. |
| `official_mcp` | Only an operation actually discovered and authorized in the session; never assumed from a family listing. |
| `skill44_private` | The existing authorized Firebase/internal operation, for a documented public gap only. |
| `skill06_authoring` | Managed UI/browser authoring because the row declares no public contract. |
| `capability_gap` | No route is established; the honest gap is reported, never a fabricated success. |

A catalog entry, an MCP discovery result, or a documentation page never enables an operation.
Enablement stays with the per-`(operation_id, tenant)` capability evidence.

## Edit manifest

| # | Owning source path | Stale claim or missing statement | Required change | Canonical authority |
|---|---|---|---|---|
| 1 | `universal-sops/SOP-CONV-AI-01-OPERATING-THE-CONVERSATIONAL-AI-SYSTEM.md` | §3 and §8 present a fixed **private-primary ladder**: "Option 1 PRIMARY (Skill 44 … Tier 0 caf-direct) … Option 2 FALLBACK (Skill 41)". | Replace with the operation-aware, public-first decision: resolve the registry row and capability evidence first; public REST when the row is `public_direct` and the capability record allows it; official MCP only for an exact discovered/authorized operation; `skill44_private` only for a documented gap; `skill06_authoring` for authoring rows. Add the native-responder vs local/self-hosted-responder distinction and the activation-evidence requirement. Keep brainstorm/intake, the 4-part build artifacts, independent QC, client rehearsal, and registry/visual hygiene. | Doc 1 §32.2 row 1; §5.3; §25 responder ownership |
| 2 | `universal-sops/form-craft/SOP-FORM-01-INTAKE.md` | The brief never captures the submission outcome, consent/data requirements, or whether the request is a form, a survey, or a marketing quiz. | Add those three intake facts to the one-block brief and the preflight list. Keep the approved brief and the single-client `location_id` truth gate. | Doc 1 §32.2 row 3; §30 |
| 3 | `universal-sops/form-craft/SOP-FORM-03-DEPENDENCIES.md` | "Custom fields + tags are created through the GHL-API rail" without per-operation capability evidence or a record of the actual resource mappings. | Require Skill 44's verified public operations (`custom_fields.list/create`, `tags.list/create`, `custom_values.list/create`) where the row and capability allow; record the actual created/reused resource ids and keys in the ledger. Keep dependency-first creation, naming, and reuse-before-create. | Doc 1 §32.2 row 4; §5.3 |
| 4 | `universal-sops/form-craft/SOP-FORM-04-BUILD.md` | Implies the builder/API surface is generally available and can be inferred from discovery; no exact operation selection is stated. | Add the exact operation capability selection: `forms.list` / `forms.submissions.list` are reads only; `forms.update`, `forms.authoring`, `surveys.authoring`, `funnels.pages.authoring` are `skill06_authoring` rows with no public contract; `forms.custom_files.upload` is `B-NO-ADAPTER`. State explicitly that discovering Forms or MCP tools proves nothing about create support. Keep resolved plan, live selector capture, draft boundary, real id/embed, and the unchanged vendor snippet. | Doc 1 §32.2 row 5; §5.1; §8 |
| 5 | `universal-sops/form-craft/SOP-FORM-05-CERTIFY.md` | Verification stops at render + tag workflow but does not require the same functional submission contract on public-built and private/UI-built forms. | Verify a real submission and the resulting tag workflow with one functional contract regardless of the rail used to build. Keep rendered DOM, actual contact outcome, independent QC, human approval. | Doc 1 §32.2 row 6; IG-PAGE-02 |
| 6 | `universal-sops/funnel-craft/SOP-FUNNEL-04-BUILD.md` | Treats every non-Skill-6 call as ungoverned and does not separate public inventory/redirect/media operations from visual construction; no route receipt is required. | Keep Skill 6 as sole construction owner while naming the `public_direct` inventory/redirect/media rows (`funnels.list`, `funnels.pages.list`, `funnels.pages.count`, `funnels.redirects.create`, `media.upload`, `media.folders.create`) as governed operations issued through the shared adapter; require one route receipt per logical operation. Preserve native full-width verification, approved copy/images, native commerce, and branch correctness. | Doc 1 §32.2 row 7; §5.5 |
| 7 | `universal-sops/funnel-craft/SOP-FUNNEL-05-CERTIFY.md` | Certificate evidence is described per rail; unsupported or pending sub-results are not explicitly disclosed. | Require transport-independent evidence and an explicit unsupported/pending sub-result list. Keep the clean thank-you policy, signed process certificate, preview approval, and no automatic publication. | Doc 1 §32.2 row 8; IG-RELEASE-02 |
| 8 | `universal-sops/website-craft/SOP-WEB-04-BUILD.md` | The routing contract is not named; widget integration and full-width settings are not verified at build time. | Use the shared routing contract (registry row + capability evidence) with Skill 6 as sole construction owner; verify widget integration and full-width settings before the build is called verified. Keep the approved copy source, no competing GHL builder, and required visuals. | Doc 1 §32.2 row 9; IG-PAGE-01 |
| 9 | `universal-sops/website-craft/SOP-WEB-05-CERTIFY.md` | Certification verifies render and copy only. | Add functional widget and meeting-link checks to the existing render/copy verification. Keep copy floors, independent QC, real preview, human approval. | Doc 1 §32.2 row 10; IG-PAGE-01 |
| 10 | `universal-sops/funnel-automation-build-quality-rubric.md` | The rubric is transport-blind and lacks graph-preservation and functional-integration checks. | Score behavior and evidence regardless of transport; add graph-preservation and functional-integration checks. Keep the 8.5 threshold, dependency, timing, complete-branch, and no-false-completion rules unchanged. | Doc 1 §32.2 row 11; §17.5 B22 |
| 11 | `44-convert-and-flow-operator/references/workflow-build-checklist-template.md` | Items stop at WF-22 and omit per-location public capability, current step schemas, API validation, revision preservation, and a log-backed controlled test. | Append WF-23..WF-28 (no renumbering) for graph-validator evidence, trigger entrance link, per-location public capability, current step schemas + API validation, revision preservation, and log-backed controlled test. Keep every existing WF item and gate verbatim in meaning. | Doc 1 §32.2 row 12; §5.1; §22 |
| 12 | `44-convert-and-flow-operator/references/workflow-quality-rubric.md` | Dimensions do not separate route/contract evidence from definition, read-back, and runtime proof. | Add the route/contract evidence requirement and the three proof tiers. Keep the eight dimensions, their weights, the 8.5 ship threshold, and the independent-reviewer rule. | Doc 1 §32.2 row 13; §5.5 |
| 13 | `44-convert-and-flow-operator/references/workflow-timing.md` | Timing contract does not require resolving the real date/timezone source or validating the public/private action representation before building. | Require the resolved source + IANA timezone, and validation that the chosen rail can actually represent the scheduled action. Keep the refusal to replace a date condition with an unrelated relative wait. | Doc 1 §32.2 row 14; §22 |
| 14 | `41-build-with-ai-playbook/SKILL.md`, `41-build-with-ai-playbook/INSTRUCTIONS.md`, and the Skill 41 `references/` that carry route doctrine | Skill 41 states "Option 1 — CAF direct (PRIMARY)" and does not separate compile-time Build-with-AI prompt generation from native runtime behavior. | Make the build-path choice operation-aware and public-first; keep Build-with-AI as the compile-time Layer 0 prompt generator; state that the prompt does not configure native runtime responders; keep the 8-section template, the dependency-first rule, the 12-point checklist, and the honest-gap floor. | Doc 1 §32.2 rows 1-14 (Skill 41 doctrine); Doc 1 §25; Doc 2 §WF35 |

## Generated / owned-elsewhere files this lane will NOT write

| File | Owner | Request this lane raises |
|---|---|---|
| `universal-sops/_content-manifest.json` | WF21 (generated manifests) | Regenerate with `scripts/hash-universal-sops-manifest.py` after these source edits land; the changed-source list is in the builder checkpoint. |
| `44-convert-and-flow-operator/QC.md` | WF14 (Skill 44 runtime prose and QC-doc corrections) | Update the "22 WF items (WF-1 through WF-22)" line to the appended item set. |
| `universal-sops/ghl-hybrid-operations/SOP-GHL-08-NATIVE-AI.md` and the cluster README | WF16 | Existing SOPs point into this cluster; this lane creates no second cluster. |
| Skill versions, `CHANGELOG`, `VERSION`, frontmatter versions | WF21 | None; this lane does not bump them. |

## Acceptance mapping (this lane)

| ID | What this lane proves | Fixture |
|---|---|---|
| B22 | Existing SOPs and Skill 41 match the new routing doctrine; no second cluster; source and bundle/retrieval copies stay coherent within this lane's scope | `41-build-with-ai-playbook/scripts/wf35-sop-reconciliation.test.sh` |
| IG-RELEASE-01 (source side) | Source documents and the changed-source manifest agree; distribution/regeneration is handed to WF21 | the changed-source list in the builder checkpoint |
| IG-PAGE-01 (doc side) | Design/intake/copy/full-width/SEO gates remain explicitly enforced in the form/funnel/website SOPs | the same fixture's design-gate assertions |
