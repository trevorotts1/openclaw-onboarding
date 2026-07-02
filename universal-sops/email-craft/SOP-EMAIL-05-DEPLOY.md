# SOP-EMAIL-05: DEPLOY DRAFT-ONLY + HUMAN APPROVE + CERTIFICATE

**Cluster:** Email-Craft Rules (`universal-sops/email-craft/`)
**Master authority:** `EMAIL-PIPELINE-MANIFEST.json` + `50-email-engine/run_email_engine.py`
**Owning roles:** Automation Workflow Specialist (CRM) deploys; Email Campaign Strategist (Marketing) owns the approval pause
**Stage:** P4-DEPLOY + P5-APPROVE
**Produces:** `working/deploy/build-plan.json`, `working/deploy/approval.json`, `delivery/PROCESS-CERTIFICATE.json`
**Gates this stage satisfies:** AF-PROCESS-INTEGRITY, AF-EMAIL-DEPLOY-UNAPPROVED, AF-EMAIL-SEND-BYPASS

---

## 0. WHY THIS SOP EXISTS

The Email Engine OWNS authorship + QC and DELEGATES deployment to Skill 44 (`caf`) as **workflow email steps, DRAFT-ONLY**. Nothing sends without an explicit human approval. The engine never authors a broadcast into a live send.

## 1. EMIT THE BUILD PLAN

After P3 passes, emit the Skill-44 build plan from the approved copy:

```
python3 50-email-engine/tools/emit_build_plan.py --run-dir <RUN_DIR>
```

The plan is the `caf` contract: a folder + workflow slug + `templates[]`, each `{type:"email", attributes:{subject, body(html), html, fromName:<founder>, ...}}`. Skill 44 wires it (draft-only); it does NOT author copy.

## 2. HAND TO SKILL 44 (DRAFT-ONLY)

```
caf workflows build --from-plan working/deploy/build-plan.json     # draft workflow
```

Skill 44's `qc-built-workflow.sh >= 8.5` runs on the deployed draft. A hand-rolled email sender in the run directory (a direct GHL/SMTP send outside this sanctioned draft-only handoff) is AF-EMAIL-SEND-BYPASS.

## 3. THE HUMAN APPROVAL PAUSE (P5)

Nothing sends until a person approves. Record `working/deploy/approval.json` with `approved: true` + `approved_by`. A deploy reached without it is AF-EMAIL-DEPLOY-UNAPPROVED.

## 4. THE PROCESS CERTIFICATE

The whole run is driven through the ONE sanctioned entry:

```
50-email-engine/email-engine-entry.sh --run-dir <RUN_DIR>
```

`run_email_engine.py` walks P1->P4 in order with NO phase skips and issues `delivery/PROCESS-CERTIFICATE.json` ONLY on a full pass (`all_phases_pass:true`, `verified_phases == 4`, `deploy_mode: draft-only`). The certificate SHA is deterministic (computed over the ordered phases + sequence identity + email count, not the clock). No certificate -> AF-PROCESS-INTEGRITY; the deploy is not unlocked. The certificate attests the governed pipeline ran in order; it never authorizes a send.
