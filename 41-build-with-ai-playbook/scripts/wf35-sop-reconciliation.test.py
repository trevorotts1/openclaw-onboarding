#!/usr/bin/env python3
"""WF35 focused test — existing SOP and Skill 41 reconciliation (B22 / IG-PAGE-01 doc side).

Asserts externally meaningful doctrine in the documents agents actually retrieve:

  * the fixed private-primary ladder is gone and the operation-aware public-first
    decision is present, with the native/local responder distinction;
  * each form / funnel / website SOP names the exact registry operations and the
    rail-independent functional contract it must prove;
  * the Skill 44 checklist and quality rubric keep their existing gates (WF-4,
    WF-12, WF-20, WF-22, 8.5) and add the new capability / schema / revision /
    controlled-test evidence items;
  * Skill 41 keeps its dependency-first rule and honest-gap floor and no longer
    calls CAF-direct the primary path;
  * design / approval / verbatim-snippet / copy-floor gates are still enforced
    (IG-PAGE-01 doc side);
  * no second SOP cluster, no operator path, no banned identifier is introduced.

Stdlib only. Run from the repository root or any cwd:

    python3 -I 41-build-with-ai-playbook/scripts/wf35-sop-reconciliation.test.py

Exit 0 = every assertion holds. Exit 1 = one or more assertions failed (each
failure is named). This is a document contract test: it proves the retrieved
doctrine, not a live GHL behavior.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

CHANGED = [
    "universal-sops/SOP-CONV-AI-01-OPERATING-THE-CONVERSATIONAL-AI-SYSTEM.md",
    "universal-sops/form-craft/SOP-FORM-01-INTAKE.md",
    "universal-sops/form-craft/SOP-FORM-03-DEPENDENCIES.md",
    "universal-sops/form-craft/SOP-FORM-04-BUILD.md",
    "universal-sops/form-craft/SOP-FORM-05-CERTIFY.md",
    "universal-sops/funnel-craft/SOP-FUNNEL-04-BUILD.md",
    "universal-sops/funnel-craft/SOP-FUNNEL-05-CERTIFY.md",
    "universal-sops/website-craft/SOP-WEB-04-BUILD.md",
    "universal-sops/website-craft/SOP-WEB-05-CERTIFY.md",
    "universal-sops/funnel-automation-build-quality-rubric.md",
    "44-convert-and-flow-operator/references/workflow-build-checklist-template.md",
    "44-convert-and-flow-operator/references/workflow-quality-rubric.md",
    "44-convert-and-flow-operator/references/workflow-timing.md",
    "41-build-with-ai-playbook/SKILL.md",
    "41-build-with-ai-playbook/INSTRUCTIONS.md",
    "41-build-with-ai-playbook/protocols/verification-checklist.md",
    "41-build-with-ai-playbook/references/qc-rubric.md",
    "41-build-with-ai-playbook/references/ghl-workflow-ai-builder.md",
    "41-build-with-ai-playbook/references/ghl-dependency-protocol.md",
    "41-build-with-ai-playbook/references/wf35-existing-sop-edit-manifest.md",
]

failures: list[str] = []
checks = 0


def text(rel: str) -> str:
    p = ROOT / rel
    if not p.is_file():
        failures.append(f"MISSING FILE: {rel}")
        return ""
    return p.read_text(encoding="utf-8")


def has(rel: str, needle: str, label: str) -> None:
    global checks
    checks += 1
    body = text(rel)
    if needle not in body:
        failures.append(f"{rel}: missing {label!r} ({needle!r})")


def has_ci(rel: str, needle: str, label: str) -> None:
    global checks
    checks += 1
    body = text(rel).lower()
    if needle.lower() not in body:
        failures.append(f"{rel}: missing {label!r} ({needle!r})")


def lacks(rel: str, needle: str, label: str) -> None:
    global checks
    checks += 1
    body = text(rel)
    if needle in body:
        failures.append(f"{rel}: stale {label!r} still present ({needle!r})")


# ---------------------------------------------------------------- SOP-CONV-AI-01
CONV = "universal-sops/SOP-CONV-AI-01-OPERATING-THE-CONVERSATIONAL-AI-SYSTEM.md"
has(CONV, "operation-aware and public-first", "public-first route decision")
has(CONV, "`public_direct`", "public route class")
has(CONV, "`official_mcp`", "official MCP route class")
has(CONV, "`skill44_private`", "authorized private route class")
has(CONV, "`skill06_authoring`", "managed authoring route class")
has(CONV, "beta_not_enabled", "beta-denial handling")
has(CONV, "Compile-time versus native runtime", "compile-time/runtime split")
has(CONV, "exactly one primary", "single-responder contract")
has(CONV, "activation evidence", "activation evidence requirement")
has(CONV, "ghl-hybrid-operations", "single canonical cluster pointer")
lacks(CONV, "Option 1 PRIMARY", "private-primary ladder")
lacks(CONV, "Tier 0 caf-direct", "private-primary tier label")
# preserved controls
has(CONV, "I Do You Do brainstorm", "brainstorm/intake")
has(CONV, "judges its own completion", "independent QC")
has(CONV, "TEST MODE", "client rehearsal")
has(CONV, "registry hygiene", "registry/visual hygiene")

# ------------------------------------------------------------------ form SOPs
F01 = "universal-sops/form-craft/SOP-FORM-01-INTAKE.md"
has(F01, "**submission outcome**", "submission outcome intake field")
has(F01, "**consent / data requirements**", "consent/data intake field")
has(F01, "**requested artifact**", "form vs survey vs quiz intake field")
has(F01, "marketing quiz", "marketing-quiz distinction")
has(F01, "AF-FORM-INTAKE-LOCATION", "single-client location gate kept")

F03 = "universal-sops/form-craft/SOP-FORM-03-DEPENDENCIES.md"
has(F03, "custom_fields.create", "public custom-field create row")
has(F03, "tags.create", "public tag create row")
has(F03, "custom_values.create", "public custom-value create row")
has(F03, "actual resource mapping", "recorded resource mapping")
has(F03, "AF-FORM-DEP-LEDGER-MISSING", "ledger gate kept")

F04 = "universal-sops/form-craft/SOP-FORM-04-BUILD.md"
has(F04, "forms.authoring", "form authoring route row")
has(F04, "`skill06_authoring`", "managed authoring class")
has(F04, "does not prove create support", "discovery-is-not-create rule")
has(F04, "AF-FORM-EMBED-VERBATIM", "verbatim embed gate kept")
has(F04, "AF-FORM-INVENTED-SELECTOR", "no-invented-selector gate kept")
has(F04, "AF-FORM-BUILD-DRAFT", "draft-only boundary kept")

F05 = "universal-sops/form-craft/SOP-FORM-05-CERTIFY.md"
has(F05, "rail-independent", "rail-independent functional contract")
has(F05, "on_submit", "submission outcome proof")
has(F05, "AF-FORM-MARKER-DOM", "rendered-DOM gate kept")
has(F05, "AF-FORM-CERT-MISSING", "independent QC gate kept")
has(F05, "human approval", "human approval kept")

# ---------------------------------------------------------------- funnel SOPs
FN04 = "universal-sops/funnel-craft/SOP-FUNNEL-04-BUILD.md"
has(FN04, "funnels.pages.list", "public funnel inventory row")
has(FN04, "funnels.redirects.create", "public redirect row")
has(FN04, "media.upload", "public media upload row")
has(FN04, "funnels.pages.authoring", "authoring route row")
has(FN04, "Skill 6 is the ONE GHL construction", "Skill 6 construction ownership")
has(FN04, "full-width", "native full-width verification kept")
has(FN04, "AF-FUN-CANONICAL-BYPASS", "canonical-bypass gate kept")
has(FN04, "funnel-build QC ≥ 8.5", "funnel QC threshold kept")

FN05 = "universal-sops/funnel-craft/SOP-FUNNEL-05-CERTIFY.md"
has(FN05, "TRANSPORT-INDEPENDENT EVIDENCE", "transport-independent evidence")
has(FN05, "unsupported", "unsupported sub-result disclosure")
has(FN05, "pending", "pending sub-result disclosure")
has(FN05, "PROCESS-CERTIFICATE.json", "signed certificate kept")
has(FN05, "AF-FUN-TY-PITCH", "clean thank-you gate kept")
has(FN05, "never auto-publishes", "no auto-publication kept")

# --------------------------------------------------------------- website SOPs
W04 = "universal-sops/website-craft/SOP-WEB-04-BUILD.md"
has(W04, "SHARED ROUTING CONTRACT", "shared routing contract")
has(W04, "SOLE GHL construction owner", "Skill 6 sole construction owner")
has(W04, "full-width", "full-width verification")
has(W04, "single embed", "single-widget verification")

W05 = "universal-sops/website-craft/SOP-WEB-05-CERTIFY.md"
has(W05, "Widget integration", "widget functional check")
has(W05, "Meeting / calendar links", "meeting-link functional check")
has(W05, "full_width", "certificate full-width field")
has(W05, "copy floors", "copy floors kept")
has(W05, "prove_web_pages.py", "copy prover kept")
has(W05, "human approval", "human approval kept")

# ------------------------------------------------------- FAB build-quality rubric
FAB = "universal-sops/funnel-automation-build-quality-rubric.md"
has(FAB, "8.5", "8.5 threshold kept")
has(FAB, "Transport-independent scoring", "transport-independent scoring")
has(FAB, "Graph preservation is part of fidelity", "graph preservation check")
has(FAB, "Functional-integration check", "functional integration check")
has(FAB, "no hard miss", "hard-miss rule kept")
has(FAB, "WF-1..28", "checklist range updated")

# ------------------------------------------------------------ Skill 44 checklist
CHK = "44-convert-and-flow-operator/references/workflow-build-checklist-template.md"
for n in range(1, 29):
    has(CHK, f"WF-{n}", f"WF-{n} present")
has(CHK, "Per-Location Public Capability", "WF-25 capability item")
has(CHK, "Current Step Schemas and API Validation", "WF-26 schema/validation item")
has(CHK, "Revision Preservation", "WF-27 revision item")
has(CHK, "Log-Backed Controlled Test", "WF-28 controlled-test item")
has(CHK, "branches=", "machine branch-count evidence")
has_ci(CHK, "email body", "WF-22 email-body wording kept")

QR = "44-convert-and-flow-operator/references/workflow-quality-rubric.md"
has(QR, "(D1*20 + D2*15 + D3*15 + D4*12 + D5*12 + D6*10 + D7*8 + D8*8) / 100",
    "unchanged weighted formula")
has(QR, "8.5", "8.5 ship threshold kept")
has(QR, "Three proof tiers", "definition/read-back/runtime tiers")
has(QR, "Definition", "definition tier")
has(QR, "Read-back", "read-back tier")
has(QR, "Runtime", "runtime tier")
has(QR, "Route and contract evidence", "route/contract evidence section")

TIM = "44-convert-and-flow-operator/references/workflow-timing.md"
has(TIM, "IANA timezone", "resolved timezone")
has(TIM, "Resolve the real date and timezone", "real date/timezone resolution")
has(TIM, "never replace a date condition with an unrelated relative wait", "anti-bypass rule kept")

# ------------------------------------------------------------------- Skill 41
SK = "41-build-with-ai-playbook/SKILL.md"
IN = "41-build-with-ai-playbook/INSTRUCTIONS.md"
for rel in (SK, IN):
    lacks(rel, "CAF direct (PRIMARY)", "CAF-direct primary claim")
    has(rel, "public_direct", "public-first route")
    has(rel, "skill44_private", "authorized private rail")
    has(rel, "skill06_authoring", "managed authoring rail")
    has_ci(rel, "never fabricat", "no-fabrication floor")
    has_ci(rel, "honest gap", "honest-gap path")
has(IN, "must exist FIRST", "dependency-first rule (qc-dependency-order)")
has_ci(IN, "BEFORE generating", "dependency-before-prompt rule")
has(SK, "compile-time", "compile-time artifact statement")
has(SK, "ghl-hybrid-operations", "single cluster pointer")
has(SK, "8 sections", "8-section template kept")

VC = "41-build-with-ai-playbook/protocols/verification-checklist.md"
has(VC, "Route and contract evidence", "route evidence in verification")
has(VC, "runtime: not_run", "runtime tier honesty")
has(VC, "WF-1..WF-28", "checklist cross-reference updated")
lacks(VC, "WF-1..WF-21 checklist is authoritative", "obsolete cross-reference")

QCR = "41-build-with-ai-playbook/references/qc-rubric.md"
has(QCR, "8.5 to pass", "8.5 pass threshold kept")
has(QCR, "Route/Contract Evidence", "route evidence folded into existing category")
has(QCR, "no new category and no new threshold", "no new QC bureaucracy")

AI = "41-build-with-ai-playbook/references/ghl-workflow-ai-builder.md"
has(AI, "Compile-time, not runtime", "compile-time vs runtime reference")
has(AI, "NOT capability", "catalog/discovery is not capability evidence")

DEP = "41-build-with-ai-playbook/references/ghl-dependency-protocol.md"
has(DEP, "verified public operations first", "public-first dependency route")
has(DEP, "custom_fields.list/create", "public dependency rows named")
has(DEP, "ZHC-", "ZHC prefix rule kept")

# ------------------------------------------------------------------- boundaries
for rel in CHANGED:
    body = text(rel)
    checks += 1
    if "ghl-operations/SOP-" in body:
        failures.append(f"{rel}: forbidden second cluster path present")
    if "/Users/" in body or "blackceomacmini" in body:
        failures.append(f"{rel}: operator path or banned identifier present")

print(f"WF35 reconciliation test: {checks} assertions over {len(CHANGED)} files")
if failures:
    for f in failures:
        print("FAIL " + f)
    print(f"RESULT: FAIL ({len(failures)} failing assertion(s))")
    sys.exit(1)
print("RESULT: PASS")
sys.exit(0)
