# Social Media Planner completion evidence v2

This checker repairs the false-green completion audit discovered in the September 9 review. It is **a verification tool, not deployment automation**. It never imports workflows, changes client services, posts content, edits old receipts, or creates model review claims. Old `state: VERIFIED` records are intentionally insufficient. A recovered legacy workflow is service restoration; it is not acceptance of the new version.

Run the repository-supported checker instead of the packet's old `run/audit-completion.py`:

```sh
python3 scripts/social-completion-audit.py \
  --run-root '/absolute/path/to/run/v2-final' \
  --repo ONB='/absolute/path/to/openclaw-onboarding' \
  --repo CC='/absolute/path/to/blackceo-command-center'
```

It prints complete JSON, exits 0 only on complete acceptance, and writes nothing by default. To preserve an output use `--output '/absolute/path/to/a-new-completion.json'`; an existing file is never overwritten. Authentication for read-only `gh api` and GitHub HTTPS access must already work. Git objects for original/repaired/batch/release revisions must exist in the designated clones; absent historical objects are blockers, not a reason to substitute HEAD. Fetch missing known refs through the normal repository procedure, then rerun. The verifier itself does not fetch or change refs.

## Migration: preserve evidence, do not convert PASS labels

1. Preserve the original run, including failed cutover/rollback receipts and final reviews. Create a separate `run/v2-final` directory. Copy original SPEC.md, COMPLETION.md, QC.md and scope provenance there as immutable evidence. Do not weaken the scope or overwrite history.
2. Establish `scope.v2.json` with all F01–F40 exactly once. F02 remains the accepted intentional anyone-with-link writer policy. Record each task's required repositories and all named QC cases from QC.md, plus positive, negative and recovery cases. Record required CI names and actual migration IDs before evaluating results. Capture the real scope review/authorization in an evidence file; arbitrary scope edits cannot waive original obligations.
3. For each task, reconstruct original review and every repair as distinct revisions. Obtain missing historical source objects and exact old logs from the original producer. Never overwrite a repaired candidate SHA while retaining an earlier diff hash. If provenance cannot be recovered, review and test the final actual content again and record the unresolved historical limitation honestly until the authorized acceptance policy resolves it.
4. Run current aggregate tests and required GitHub CI on final released content. Capture source-to-batch mappings and current release marker files. The checker independently reads remote main, annotated tag peeling, GitHub release state and required checks; it does not trust local tag labels.
5. Complete installation/deployment acceptance on designated authorized sandbox targets. The exact released builds must be installed, migrations applied, services registered, restarted and persistent state recovered on Mac, Hostinger Docker and Contabo Docker. Capture actual n8n definitions, IDs, active flags and successful execution receipts. Preserve raw API output as artifacts. No placeholder deployment, old-build restart, fixture-only run, inactive new workflow or successful rollback qualifies.
6. Complete all installed/sandbox client-path scenarios listed below, with actual logs/browser evidence, exact build bindings and no unresolved checks. Posting tests require the previously authorized test accounts/audiences; this script grants no posting authority.
7. Reconcile workers, both batch trains and all six wave reports. Stop/fence obsolete writers and preserve their outputs. No unfinished writer can mutate approved content after final acceptance.
8. Freeze `manifest.v2.json` after the last acceptance action. Both fresh final auditors must inspect this exact evidence set plus source/remote output. Obtain genuine Opus and Sonnet reviews in separate fresh contexts; never relabel Codex or another model as either. If unavailable, retain a named final-review blocker rather than fabricating a receipt.
9. Rerun the checker and report its actual `failing`, `unresolved_ids`, release identities and `complete` result. Any missing proof remains incomplete. A new deployment, repair or evidence change requires a new manifest and fresh final decisions. A later unrelated main commit is allowed if the intended release remains contained in main; a ref changing during the audit forces another verification run.

## Files and exact schema

