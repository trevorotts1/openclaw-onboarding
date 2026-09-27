# Core Updates — Base Installation

<!-- CORE_REFERENCE_POLICY_V1 -->
These instructions define storage for base onboarding. Current explicit owner instructions take precedence. Installation does not authorize replacing owner facts or changing identity, permissions or model routing.

## Storage contract

- Keep complete skill procedures in the canonical master folder or installed skill references. Bootstrap contains essential rules and short task-triggered pointers only.
- Use a stable, version-free pointer ID. Replace that owned pointer in place; never append another copy because a version changed. Preserve other skills' blocks and all owner content.
- Use one appropriate core file per pointer. Additional core changes need a distinct durable fact or essential rule; an installation or learning receipt is not such a fact.
- Whole-file budgets: AGENTS.md 15,000 characters; MEMORY.md 8,000; TOOLS.md 15,000. Count characters, not lines. An individual skill gets no separate allowance.
- Validate references, block boundaries and the whole-file budget before applying. Compare the expected hash and write atomically. Coordinate large reductions with the core watcher's approved baseline. Repeating the same update must produce no byte changes or extra backups.

## AGENTS.md

If an onboarding/update trigger pointer already exists, reuse it. Otherwise, add one concise pointer to the verified master-folder installation/update reference, using its exact local path. Keep pending activation state outside bootstrap. Read that reference only for onboarding, update or maintenance tasks.

## MEMORY.md

No default update. Do not add an installed-on date, skill inventory, version stamp, learned-this receipt, pending flag or diagnostic history. Record a separately verified durable owner decision only when it is not already represented.

## Installation and pending state

Use the existing onboarding state, `.onboarding-version`, update log and `.pending-setup.md` in the managed OpenClaw tree. Verify their actual configured paths rather than creating another master folder. Downloaded, staged, wired and QC-passed are distinct states; report only the state actually verified.

Check pending setup only when relevant to the current task. Existing credential conventions and owner permissions govern any action. Do not copy credentials into core files or automatically send notifications from this storage procedure.

Read the local scheduler for the actual update schedule; do not insert a guessed Sunday time into bootstrap. Compact-policy legacy updater candidates remain pending until their writers have been reconciled and reviewed. An approved candidate hash is not evidence that its installation gates passed.

On this machine the review index is `/Users/blackceomacmini/Downloads/openclaw-master-files/References 4 Bootstrap/updates-index.md`; detailed policy is `/Users/blackceomacmini/Downloads/openclaw-master-files/References 4 Bootstrap/memory-policy.md`. Resolve the canonical master folder when provisioning another machine; never copy this machine's absolute path blindly.
