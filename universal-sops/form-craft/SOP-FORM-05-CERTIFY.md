# SOP-FORM-05: RENDER-VERIFY + TAG WORKFLOW + PREVIEW/APPROVE + CERTIFY

**Cluster:** Form-Craft Rules (`universal-sops/form-craft/`)
**Canonical GHL operations cluster:** cross-craft GHL procedures (meeting rooms, native AI, knowledge bases, widgets, Projects sync, workflow monitoring, marketing quizzes) live in the single `universal-sops/ghl-hybrid-operations/` cluster (its README is the index). This SOP is not duplicated there; do not fork a second `ghl-operations/` cluster.
**Master authority:** `06-ghl-install-pages/tools/ghl_verify.py` (`render_check`) + `06-ghl-install-pages/qc-built-form.sh` (QC-F1..F11) + Skill 44 workflow (WF-1..21, rubric >= 8.5)
**Owning role:** Skill 6 QC + Skill 44 tag workflow → owner (human approval)
**Stage:** P4-CERTIFY
**Produces:** `qc-built-form.sh` PASS, `render_check` 200, the tag workflow, a preview URL, a labeled downloads bundle
**Gates:** AF-FORM-RENDER-200, AF-FORM-MARKER-DOM, AF-FORM-TAG-WORKFLOW, AF-FORM-CERT-MISSING, AF-FORM-PROCESS-INTEGRITY

---

## 0. WHY THIS SOP EXISTS

A form is "done" only when the embed actually RENDERS on the host page AND a submission actually gets
its tag AND an independent gate proves every phase ran in order. A self-attested "all passed" is never
trusted — the operator's report is a hypothesis; `render_check` and `qc-built-form.sh` read the real DOM
and the real ledger chain.

## 1. RENDER VERIFY — 200 + MARKER IN THE RENDERED DOM

`ghl_verify.render_check` fetches the host page carrying the embed and asserts:

- HTTP **200** (else AF-FORM-RENDER-200), AND
- the form widget **marker present in the JS-hydrated DOM** — the `zhc_` / `data-form-id="<FORM_ID>"`
  marker after hydration (else AF-FORM-MARKER-DOM).

A GHL storage/autosave **201 is NOT verification** — the storage marker proves the blob was saved, not
that the widget renders. Screenshot desktop + mobile; the 50%-width field pairs MUST stack on mobile.

## 2. TAG ATTACHMENT — THE SKILL-44 WORKFLOW (built after the form id exists)

Tag creation happened at P2; **attachment** happens here. Because the GHL form builder has no native
add-tag control, Skill 44 builds a **"Form Submitted → Add Contact Tag `{{contact.zhc_…}}`"** workflow,
filtered to THIS form, using the form id parsed from the build. It runs under Skill 44's PLAN-MODE +
WF-1..28 + rubric >= 8.5. No such workflow (and no documented hidden-Tags-field alternative) ⇒
AF-FORM-TAG-WORKFLOW.

**The functional contract is rail-independent.** Whether the form was authored in the managed UI
(`forms.authoring` / `forms.update`, `skill06_authoring`), by a supported public row where one is
actually enabled, or by an authorized private gap fill, P4 proves the SAME intake contract from
SOP-FORM-01: one real submission produces the recorded `on_submit` outcome (contact upsert, the exact
`zhc_` tag, notification/redirect, workflow enrollment) and honours the recorded consent/data
requirements. A build that passes on one rail and not the other is not certified; the route used is
recorded on the certificate.

## 3. THE INDEPENDENT QC GATE

```
bash 06-ghl-install-pages/qc-built-form.sh <run-dir>
```

`qc-built-form.sh` (QC-F1..F11) is a SEPARATE fail-closed gate — it re-checks the built form (form under
the `ZHC ` name, custom fields/tags re-GET 200, embed marker in DOM, required-XOR-hidden, no invented
selectors, no banned/purged model slugs) and emits a PASS certificate only on a full pass. No PASS ⇒
AF-FORM-CERT-MISSING. A skipped phase or a broken ledger chain (brief → plan → deps → click list →
operator report → QC) ⇒ AF-FORM-PROCESS-INTEGRITY.

## 4. PUBLISH GUARD (human approval)

The pipeline STOPS at the **preview URL** (`…/widget/form/<FORM_ID>` + the host-page preview) plus a
labeled downloads bundle (the locked brief, `form-plan.json`, `form-dependency-plan.json`,
`form-click-list.json`, `form-operator-report.json`, the embed snippet, screenshots, the certificate).
**Going live is an explicit human approval** — the owner approves in the Review lane; the engine never
auto-publishes. Reporting is operator-verbose, never client-facing noise.

## 5. DEFINITION OF DONE

`render_check` 200 + the marker in the RENDERED DOM, the `Form Submitted → Add Contact Tag` workflow
built and confirmed, one real submission matching the recorded `on_submit` outcome and consent
contract, every custom field/tag re-GET 200 under its `zhc_` key, the routes used recorded on the
certificate, the form under its `ZHC ` container name, `qc-built-form.sh` PASS (QC >= 8.5), a preview
URL delivered, the downloads bundle labeled with the `<client>__<form>__<type>__vNN` grammar
(`type ∈ {brief, fields, deps, embed, preview}`), and human approval before any publish. Anything
short of this is NOT done.