All evidence references below are relative paths inside the selected run root. Escaping symlinks, empty files, unknown hashes and duplicate JSON keys fail. SHA fields are lowercase full 40-character Git SHAs; SHA-256 fields are lowercase 64-character digests. Times must be ISO 8601 with timezone. `unresolved` is required and must be `[]` for acceptance; a comment describing pending work is not a substitute for an explicit blocker.

`manifest.v2.json` contains:

```json
{
  "schema_version": 2,
  "program_id": "social-planner-september-eighth",
  "frozen_at": "2026-09-09T15:00:00Z",
  "files": {"index.v2.json": "<sha256-of-exact-file-bytes>", "...": "..."}
}
```

Include every referenced input/artifact, including specification, scope, task reviews, deployment proofs and logs. Exclude the manifest itself, final auditor files and generated completion reports to avoid circular hashes. The **final evidence identity is SHA-256 of the exact manifest bytes**, not reserialized JSON. The checker rehashes all listed files and checks the manifest/final reviews again before returning.

`index.v2.json` has `scope` (path), `tasks` (exact F01–F40 → receipt paths), `releases` and `trains` (exact ONB/CC → paths), `deployments` (exact n8n/mac/hostinger-docker/contabo-docker → paths), `workers` (path), `waves` (exact W0–W5 → paths), and `scenarios` (scenario names → check proof paths).

`scope.v2.json` has `task_ids`, `accepted_design_ids: ["F02"]`, `required_repos` (every task → nonempty subset of ONB/CC), `required_task_checks` (every task → full check-name list, including positive/negative/recovery), `required_ci` (ONB/CC → nonempty required CI names), `required_migrations` (nonempty actual migration IDs), and paths `spec`, `completion_contract`, `scope_approval`. Include QC.md in manifest evidence and preserve its complete task-level requirements. Scope review must verify this mapping; a manifest hash does not make an incomplete scope correct.

### Check proofs and model identities

Each check proof is a JSON object with:

- `result: "PASS"`, integer `exit_code: 0`, `unresolved: []`;
- actual `command`, `recorded_at`, `environment` (`unit`, `sandbox`, or `installed`);
- nonempty `artifacts` array of hash-listed captured log/screenshot/readback paths;
- task tests: `reviewed_revisions` mapping each applicable repo to the final tested candidate SHA;
- aggregate repository tests: `commit_sha` equal to released SHA;
- deployment checks: `target_id`, `source_releases` mapping both repos to released SHAs, and `environment: sandbox|installed`;
- end-to-end scenarios: `source_releases` and `environment: sandbox|installed`.

A model identity contains actual `actor_id`, `session_id`, `model_family` (`opus` or `sonnet`), and provider `model_id` containing that family. The IDs and transcript must describe the real producer; identity strings are not cryptographic attestation. For mixed-author revisions, a qualified reviewer must be a different actor/context from **every** author. Every author needs an opposite-family review of that revision.

### Task receipt and revision history

Each task receipt contains `task_id`, `decision: "PASS"`, `unresolved: []`, `kind` (`accepted_design` only F02; otherwise `implemented`), `required_repos`, `checks` (required check names → proof paths), nonempty `revisions`, and `final_revision_by_repo` (repo → final revision ID).

Each revision contains:

- `revision_id`, allowlisted `repo`, `base_sha`, `candidate_sha`, `batch_sha`, candidate `tree_sha`;
- nonempty literal repo-relative `paths` (no wildcard/magic pathspecs or traversal);
- `diff_sha256`, `recorded_at`, nonempty `authors` identity array and `reviews` path array;
- for a nonfinal revision, `superseded_by` points to a later revision in the same repo. Preserve the entire repair chain.

Compute the diff from exact stdout bytes of:

```sh
git diff --binary --full-index --no-ext-diff --no-textconv BASE CANDIDATE -- path1 path2
```

A revision review has `reviewer`, `decision: "PASS"`, `unresolved: []`, `recorded_at`, `transcript` path and `revision_sha256`. That digest is SHA-256 of the **complete revision JSON object** serialized with Python `json.dumps(revision, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()`. Review filenames appear in that object; review content is separate, so there is no circular hash. Any candidate/path/author/batch change invalidates the review.

