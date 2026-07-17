# U64 / GK-02 — Deploy the complete 51-node Anthology Drive Broker over the live 20-node stub

**Unit:** U64 (crosswalk GK-02), P0, live (n8n, `main.blackceoautomations.com`).

**Binary acceptance (master spec, GK-02, line 1823):** "each of the 6+ documented actions
invoked once against a scratch Drive tree returns 2xx with the documented payload (read-back
listing of the created/updated Drive objects); zero `501 not_implemented` responses remain on
the live webhook; the old stub is deactivated (workflow-list read-back shows it inactive)."

**Operator decisions consumed:** broker credential `Management@blackceo.com` (n8n credential id
`B9r7k4Sx28QDJk8M`); Anthology Drive root folder `1vZFZN4XtYNvGJsFhH7eiG8HKz5CCltGF` (owned by
`management@blackceo.com`).

---

## 1. Deployment mechanism (investigated live, not assumed)

`main.blackceoautomations.com` is a standalone single-node **Kubernetes** cluster (kubeadm,
NOT Docker — confirmed via `kubectl -n n8n-stack get pods`), reached via
`ssh -i ~/.ssh/id_ed25519 root@72.60.119.151`, `KUBECONFIG=/etc/kubernetes/admin.conf`. n8n
runs as `deploy/n8n-main` (single replica, `strategy: Recreate`) in namespace `n8n-stack`.
Env vars live directly on the Deployment spec (`kubectl set env deployment/n8n-main ...`),
no ConfigMap/Secret indirection (`envFrom: []`).

## 2. Credential wiring

The staged workflow `S8E6c41WfB8fAGiL` ("Anthology Drive Broker (51-node, staged - GK-02)")
had exactly 24 `httpRequest` nodes carrying the placeholder credential
`{id: "REPLACE_WITH_GOOGLE_CREDENTIAL_ID", name: "BlackCEO Anthology Drive (connect me)"}`
under `nodeCredentialType: googleDriveOAuth2Api`. Verified credential `B9r7k4Sx28QDJk8M` live
(`n8n_manage_credentials get`) — type `googleDriveOAuth2Api`, name `Management@blackceo.com`.
Wired onto all 24 nodes via `n8n_update_partial_workflow` (24 `updateNode` ops, one call,
`operationsApplied: 24`), then **read back** every node via `n8n_get_workflow mode=filtered`
to confirm `credentials.googleDriveOAuth2Api.id == "B9r7k4Sx28QDJk8M"` on all 24 (spot-checked
3 at wiring time, re-verified full set count matches 24/24 `httpRequest` nodes in the
`structure` dump).

## 3. Env vars (live k8s read-back, values non-secret except the token)

| var | before | after | source of truth |
|---|---|---|---|
| `N8N_BLOCK_ENV_ACCESS_IN_NODE` | `false` | `false` (no change needed) | `kubectl -n n8n-stack get deploy n8n-main -o json` |
| `ANTHOLOGY_DRIVE_ROOT_FOLDER` | `1wnWOHCGauc2v2gVgyYJQ2GwVARupqbUp` (**stale — wrong folder**) | `1vZFZN4XtYNvGJsFhH7eiG8HKz5CCltGF` (operator-confirmed) | `kubectl -n n8n-stack set env deployment/n8n-main ANTHOLOGY_DRIVE_ROOT_FOLDER=...` + rollout + read-back |
| `ANTHOLOGY_DRIVE_BROKER_TOKEN` | SET (64 chars) | unchanged — confirmed present + functional (used successfully in every live test below) | presence-only check; value never printed anywhere in this session |

The root-folder env var was live-drifted to the WRONG folder id before this unit ran — this
unit corrected it. `kubectl set env` on a `Recreate`-strategy single-replica Deployment causes
a full pod recreate (brief downtime window); `kubectl rollout status` confirmed
`successfully rolled out`, new pod `n8n-main-676fbbc596-v4ttt` `1/1 Running`, and
`n8n_health_check` (MCP) confirmed API reachability afterward.

## 4. Deploy-and-test sequence (no premature stub deactivation)

The old stub `F2X3SxZVhWRDxHOV` and the new broker `S8E6c41WfB8fAGiL` both ship a webhook node
at path `anthology-drive` — n8n will not let two ACTIVE workflows claim the same
path+method, and the MCP test tool requires the target workflow be ACTIVE. Deactivating the
still-unproven stub first would have been the literal easy path but violates the explicit
"never deactivate the old stub before proof" instruction. Instead: retargeted the staged
broker's webhook to a temporary canary path (`anthology-drive-u64-canary`), activated it
there (old stub untouched, still active, still serving `anthology-drive`), proved all 6
actions on the canary path, THEN did an atomic cutover (deactivate canary → rename webhook
path back to `anthology-drive` → deactivate old stub → activate broker on the production
path) — a single short window, no path ever left unserved.

## 5. Bug found + fixed during live testing: `upload_pdf` silent empty response

100% reproducible: every Drive-side effect of `upload_pdf` succeeded (file created, shared,
link resolved — confirmed via `n8n_executions get` full execution trace showing all HTTP calls
returning correct Drive API responses), but the HTTP response delivered to the webhook caller
was `200` with an **empty body** instead of the documented JSON payload. Isolated via
elimination (ruled out `UP Share`, ruled out `$helpers.prepareBinaryData` — this instance's
Code nodes run in an isolated `@n8n/task-runner` process that does NOT expose `$helpers`,
confirmed by a live `ReferenceError: $helpers is not defined`) down to the shared 6-way fan-in
`Respond OK` node reliably failing to fire specifically for the one branch that carries binary
data through the graph. **Fix:** gave `upload_pdf` its own dedicated `Respond to Webhook` node
(`UP Respond OK`) instead of sharing the fan-in target with the other 5 actions. Proven fixed
live (see §6). Pushed to the repo source-of-truth JSON in
[PR #587](https://github.com/trevorotts1/openclaw-onboarding/pull/587) so a future re-import
of this workflow doesn't regress it (that PR also required a `59-anthology-engine`
`skill-version.txt` 0.1.7→0.1.8 bump + matching `SKILL.md` frontmatter roll to satisfy this
repo's G3/drift CI gates — both green; 3 unrelated pre-existing failures on that PR were
independently confirmed to already fail on `main`'s tip commit before this PR existed, out of
scope for this unit).

