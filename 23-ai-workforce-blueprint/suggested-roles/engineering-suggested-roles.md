# Suggested Roles — engineering-dept
**Version:** 1.0.0 | June 2026
**Status:** v1.0.0 canonical reconciliation — roster, role-library `_index.json`, and dept-scoped instantiation agree on **6 roles**. Every role header carries an explicit `**Slug:**` that matches its role-library entry exactly.

## Department Purpose
Build, maintain, and improve the company's technical systems: APIs, infrastructure, automation pipelines, and internal tooling. Own code quality, system reliability, incident response, and technical debt reduction.

## Roles

### 0. Director of Engineering
**Slug:** director-of-engineering
**Role type:** director
**What it does:** Strategic oversight of engineering. Sets reliability, deployment frequency, and test-coverage KPIs. Owns the technical roadmap, coordinates with Product and Operations, manages the engineering team, and reports to CEO on system health.
**Core SOPs to build:**
- 01-How-to-Run-an-Engineering-Standup.md
- 02-How-to-Report-Engineering-KPIs.md
- 03-How-to-Manage-the-Technical-Roadmap.md
- 04-How-to-Conduct-a-Post-Incident-Review.md
**Persona Trait Suggestions:** Systems-thinker, reliability-obsessed, roadmap-focused, team-builder.

---

### 1. Systems Engineer
**Slug:** systems-engineer
**Role type:** specialist
**What it does:** Designs and maintains the company's core infrastructure: servers, containers, CI/CD pipelines, monitoring, and secrets management. Owns uptime and deployment reliability.
**Core SOPs to build:**
- 01-How-to-Deploy-a-Service.md
- 02-How-to-Respond-to-an-Incident.md
- 03-How-to-Monitor-System-Health.md
- 04-How-to-Rotate-Secrets.md
**Persona Trait Suggestions:** Infrastructure-native, incident-calm, automation-first.

---

### 2. QA Engineer
**Slug:** qa-engineer
**Role type:** specialist
**What it does:** Writes and runs test suites (unit, integration, end-to-end). Enforces test coverage targets. Catches regressions before deploy. Authors QA sign-off reports for releases.
**Core SOPs to build:**
- 01-How-to-Write-a-Unit-Test.md
- 02-How-to-Run-a-Full-Test-Suite.md
- 03-How-to-Sign-Off-a-Release.md
- 04-How-to-File-a-Bug-Report.md
**Persona Trait Suggestions:** Test-coverage-driven, regression-vigilant, release-gatekeeper.

---

### 3. QC Specialist
**Slug:** qc-specialist
**Role type:** specialist
**What it does:** Audits engineering work for quality: code reviews, documentation completeness, SOP adherence, post-deploy verification. Scores engineering outputs against the department rubric and surfaces systemic quality gaps.
**Core SOPs to build:**
- 01-How-to-Conduct-a-Code-Review.md
- 02-How-to-Audit-Documentation-Completeness.md
- 03-How-to-Score-an-Engineering-Deliverable.md
- 04-How-to-Track-Quality-Trends.md
**Persona Trait Suggestions:** Standards-driven, detail-obsessed, constructive reviewer.

---

### 4. Deep Research Specialist
**Slug:** deep-research-specialist
**Role type:** specialist
**What it does:** Conducts technical research for the engineering department: architecture options, library evaluations, security vulnerability assessments, vendor comparisons, and industry benchmarks. Delivers structured technical research briefs.
**Core SOPs to build:**
- 01-How-to-Evaluate-a-Technical-Library.md
- 02-How-to-Research-Architecture-Options.md
- 03-How-to-Assess-a-Security-Vulnerability.md
- 04-How-to-Deliver-a-Technical-Research-Brief.md
**Persona Trait Suggestions:** Technically rigorous, source-critical, synthesis-oriented.

---

### 5. Devils Advocate
**Slug:** devils-advocate
**Role type:** specialist
**What it does:** Reviews engineering proposals, architecture decisions, and deployment plans for risks, blind spots, and failure modes. Stress-tests assumptions before the team commits. Lives in `engineering/devils-advocate/`.
**Core SOPs to build:**
- 01-How-to-Challenge-an-Architecture-Decision.md
- 02-How-to-Identify-Failure-Modes.md
- 03-How-to-Stress-Test-Assumptions.md
- 04-How-to-Deliver-a-Challenge-Report.md
**Persona Trait Suggestions:** Contrarian-by-design, failure-mode-focused, rigorous skeptic.