The provider recomputes source diffs/trees, verifies batch ancestry in the released commit and compares final reviewed scoped paths against both batch and release. Squash/cherry-pick histories are permitted through explicit candidate-to-batch content mapping; changing the relevant released paths requires another actual review. F02 may legitimately have an empty diff while its preservation checks still run.

### Release and deployment records

A release record contains `repo`, exact allowlisted `repository`, `released_sha`, `tree_sha`, `version`, corresponding `tag: vVERSION`, boolean `prerelease`, `release_url`, `required_ci`, nonempty `aggregate_checks`, and `markers`. Each marker has `role`, repo `path`, exact file `sha256`, and nonempty `expected_token`. Required roles: version/readme/changelog/compatibility. Version/readme/changelog tokens must include this release version. Include all applicable package/skill/root markers, not merely one convenient marker per role. Compatibility contents are inspected in independent review.

A deployment has `profile`, `state: "NEW_VERSION_ACCEPTED"`, `unresolved: []`, boolean `rolled_back: false`, boolean `authorized_target: true`, `target_id`, `company_id`, `source_releases` for both repos, `recorded_at`, and `checks` (names → proof paths).

For each host, additionally require `installed_releases` exactly matching source releases, `migrations_applied`, booleans `service_registered`, `restart_passed`, `persistent_state_verified`, all true. Required checks: install, migrations, health, service-registered, restart, state-persisted. Actual logs must show the running new build and survival of draft/queue/lease state, not just generation of a plist or old-service health.

For n8n, require exactly create/append workflows. The role-to-source mapping is fixed: create → `35-social-media-planner/config/n8n/social-planner-sheet-create.json`; append → `35-social-media-planner/config/n8n/social-planner-row-append.json`. Each contains actual `workflow_id`, `active: true`, successful `execution_id` and `execution_result: "success"`, that `source_repo_path`, `source_file_sha256`, `normalization_proof`, `deployment_mapping`, `source_definition`, `deployed_definition`, and `expected_sha256`.

**The checker recomputes the intended runtime definition from actual released Git source bytes.** It parses the released JSON and projects exactly top-level `name`, `nodes`, `connections`, `settings`, preserving every node field, ID, name, parameter, Code body, type/version, connection, retry/error option and setting. It applies only the deployment mapping below to this released source. It separately parses/projects both the captured import payload (`source_definition`) and actual API readback (`deployed_definition`), then requires exact semantic equality to the recomputed expected definition. Root export/API metadata (e.g. contract, schema_version, createdAt, workflow ID/active) is outside this operational projection; operational fields cannot be deleted to hide mismatches. `expected_sha256` is SHA-256 of the expected projection serialized with the same canonical JSON function as revision hashes, not the capture's whitespace-sensitive file bytes. Manifest hashes still protect the complete raw captures.

The `deployment_mapping` file must contain exactly: `credential_references` (only `googleDriveOAuth2Api`/`googleSheetsOAuth2Api`, each with nonempty string id/name and no secret values), `webhook_prefix` (null or approved letters/digits/slash/underscore/hyphen prefix), `workflow_name` (null or approved deployed name), and `approval_evidence` (manifest-bound authorization/configuration capture). Credential assignment follows `prepare-import.py`: use a node's `parameters.nodeCredentialType` or Google Drive node type, require its approved reference, and assign that reference only. Prefix only webhook `parameters.path`. Replace only the top-level name when approved. No arbitrary node/settings/Code-body mapping is accepted. The prefix/name must describe the actual authorized target, and independent QC must verify credential reference ownership.

The normalization proof adds `source_releases`, `source_sha256` of the actual released repo file, `canonical_sha256` of the independently recomputed operational projection, and `mapping_sha256` of the complete canonical deployment mapping object. Retain raw API exports and the exact prepare-import command/version. The proof's claims are cross-checks, never substitutes for deriving the expected definition from released source. Matching two old captures plus a current source hash must fail.