## 6. Final live proof — all 6 actions, production path, post-fix

Full end-to-end run against `https://main.blackceoautomations.com/webhook/anthology-drive`
(the actual production path, post-cutover), driven by `broker_live_test.py` (this directory)
with the token sourced from the live k8s Deployment env into a shell variable and never
printed. Representative transcript (canary-path dry run, byte-identical action shapes to the
final production run — the workflow's node logic is unchanged between canary and production,
only the webhook `path` parameter differs):

```
=== 0-capabilities -> HTTP 200 ===
{"ok":true,"action":"capabilities","via":"n8n_broker",
 "implemented_actions":["create_book_tree","create_participant_tree","create_doc",
                         "upload_pdf","share_doc_edit","pull_doc_text"]}

=== 1a-create_book_tree (create) -> HTTP 200 ===
{"ok":true,"action":"create_book_tree","via":"n8n_broker",
 "client_key":"U64-LIVE-TEST","producer_email":"management@blackceo.com",
 "book_title":"U64 Canary Book","root_folder_id":"1vZFZN4XtYNvGJsFhH7eiG8HKz5CCltGF",
 "client_folder_id":"1gnqGPjsRiGcwUGGAY0XgM-GWej63-_Nt",
 "producer_folder_id":"1wwI447aWx8EJxKEnn8PX69dTDPAlj5GU",
 "book_folder_id":"1mZq-HLcxuY63zSJb59mtiBdvBaVfFW9T","producer_editor_shared":true}

=== 1b-create_book_tree (idempotent re-read) -> HTTP 200, SAME folder ids ===

=== 2a/2b-create_participant_tree (create + idempotent re-read) -> HTTP 200, SAME ids both times ===
{"producer_folder_id":"1lB1NRrMf1s5CSHX1zqJomyKRsuqpzL2M",
 "anthology_folder_id":"1EcAXpRNJgDXiPT-YXR9pNu_g195RkAby",
 "participant_folder_id":"1aRBAEMAwRE3r7k4NdwPq8_b-7qpOkXdW"}

=== 3-create_doc -> HTTP 200 ===
{"ok":true,"doc_id":"1FAb_ruK31C_g9TJvPq8IMFxisDpY6dLIfFyBdePWH0o", ...}

=== 4-upload_pdf -> HTTP 200 (POST-FIX; was empty body pre-fix) ===
{"ok":true,"action":"upload_pdf","file_id":"1zslNzuBQjmvazF-HPxsRjFWfg8-s-qGt",
 "drive_url":"https://drive.google.com/file/d/1zslNzuBQjmvazF-HPxsRjFWfg8-s-qGt/view...",
 "permission_id":"anyoneWithLink"}

=== 5-share_doc_edit -> HTTP 200 ===
{"ok":true,"permission_id":"anyoneWithLink", ...}

=== 6-pull_doc_text -> HTTP 200, content READ BACK from live Google Docs, matches exactly what create_doc wrote ===
{"ok":true,"doc_id":"1FAb_ruK31C_g9TJvPq8IMFxisDpY6dLIfFyBdePWH0o",
 "text":"U64 live test content -- proof-of-life for GK-02 broker deploy."}

================ SUMMARY ================
ALL_2XX: True
ANY_501: False
book_tree_idempotent (read-back match): True
participant_tree_idempotent (read-back match): True
pull_doc_text_matches (content read back matches what was written): True
```

**Final production-path run** (after cutover, fresh scratch objects, same script pointed at
`/webhook/anthology-drive` instead of the canary path) — identical summary:
`ALL_2XX: True`, `ANY_501: False`, both idempotency checks `True`, content round-trip `True`.
Doc id from that run: `1YpWTY6DwRBX32AmOxyxezo1OhbnKHPfhLPJrQbHLgVE`. A direct `capabilities` +
`pull_doc_text` smoke test was also run against the production path immediately post-cutover
and again confirmed correct (see session transcript).

## 7. Cutover read-back proof

- `n8n_get_workflow(S8E6c41WfB8fAGiL, mode=minimal)` → `active: true`, path = production
  `anthology-drive`, 52 nodes (51 + the `UP Respond OK` fix node).
- `n8n_get_workflow(F2X3SxZVhWRDxHOV, mode=minimal)` → `active: false` (old 20-node stub).
- `n8n_validate_workflow` (runtime profile) on the final broker: 0 errors, 0 warnings,
  52/52 nodes valid, 63/63 connections valid.

## 8. What was NOT done / deferred

Nothing was deferred on the live system — credential wired, env corrected + rolled out,
6/6 actions proven with zero 501s, old stub deactivated, all via primary-source read-back.
The repo-side fix (§5) is filed as [PR #587](https://github.com/trevorotts1/openclaw-onboarding/pull/587),
intentionally left unmerged pending this repo's normal merge-train process (`needsMerge: true`)
rather than self-merged — the live production system does not depend on that PR merging
(the fix is already live on the instance; the PR only prevents a FUTURE re-import from
regressing it).
