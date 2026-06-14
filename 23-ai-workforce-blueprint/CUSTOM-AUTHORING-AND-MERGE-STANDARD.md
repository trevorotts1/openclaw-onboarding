# Custom Role + SOP Authoring and Core-Merge Standard

Status: BINDING standard for Skill 23 (AI Workforce Blueprint).
Scope: defines the repeatable way the system authors custom roles and custom
SOPs that the 233-template core/floor library does not already cover, and the
way custom content MERGES into an overlapping core department instead of
shipping a duplicate department.

This is a STANDARD DOCUMENT. It does not change `build-workforce.py` logic. It
specifies the contract that the build scripts, the interview, and the closeout
gate must satisfy. Where it names a function or file, that name is the real one
in this repo as of skill-version 12.4.0.

## Why this exists

The core library at `23-ai-workforce-blueprint/templates/role-library/` is the
233-template source of truth. Canonical and floor departments resolve their
roles and SOPs by COPY + token-personalize from that library; they are never
authored by an LLM. This is enforced by `scripts/sop_boundary_gate.py`
(`refuse_if_canonical`, `assert_no_canonical_in_authoring_path`) and by
`_instantiate_role_from_library()` in `build-workforce.py`.

What the system has NOT had is a written, executable standard for the work that
falls OUTSIDE the library:

1. How custom roles and custom SOPs get authored to the same quality bar the
   core library was authored to (the 11-dimension rubric, the 19-section role
   file, the six-field SOP skeleton).
2. How a custom department or a custom role/SOP that semantically OVERLAPS a
   core department gets LAYERED INTO that one core department instead of being
   shipped as a second, duplicate department.

The grounded diagnosis at
`Downloads/ZHC-INTERVIEW-CLOSEOUT-FIX/diag/02-departments.md` records both gaps
(capability 2 partial: detect/de-dup exists, true combine/merge missing;
capabilities 3 and 4 missing as a build decision). This standard closes them at
the specification level so the build and the closeout gate have a single rule to
satisfy.

The mission this serves: BlackCEO builds Zero Human Companies that break the
owner's addiction to labor as the revenue mechanism. A custom role or SOP only
earns its place if it does real work the owner actually needs and the core
library does not already provide. Custom content that merely duplicates the
library wastes tokens and clutters the org chart, which is the opposite of the
mission. Every rule below exists to keep custom content scarce, grounded, and
non-duplicative.

---

## 1. TRIGGER - when custom authoring fires (and when it must not)

Custom authoring fires ONLY for a need that the 233-template core/floor library
does NOT cover. There are exactly two trigger shapes:

- TRIGGER A - Custom department. The owner needs a whole department that has no
  canonical entry in `department-naming-map.json` and no role-library directory
  under `templates/role-library/`. Examples from the field: Government
  Contracting, Tax (when not folded into Billing and Finance). These are the
  `clientCustoms` / `CUSTOM_KEEPS` set already computed by
  `reconcile_canonical_floor()` and Phase 5.5 Step 1.

- TRIGGER B - Custom role or custom SOP inside ANY department, including a core
  one. The owner needs a specialist or a procedure that the core department's
  library roster does not include. Example: an owner whose Sales department needs
  a "Government RFP Bid Writer" role, or whose Customer Support department needs
  a specific refund-escalation procedure unique to their contracts. The host
  department can be canonical; only the ADDED role/SOP is custom.

### The hard boundary (never author canonical work)

Canonical and floor content stays COPY + token-personalize. It is NEVER
LLM-authored. This is the token-economics gate and it is enforced in code:

- `sop_boundary_gate.is_canonical_dept(dept_id)` is the single source of truth
  for canonicity (computed from the role-library directory tree, not a hardcoded
  list). A dept is canonical if its alias-normalized id is in
  `CANONICAL_LIBRARY_DEPT_IDS`.
- `sop_boundary_gate.refuse_if_canonical()` raises `CanonicalDeptAuthError` at
  the start of any authoring path for a canonical dept.
- `populate-sops-from-manifest.py` filters canonical depts out of the authoring
  manifest (per-loop guard included) and refuses to author them; it exits 0 when
  the manifest contained only canonical depts because the copy path already did
  the work.