The superseded legacy n8n weekly workflow must **not** be reactivated. Record `weekly_scheduler` with `kind: "command-center-cycle-service"`, actual `legacy_n8n_workflow_id`, `legacy_n8n_active: false`, `single_owner: true`, and a `proof` path. That sandbox/installed proof must bind both source releases and capture legacy scheduler inactivity, the one canonical weekly owner and an actual succeeding next-week/no-response scheduling cycle. The host/end-to-end checks remain required; this does not waive weekly behavior.
The n8n deployment also needs `template_id`, `template_readback` artifact and these checks: fresh-import, create, append, duplicate-provision, two-company-isolation, retry-restart, missing-credentials, template-access-failure, interrupted-formatting, sheet-visual, permission-anyone-writer. Negative cases pass when the expected safe failure/structured error was actually observed, not when the request accidentally succeeded.

### Closure and final review records

Workers: integer `active_worker_count: 0`, `unfinished_worker_ids: []`, nonempty `max_observed_agents_by_workflow` (integer counts 0–10), integer `max_active_workflows` 1–50, and `reconciliation_log`. These are observed high-water counts, not configured maxima.

Each train: `repo`, `state: "RELEASE_VERIFIED"`, nonempty `candidates`. Each candidate has unique `candidate_id`, nonempty `task_ids`, `released_sha`, `merge_proof`, and `state: "MERGED"`. SUPERSEDED/REJECTED additionally needs `replacement_id` naming a MERGED candidate covering those tasks. Pending/blocked/empty initial queues do not close a program. The task revisions provide the actual reviewed-to-batch content mapping.

Each wave: `wave` W0–W5, `state: "REPORTED"`, actual `report_id`, `next_dispatch_id` for W0–W4, and `proof` with observed progression output. A report pointer without evidence does not prove launch or completion.

Required scenarios (all sandbox/installed): first-client-setup; theme-company-isolation; theme-cycle-isolation; theme-stop-resume; theme-expiry-renewal; canonical-assignment-worker-start; content-production; independent-content-visual-qc; sheet-images-video-links; sheet-client-edits; sheet-desktop-mobile-visual; ghl-account-discovery; healthy-platform-continuation; publication-readback; truthful-board-client-updates; following-week-no-response; restart-recovery; provider-model-choice; optional-output-isolation; prompt-9000-19000; ultra-concurrency; shared-store-lock-recovery; wave-progression-idempotency. Include any additional original QC cases too. A scheduled post is not published until actual provider readback.

Final reviews live at `audit/final-opus.v2.json` and `audit/final-sonnet.v2.json`, outside the manifest. Each contains fresh `reviewer` identity, `decision: "PASS"`, `unresolved: []`, exact `manifest_sha256`, `recorded_at` after freeze, `transcript` path, and exact `transcript_sha256`. Both contexts must differ from each other and previous task authors/QC. They must approve the same final evidence set. Pending deployment/repair cannot be explained away in notes under overall PASS.

## Verification and limits

```sh
python3 -m unittest discover -s tests/social-planner -p test_completion_audit_v2.py -v
```

The suite contains a deliberately synthetic complete fixture, corruption cases and a real temporary Git-history test. It rejects false-green nested proofs, unknown repositories, forged diff/SHA, omitted F02, wrong/lightweight tags, missing releases, skipped required CI, stale reviews, old installed builds, rollback, inactive workflows, identical old captures with forged normalization, invalid released workflow JSON, wrong role/source bindings, changed retry options, duplicate weekly schedulers, missing browser evidence, pending workers/queues and path escape. The injected provider is a Python testing seam; the CLI has no offline-pass or mock-provider switch.

Hashes establish byte identity and prevent unnoticed stale evidence; they cannot establish that a fabricated log is true, that a scope author captured every obligation, or that a typed model name is genuine. Independent reviewers must inspect captured raw output and provenance. Deployment receipts are historical acceptance, not continuous live monitoring: the checker independently re-reads GitHub state but does not SSH into client hosts or query n8n live. Capture fresh authorized deployment readbacks when certifying current live status. Do not label a fixture pass or read-only source review as full live acceptance.
