# QC Rules — {{PROJECT_NAME}}

**Project Slug:** {{project-slug}}
**Gate:** ≥ 8.5 weighted average to PASS. < 8.5 → return to writer with surgical fix directive.
**Max defect-loop depth:** 3 rounds per work item. After 3 fails: flag to owner.
**Model rule:** QC agent MUST run on a different model than the writer (Rule 6).

---

## Per-Deliverable-Type Rubrics

### Code / Configuration Rubric
Used for: code files, config files, CI/CD workflows, infrastructure specs.

| Dimension | Weight | 10 = Excellent | 0 = Fail |
|-----------|--------|----------------|----------|
| D1 Correctness | 30% | All acceptance criteria met; zero logic errors; all APIs used correctly per verified docs | One or more acceptance criteria unmet OR verified API misuse |
| D2 Security | 20% | No hardcoded secrets; env vars used; no exposed credentials | Hardcoded secret or credential in output |
| D3 Readability | 20% | Clear naming; inline comments on non-obvious logic; consistent formatting | Cryptic variable names; zero comments; inconsistent style |
| D4 Efficiency | 15% | No redundant code; no unused imports; minimal footprint | Significant dead code or redundancy |
| D5 Handoff | 15% | Building dept can deploy/run without follow-up questions | Missing setup instructions or config docs |

**Weighted gate:** sum(D_i × weight_i) ≥ 8.5

---

### Copy / Content Rubric
Used for: website copy, marketing content, email sequences, documentation.

| Dimension | Weight | 10 = Excellent | 0 = Fail |
|-----------|--------|----------------|----------|
| D1 Message Clarity | 30% | Core message communicated in ≤2 sentences; no jargon without definition | Core message unclear after first read |
| D2 Accuracy | 25% | All factual claims verified; no fabricated statistics | Unverified claim or fabricated statistic |
| D3 Brand Alignment | 20% | Voice consistent with SOUL.md / USER.md brand standards | Contradicts stated brand voice |
| D4 Conversion Focus | 15% | Clear call-to-action; logical flow toward desired outcome | No CTA or illogical flow |
| D5 Handoff | 10% | Formatted for direct implementation (correct file format, metadata included) | Not in deployment-ready format |

---

### Design / Specification Rubric
Used for: Figma specs, UX flows, system architecture diagrams, wireframes.

| Dimension | Weight | 10 = Excellent | 0 = Fail |
|-----------|--------|----------------|----------|
| D1 Completeness | 35% | All screens/components specified; no TBD sections | Key screens or states missing |
| D2 Verifiability | 25% | Each spec item is binary-testable by the builder | Vague specs requiring builder interpretation |
| D3 Consistency | 20% | Consistent naming, spacing, style across all specs | Inconsistent naming or style |
| D4 Feasibility | 10% | No technically infeasible requirements | Spec requires unavailable technology |
| D5 Handoff | 10% | Annotated and ready for builder — no follow-up needed | Missing annotations |

---

### Infrastructure / Deployment Rubric
Used for: Vercel config, CI/CD pipelines, database schema, environment setup.

| Dimension | Weight | 10 = Excellent | 0 = Fail |
|-----------|--------|----------------|----------|
| D1 Correctness | 35% | Config produces the specified behavior; no syntax errors | Config produces wrong behavior or fails to parse |
| D2 Security | 25% | Secrets in env vars; principle of least privilege applied | Hardcoded secrets or over-permissioned service |
| D3 Idempotency | 20% | Running config twice has the same result as once | Config creates duplicates or errors on re-run |
| D4 Observability | 10% | Logging/monitoring configured; errors surfaced | No logging or error visibility |
| D5 Handoff | 10% | Building dept can apply this config without follow-up | Missing context or undocumented assumptions |

---

## Defect-Loop Protocol

1. QC agent scores deliverable. If <8.5: identify the LOWEST-scoring dimension.
2. Issue surgical fix directive: "D{N} {Name} ({score}): [specific issue — quote the exact segment]. Fix: [one sentence]."
3. Writer applies fix. Re-submits. QC re-scores.
4. Repeat up to 3 rounds.
5. After 3 rounds without reaching 8.5: `{pass: false, escalate: true}` → Chief Project Architect → owner.

**NEVER:**
- Pass a deliverable below 8.5.
- Issue a fix directive that rewrites the whole deliverable.
- Run QC on the same model as the writer.

---

## Verifiable Pass Definition

A deliverable has a "verifiable pass" when:
1. QC score ≥ 8.5 (logged in `checklist.md`).
2. QC ran on a different model than the writer (logged in QC verdict).
3. The corresponding checklist item in `checklist.md` is marked ✅.
4. Commit SHA recorded in `checklist.md`.
5. No open issue in `todo.md` referencing this work item.

---

## Custom Rubrics (Add Below for This Project)

{{ADD project-specific quality rules here. Example: "All Stripe webhook handlers must include idempotency_key validation (D1 Correctness auto-fail if missing)."}}