- `write_sop_research_manifest()` in `build-workforce.py` skips any canonical
  dept whose roles failed to instantiate from the library, logging a loud
  `[SOP-BOUNDARY-GATE] REFUSE` line, and records `boundary_gate.canonical_refused`
  / `boundary_gate.custom_queued` in the manifest.

Rule statement: custom authoring is permitted for the custom ADDITION only - a
custom department, or the specific custom role/SOP an owner needs inside any
department. The canonical roles and canonical SOPs of a core department are
always copied from the library, even when that core department is also receiving
custom additions (see section 5, Core-Merge). A canonical role/SOP must never be
regenerated by an LLM.

---

## 2. DETERMINE - capturing what custom roles and SOPs are needed, per department

Custom authoring cannot fire until the build knows precisely what is custom.
That determination happens during the interview and is recorded in build-state
so the post-interview build is deterministic and resumable.

### What to ask (interview)

The department arcs in INSTRUCTIONS.md Phase 4 (D-1..D-13) and Phase 5.5 already
surface the department set. This standard adds a per-department capture pass for
custom roles and custom SOPs. For every department in the final set (canonical,
floor, vertical, OR custom), the interview asks two grounded questions:

- Custom role question: "Inside [Department], is there a specific specialist or
  job the core team does not already cover that you want? If you are not sure,
  I will show you the roles this department already includes so you only add what
  is genuinely missing." (Show the library roster from
  `templates/role-library/<dept>/` or `suggested-roles/<dept>-suggested-roles.md`
  first, so the owner adds only true gaps - keeping custom content scarce.)

- Custom SOP question: "Is there a procedure YOU run a specific way in
  [Department] that an outsider would get wrong? Walk me through it." A captured
  owner-specific procedure becomes a custom SOP authored to section 4 of this
  standard; it does NOT replace the core-copied SOPs, it is added alongside them.

Defaults and discipline: most departments will capture zero custom roles and zero
custom SOPs - that is the correct and expected outcome, because the core library
already covers the standard work. The capture pass exists to catch the genuine
gap, not to manufacture additions. When the owner says "whatever you think is
best," the answer is zero custom additions for that department, not invented
ones.

### What to record (build-state)

Record the determination in `[ZHC]/[slug]/.workforce-build-state.json` alongside
the existing `canonicalReconciliation` block. Per department:

```json
"customAuthoring": {
  "version": "1.0",
  "capturedAt": "<ISO timestamp>",
  "departments": {
    "sales": {
      "isCustomDept": false,
      "hostDeptCanonical": true,
      "customRoles": [
        {
          "name": "Government RFP Bid Writer",
          "reason": "<owner's words: why this is needed and not covered>",
          "status": "captured"
        }
      ],
      "customSops": [
        {
          "title": "Federal Bid Compliance Pre-Flight",
          "hostRole": "government-rfp-bid-writer",
          "reason": "<owner-specific procedure captured verbatim>",
          "status": "captured"
        }
      ]
    },
    "gov-contracting": {
      "isCustomDept": true,
      "hostDeptCanonical": false,
      "customRoles": [ ... ],
      "customSops": [ ... ]
    }
  }
}
```

`status` transitions: `captured` (interview recorded it) -> `authored` (written
to this standard and passed QC) -> `merged` (only for items that landed in a
core department via section 5). The closeout gate (section 6) blocks until every
`captured` item reaches `authored` or `merged`.

The existing `canonicalReconciliation.customKeeps` (custom departments) and the
authoring manifest's `boundary_gate.custom_queued` remain the authority for which
DEPARTMENTS are custom. `customAuthoring` is the finer-grained record of which
ROLES and SOPS are custom within any department, including core ones.

---

## 3. CUSTOM ROLE AUTHORING STANDARD

A custom role file is authored to the SAME 19-section structure the core library
uses. There is one role file format in this system; custom roles do not get a
lesser one.

### Exact structure - the 19 sections (in order)

