# Social Planner n8n compatibility deployment

These exports preserve the historical `brandName`/`clientEmail` creator and
`sheetId`/`row` appender while retaining the company-bound 1.1.0 contract for
modern clients. Legacy append is a public-document edit capability only: Drive
must confirm current anyone-with-link writer access, the file must be a Google
Sheet, and exactly one matching 20-column Weekly Overview header must appear in
rows 1–10. It never claims company registration or verified publication.
Modern fields never fall back to legacy after validation or upstream failure.

Canonical JSON is credential-free. Do not import individual bare exports over
live routes. Compile the complete five-workflow deployment with operator-verified
configuration (these arguments must never come from a caller's webhook body):

```sh
python3 35-social-media-planner/config/n8n/compat/prepare-compat-import.py \
  --credentials-map /secure/local/google-credential-references.json \
  --output-dir /secure/local/new-social-planner-deployment \
  --webhook-base https://YOUR-N8N-HOST/webhook \
  --legacy-template-id YOUR_VERIFIED_LEGACY_TEMPLATE_ID
```

The credentials file contains only n8n references, not OAuth access tokens:

```json
{
  "googleDriveOAuth2Api": {"id": "YOUR_DRIVE_REFERENCE", "name": "YOUR_DRIVE_NAME"},
  "googleSheetsOAuth2Api": {"id": "YOUR_SHEETS_REFERENCE", "name": "YOUR_SHEETS_NAME"}
}
```

Output files use permissions 0600 and cannot overwrite an existing deployment
snapshot. Keep them outside source control. The compiler performs no live writes.

1. Snapshot current workflow definitions and activation states.
2. Import/update the two core targets under `social-planner/v1.1.0/` and the two
   legacy targets under `social-planner-compat-20260909/`. Verify credential
   bindings and activate those targets first.
3. Smoke-test the four targets with isolated operator-owned test fixtures. Verify
   fresh legacy copies contain no historical template data on any tab before
   public sharing; verify replay preserves already shared client content.
4. Replace ownership of the two unprefixed canonical webhook paths with the
   compatibility router. Disable previous owners of those exact paths to avoid
   conflicting active webhooks. The router forwards to fixed compiled targets,
   does not follow redirects, and does not retry or downgrade failed requests.
5. Verify old and modern shapes, wrong company, mixed schemas, missing public
   permission, title-row headers, and truthful failures through canonical routes.
   Keep rollback snapshots and actual receipts; do not infer deployment success
   from workflow activation alone.

All three compatibility workflows explicitly retain both successful and failed
n8n executions. A handled HTTP failure can finish with n8n execution status
`success`, so retaining only failed executions would lose the evidence needed to
diagnose it. Execution logs may contain client payloads and document IDs: protect
them with n8n access controls and govern retention/pruning with the server's
approved policy. Do not copy client execution data into source control. Core
workflow retention settings remain as released.

Legacy append is not idempotent. If an append times out after Google may have
written the row, reconcile the spreadsheet before retrying. Never add blind
retries to copy, append, or router POST requests. Legacy creation checkpoints
`initializing`, `formatted`, and `ready`; initialization refuses to clear any
copied document already accessible by a non-owner. Unknown existing states need
preserving migration rather than automatic destructive initialization.

Offline verification (the pinned parser dependency must be installed first):

```sh
npm ci --ignore-scripts --prefix tests/social-planner/fixtures/n8n-expression-parser
python3 -m unittest discover -s tests/social-planner -p test_n8n_compat.py -v
```
