# Council of Wise Elders (77): Quality Control

Score each section 0 to 10. The skill passes at 8.5 of 10 or better AND
the bundled script scripts/qc-council-of-wise-elders.sh exits 0 (the
wave gate reaches the same script through the root entry point
qc-council-of-wise-elders.sh). The QC
agent is never the agent that performed the install (no self-QC). Score
honestly: a section that was not checked scores 0, not full marks.

## 1. Discovery and registration (weight: gate)

- The installer glob discovery counts 77-council-of-wise-elders
  (discover_skills total rose by exactly one versus the pre-install
  count).
- lib-onboarding-state.sh OC_WAVE6_SKILLS contains
  77-council-of-wise-elders exactly once, and the wave-list integrity
  check passes.
- `openclaw skills info council-of-wise-elders` reports the skill as
  Ready or visible, resolving the registered name from SKILL.md.
- The skill-department-map.json skill 77 entry is present.

## 2. Package integrity

- Every file in the Section 4.2 layout inventory for this stage is
  present; generated manifest.json matches the installed tree hash
  (scripts/verify-bundles.mjs exits 0).
- SKILL.md frontmatter name is exactly council-of-wise-elders; the
  version file, skill-version.txt, and the frontmatter version agree.
- All JSON files in the folder parse (config, advisors, schemas,
  assets, runtime package files).
- No file in the folder is a placeholder that claims to work: parts
  owned by later units are marked not-yet-built in their own text.

## 3. Label and roster discipline

- config/advisors.json lists exactly the nine seats, in the fixed
  order, with the fixed seat IDs.
- Every seat's profile label is exactly: "AI perspective inspired by
  the published work of [name]. Not the individual and not an
  endorsement."
- The T. D. Jakes seat is ONE seat with three named lenses; nothing in
  the package counts it as three seats or three votes.
- No invented quotations, sources, or biography appear anywhere in the
  package. Source records distinguish bibliographic references from
  verified, ingested content.

## 4. Update-flow safety

- No state files exist inside the skill folder: no .sqlite or .db
  files, no sessions, briefs, verdicts, credentials, or client data.
- The authority mode is recorded outside the folder and matches the
  installation's intent.
- A re-run of the update sync leaves client state intact by
  construction, because none of it lives in the replaced tree.

## 5. Preservation

- 76-local-embedder is byte-untouched (in a source checkout:
  `git diff HEAD -- 76-local-embedder` is empty; on a box: its
  skill-version.txt and file inventory are unchanged).
- Global model defaults and the client's selected routes are unchanged.
  This skill prescribes no model anywhere.
- No gateway or Command Center restart was performed by the installing
  worker.

## 6. Honest behavior

- A council request missing a named prerequisite (no run grant, no
  client-selected route, no compatible Command Center release for
  managed mode) produces the typed not-ready report and spends zero
  provider requests. A simulated session, an invented verdict, or a
  fabricated advisor card is an automatic QC failure regardless of the
  numeric score.
- INSTALL.md was followed in its literal step order, and the release
  receipt records the Command Center compatibility state precisely
  (the negotiated state from the compatibility manifest), never as
  readier than the manifest supports.

## Scoring

- 9.5 to 10: every section verified with evidence.
- 8.5 to 9.4: pass, with named minor gaps recorded in the receipt.
- Below 8.5: fail. Loop on the specific failed items (maximum 5 loops),
  then escalate with the section scores and the blocker named.