1. Role Identity
2. Persona Governance Override
3. Daily Operations
4. Weekly Operations
5. Monthly Operations
6. Quarterly Operations
7. KPIs (Your Scoreboard)
8. Tools You Use
9. Standard Operating Procedures (Numbered) - each SOP authored per section 4
10. Quality Gates
11. Handoffs (Value Stream Map)
12. Escalation Paths
13. Good Output Examples
14. Bad Output Examples (Anti-Patterns)
15. Common Mistakes (Pre-Empted)
16. Research Sources (Where to Look for Best Practice)
17. Edge Cases for This Role
18. Update Triggers (When to Revise This Document)
19. When to Spawn a Sub-Specialist (use the verbatim template at
    `templates/role-library/_section-19-template.md`; >= 3 named
    sub-specialists, each with name + when-trigger + example task + duration)

Headers MUST match the `^## \d+\.` form. Section 2 MUST contain the appropriate
persona-deferral clause verbatim (Standard variant for a worker role; the CEO
variant only for the Master Orchestrator). These are the same constraints
`templates/role-library/_rubric.md` enforces on core roles.

### Grounding (no fabrication)

Every custom role is grounded in three sources, in this priority:

1. Owner business context captured in the interview (company, industry, the
   owner's own words for why this role exists). Use real captured values, never
   bracket placeholders, never literal "BlackCEO" / "Trevor" / "ZeroHumanCompany"
   (those appear only as `{{TOKENS}}`).
2. The BlackCEO mission: this company exists to break the owner's addiction to
   labor as the revenue mechanism. A custom role must do real revenue-relevant
   or operations-relevant work an AI agent can actually perform - not a vanity
   title. Section 7 KPIs must link to the revenue cascade tokens where
   applicable.
3. The department's purpose: the custom role must fit the host department's
   value stream and hand off cleanly to its existing roles (section 11).

Research citations in section 16 follow the same Tier-1 expectation as the
library: real URLs with retrieval dates, no invented sources.

### Naming by purpose

Name a custom role by the WORK it does, not by a generic seniority label. "Federal
RFP Bid Writer" not "Sales Specialist 2." The slug is the lowercased,
hyphenated name (the same slugging `create_role_workspace()` applies). The name
must read as a job an outsider could understand.

### QC gate for a custom role

A custom role does not reach `authored` status until it passes the role QC bar,
which is the 11-dimension rubric in `templates/role-library/_rubric.md`
(PASS = total >= 85 AND no dimension < 6.5). In addition, these custom-specific
checks are hard fails:

- No fabrication. Every factual claim is grounded in captured owner context or a
  cited Tier-1 source. No invented client facts.
- No em dashes anywhere in the file. Use commas, parentheses, or sentence breaks.
- Distinct from any core role. The custom role must NOT duplicate a role that
  already exists in the host department's library roster. If it overlaps a core
  role, it is not a new role - it is either a core role (copy it) or a true
  specialization that section 5 may fold in. Run the overlap check in section 5.
- KPIs present (section 7) with numeric targets and revenue-cascade linkage
  where applicable.
- Handoffs present (section 11): named upstream and downstream roles, not "the
  team."
- All 19 sections present and ordered; section 19 has >= 3 named sub-specialists.

---

## 4. CUSTOM SOP AUTHORING STANDARD

A custom SOP is authored to the SAME six-field skeleton the core library's
Section 9 SOPs use. This is the canonical SOP shape in
`templates/role-library/<dept>/<role>.md` and it is the shape the QC rubric
(Dimension 4: SOP Atomicity) scores.

### Exact SOP skeleton (six fields)

```markdown
### SOP <n.m> - <Title named by the task it performs>

**When to run:** <the trigger / condition that starts this SOP>
**Frequency:** <Daily / Weekly / Monthly / On-demand / etc.>
**Inputs:** <data, files, credentials, prior outputs the SOP consumes>
**Steps:**
1. <atomic, executable step - references a specific tool by name>
2. <atomic, executable step>
   ...
**Outputs:** <the artifact this SOP produces>
**Hand to:** <named downstream role(s) who receive the output>
**Failure mode:** <the specific way this goes wrong + how to prevent it>
```

Field mapping for clarity (the task's required shape -> this skeleton):
When = "When to run"; Inputs = "Inputs"; Steps = "Steps"; Outputs = "Outputs";
Hand-to = "Hand to"; Failure-mode = "Failure mode". "Frequency" is carried in
addition because the library SOPs carry it.

The escalation + research rule from `LEAN_SIX_SIGMA_SOP_PROMPT` applies to every
SOP: if an edge case is hit, do not guess - be absolutely sure (proceed) or not
sure (research via the heavy-tier model / Perplexity, or escalate to the
department head), and log the edge case + outcome to the department's memory.

### Grounding

A custom SOP is grounded in the OWNER'S captured procedure first. When the owner
described how they run a task (the section 2 custom-SOP capture), that answer is
the spine of the SOP. Industry research enriches and validates it; it never
replaces the owner's real procedure with a generic one. Where a step is derived
from research, cite it inline (e.g. "Per industry benchmark (Perplexity
<date>): ...").

### Owner-specific SOP vs core-copied SOP

- The core-copied SOPs (from the library, for a canonical role) stay exactly as
  copied + token-personalized. They are not edited to match the owner's quirk.
- The owner's specific procedure becomes a SEPARATE custom SOP added to the host
  role's Section 9, numbered after the copied SOPs. The result is: the role has
  its standard library SOPs PLUS the owner's custom SOP. Nothing is overwritten.

### Quality bar and QC gate for a custom SOP

A custom SOP does not reach `authored` until:

- All six fields present and non-empty.
- Steps are atomic and executable (an AI agent can actually do each step) and
  reference a specific named tool. Hard fail (Dimension 4 auto-fail) if any step
  says "use your judgment" / "as appropriate" / "based on context."
- Done criteria are measurable, not vague.
- "Hand to" names a real downstream role.
- "Failure mode" is a specific, pre-empted failure with prevention, not a
  platitude.
- No fabrication, no em dashes.
- For an owner-specific SOP: the owner's captured procedure is recognizably
  preserved (not silently replaced by a generic version).

---

## 5. CORE-MERGE - layer custom into one core department, never duplicate

This is the combine path the diagnosis flagged as missing
(`diag/02-departments.md`, capability 2). Detection and de-dup of variant-slugged
canonical depts already exists (`_canonical_present()`,
`CANONICAL_VARIANT_SLUGS`, `apply_vertical_packs` skip-on-overlap). What this
standard adds is the rule for SEMANTIC overlap that those slug maps do not catch
(e.g. "Accounting" / "Tax" vs canonical Billing and Finance), and the rule for a
custom ROLE/SOP whose work belongs inside a core department.

### The semantic-overlap decision

When the build (or the interviewing agent, per Phase 5.5 Step 1's semantic match)
finds that a custom department OR a custom role/SOP semantically overlaps a core
department, decide as follows:

- OVERLAP = the custom department's purpose is substantially the same value-stream
  function as a core department (its work would be done by the core department's
  roles), even though its name is neither the canonical id, a `CANONICAL_ID_ALIASES`
  legacy key, nor a `CANONICAL_VARIANT_SLUGS` variant. Decide overlap by purpose
  and value-stream function, matching against the canonical dept's `display_name`,
  `folder`, `one_liner`, and the work its library roles perform - the same
  semantic basis Phase 5.5 Step 1 already uses for COVERED.

- NO OVERLAP = the custom department is a genuinely distinct function with no
  canonical equivalent (e.g. Government Contracting for a firm whose entire model
  is federal bids). It stays a standalone custom department and gets its roles/SOPs
  authored per sections 3 and 4.

The bias rule from Phase 5.5 ("when in doubt, keep the canonical dept") is for
ADDING a missing canonical dept. For MERGE the complementary bias applies: when a
custom department clearly overlaps a core one, MERGE rather than ship two
departments that do the same job. If genuinely uncertain whether it overlaps,
surface it to the owner in the interview ("Your 'Accounting' work - is that the
same as the core Billing and Finance department, or something separate?") and
record their answer; do not auto-decide a merge the owner did not confirm.

### The merge result

When overlap is confirmed, LAYER the custom content INTO the one core department:

1. Keep the core department as the single department of record (canonical id,
   canonical library roles, canonical copied SOPs all intact).
2. ADD the custom department's distinct roles into that core department as custom
   roles (authored per section 3). Drop any custom role that merely duplicates a
   core role already present (per the section 3 distinctness check).
3. ADD the custom department's distinct SOPs as custom SOPs on the appropriate
   role (authored per section 4), numbered after the copied SOPs.
4. Do NOT create a second department folder. Do NOT regenerate the core
   department's canonical roles/SOPs - they remain copy-from-library.

For a custom ROLE/SOP captured against a core host department (Trigger B), there
is no second department to collapse; the role/SOP is simply authored into that
core department, which is itself the merge.

### Build-state record of a merge

Record every merge so a later audit can prove no duplicate shipped:

```json
"coreMerges": [
  {
    "customSource": "accounting",
    "mergedIntoCanonical": "billing-finance",
    "basis": "semantic-overlap: same finance value-stream function",
    "decidedBy": "owner-confirmed",
    "rolesAdded": ["tax-compliance-specialist"],
    "rolesDroppedAsDuplicate": ["bookkeeper"],
    "sopsAdded": ["billing-finance/tax-compliance-specialist: Federal Tax Filing Pre-Flight"],
    "mergedAt": "<ISO timestamp>"
  }
]
```

The affected `customAuthoring` items flip to `status: "merged"`. The custom
department id MUST NOT appear in the final department set or org chart as a
separate department once merged.

---

## 6. QC / ACCEPTANCE GATE - blocks closeout until authored and merged

Closeout is BLOCKED until both invariants below hold. This gate sits with the
existing library gate (the `roleLibraryStatus` / `sopLibraryStatus` build gates
that already block `buildCompletedAt` and `closeoutStatus=pending` per
`build-state-schema.json`). The master orchestrator must not write
`buildCompletedAt` or set `closeoutStatus=pending` until this gate passes, the
same way it must wait for `roleLibraryStatus == done` and `sopLibraryStatus == done`.

Invariant A - every captured custom item is authored to standard:

- Every `customAuthoring.*.customRoles[]` entry is `status: authored` (or
  `merged`) and its role file passes the section 3 QC gate (19 sections, rubric
  PASS, no fabrication, no em dashes, distinct from core, KPIs + handoffs
  present).
- Every `customAuthoring.*.customSops[]` entry is `status: authored` (or
  `merged`) and its SOP passes the section 4 QC gate (six fields, atomic
  executable steps, measurable done criteria, named hand-to, real failure mode,
  no fabrication, no em dashes).
- No captured item remains in `status: captured`. A `captured` item at closeout
  is the same failure class as an empty SOP stub: it means the work was promised
  but not authored.

Invariant B - every overlap is merged, not duplicated:

- No custom department that was decided OVERLAP ships as a separate department.
- Every merge is recorded in `coreMerges[]` with its basis and decision source.
- The final department set contains the core department once, carrying its
  canonical (copied) roles/SOPs plus the merged custom additions.

Failure handling: if either invariant fails, the gate keeps the build out of
closeout (the same pending/resume posture the library gate uses) and reports the
specific failing item so the resume cron can re-fire authoring or the agent can
complete the merge. A "done" flag is not closeout; verified authored + merged
content is.

---

## How this connects to the existing pipeline (reference, not a logic change)

- Canonicity / refuse-authoring: `scripts/sop_boundary_gate.py`.
- Library copy + token-personalize (the canonical path): `_instantiate_role_from_library()`
  in `scripts/build-workforce.py`.
- Floor reconciliation + custom-keep computation: `reconcile_canonical_floor()`,
  `_canonical_present()` in `scripts/build-workforce.py`.
- Variant de-dup + vertical-pack overlap skip: `CANONICAL_VARIANT_SLUGS`,
  `apply_vertical_packs()` in `scripts/build-workforce.py`.
- Custom authoring path: `scripts/populate-sops-from-manifest.py` consuming the
  manifest from `write_sop_research_manifest()`.
- Role file structure + rubric + section 19: `templates/role-library/_rubric.md`,
  `templates/role-library/_section-19-template.md`.
- Interview phases for capture: `INSTRUCTIONS.md` Phase 4 / Phase 5 / Phase 5.5.
- Build-state gates: `build-state-schema.json` (`roleLibraryStatus`,
  `sopLibraryStatus`, `closeoutStatus`).

This document is the standard those pieces must satisfy. The implementation of
the capture pass, the merge executor, and the gate checks belongs in the build
scripts and is intentionally NOT written here, to avoid colliding with in-flight
edits to `build-workforce.py` and `INSTRUCTIONS.md`.
