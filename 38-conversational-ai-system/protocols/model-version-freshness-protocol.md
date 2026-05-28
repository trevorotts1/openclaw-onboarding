# Model Version Freshness Checker Protocol

Weekly check (bundled into Saturday 11pm Proactive Suggestions Scan)
for new versions of models the client uses. Surfaces updates to
operator; NEVER auto-updates without approval.

## What it checks

For each model the client uses (real-time, async, batch, embedding,
weekly tune-up, monthly review, proactive scan, scraper):

### 1. Ollama Cloud models
Query Ollama Cloud catalog API:
```
curl -s https://ollama.cloud/api/models | jq '.models[] | {name, latest_version, released_at}'
```

Compare client's configured version vs latest available.

### 2. Ollama local models
Check installed versions vs latest manifest:
```
ollama list  # shows installed
ollama show <model> --modelfile  # shows current version

# To check for updates:
ollama pull <model>:latest --dry-run  # see if newer manifest exists
```

### 3. OpenRouter models
Query OpenRouter catalog:
```
curl -s https://openrouter.ai/api/v1/models \
  -H "Authorization: Bearer ${OPENROUTER_API_KEY}" | jq '.data[] | {id, created}'
```

Compare client's configured models against catalog for newer releases
of same family.

### 4. Direct API models
For each provider in use:
- Anthropic: `GET https://api.anthropic.com/v1/models`
- Google: list latest Gemini versions via discovery API
- OpenAI: `GET https://api.openai.com/v1/models`
- DeepSeek: query their published model list

### 5. Embedding model freshness
Apply same check to the embeddings provider configured in O.6.

## Update categorization

For each detected update:

- **MAJOR** (Kimi 2.x → 3.x, DeepSeek V4 → V5, Gemini 3 → 4): "significant
  behavior change risk — review release notes carefully before updating.
  Recommend testing in a staging environment first."
- **MINOR** (Kimi 2.6 → 2.7, DeepSeek V4 → V4.1, Gemini 3.1 → 3.2):
  "incremental improvement — likely safe but verify."
- **PATCH** (Kimi 2.6.1 → 2.6.2): "bug fixes only — usually safe to
  update immediately."

## Decision tree per detected update

```
For each model the client uses:
  Get latest available version from provider catalog
  If latest > installed:
    Categorize update (MAJOR | MINOR | PATCH)
    Fetch changelog/release notes if available
    Surface to operator:
      "Model <name> has a new version: <old> → <new> (<MAJOR/MINOR/PATCH>)
       Changes per provider: <changelog summary if available>
       Recommend: <update | hold | review release notes first>
       Reply YES to update, NO to skip, DEFER to ask again next week."
```

## What it does NOT do

- NEVER auto-updates primary models without operator approval
- NEVER updates during business hours — even with approval, updates
  scheduled for next maintenance window
- NEVER updates fallback chain models without separate approval
  (fallback changes affect resilience)
- NEVER updates the embedding model without explicit re-index plan
  (changing embeddings invalidates all stored vectors)

## Operator approval flow

1. Weekly Saturday report includes any detected version updates
2. Operator replies YES / NO / DEFER per model
3. For YES responses, the agent:
   a. Backs up current `openclaw.json` config to
      `<MASTER_FILES_DIR>/model-config-backups/openclaw-<timestamp>.json`
   b. Updates the model reference in the config
   c. Tests with a synthetic request (sends a test message through
      the new model — checks response, latency, cost)
   d. If test passes → notifies "Updated successfully. Test response
      attached."
   e. If test fails → rolls back to backup, notifies "Update failed —
      kept old version. Test response showed: <error>."
4. For NO responses, the agent logs the dismissal and won't ask again
   unless a NEWER version drops
5. For DEFER, the agent asks again the following week

## Special case — embedding model update

Updating the embeddings provider is more disruptive (re-indexing
required because old vectors are incompatible). For embedding model
updates:

1. Detection still happens weekly
2. Update process is more deliberate:
   a. Operator approves update
   b. Agent triggers full re-index of all Knowledge Sources via
      `openclaw memory index --rebuild --path "<MASTER_FILES_DIR>/KnowledgeBases"`
   c. Agent verifies semantic search still works (runs test queries
      against known content)
   d. ONLY THEN switches the configured embedding model
3. Rollback path: if re-index fails or search quality drops, revert
   embedding model + restore vector indices from backup

## Cron registration

This step does NOT register its own cron. It registers a HOOK into
the existing Saturday 11pm Proactive Suggestions Scan cron from
Step 9.34. The combined run produces ONE consolidated report:

```
openclaw run proactive-suggestions-scan
  -> 7 proactive analyzers (Step 9.34)
  -> model version freshness check (this step)
  -> aggregates results
  -> delivers via notification-routing-protocol.md
```

Implementation: extend `proactive-suggestions-scan` cron action to
include freshness check as a final step.

## Allow-list

This step adds allow-list action 17:
"Update model configurations within operator-approved policies."

NEVER customer-invocable. Only triggered by operator YES response to
freshness report. Allow-list addition noted as pending for next
allow-list refresh.

## Backups

Every model config update creates a timestamped backup at
`<MASTER_FILES_DIR>/model-config-backups/openclaw-<timestamp>.json`.
Backups kept indefinitely (small files). Operator can manually
restore from any backup.
```

**B. Extend the Saturday cron to include freshness check:**

```bash
openclaw cron update proactive-suggestions-scan --command "openclaw run proactive-suggestions-scan && openclaw run model-version-freshness-check"
```

**C. Create the backup folder:**

```bash
mkdir -p "$MASTER_FILES_DIR/model-config-backups"
```

**D. Append to MEMORY.md design principles — Rule 14:**

```markdown
### Rule 14 — Models update by invitation only

The agent checks weekly for new versions of all models the client uses
(real-time, async, batch, embedding, etc.) across Ollama Cloud, Ollama
local, OpenRouter, and direct provider APIs. When a new version is
detected, the agent categorizes the update (MAJOR / MINOR / PATCH) and
notifies the operator. The agent NEVER auto-updates primary models.
Updates happen only with explicit operator approval, in a maintenance
window, with config backups and post-update synthetic tests.
Embedding model updates require full re-index before switching over.
```

**E. Append to Run Manifest:**

```markdown
