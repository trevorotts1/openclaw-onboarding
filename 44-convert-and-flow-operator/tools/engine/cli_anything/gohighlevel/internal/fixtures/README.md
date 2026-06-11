# Contract Fixtures — How to Capture and Refresh

## Purpose

These fixtures define the expected shape of the GHL internal API contract.
The probe (`run_contract_probe`) compares LIVE READ-ONLY responses against
`contract.schema.json`.  The golden blob in `contract.golden.json` records
the exact snapshot from the capture session.

## Synthetic fixture warning

The shipped `contract.golden.json` is marked `"_synthetic": true`.  It was
built at skill-44 build time from verified source-code shapes (the
`STRIP_KEYS` frozenset, the `VERIFIED_ACTIONS` set, and the workflow
GET/PUT payload structure) and has NOT been validated against a live GHL
backend.

Until you recapture from a real canonical account:

- The contract probe runs and returns `ok=True` for CI purposes.
- The probe emits a `SYNTHETIC_FIXTURE` warning to stderr so you know it has
  not been ground-truthed.
- Workflow writes are NOT blocked by the synthetic fixture alone.

**Before first production deploy, recapture from the canonical account**
using the procedure below.  After the first recapture the `_synthetic` flag
will be absent from the new golden file.

## Files

| File | Purpose |
|---|---|
| `contract.golden.json` | Captured response shapes from ONE real account (redacted) |
| `contract.schema.json` | Minimal shape assertions the probe enforces |

## Capture procedure

The capture is a READ-ONLY operation against the canonical account.
It never creates, modifies, or deletes anything.

```bash
# From the engine root, with the canonical account credentials in env:
export GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN="..."
export GOHIGHLEVEL_LOCATION_ID="..."
export CAF_PROBE_WORKFLOW_ID="<a real workflow id in that location>"

python3 - <<'EOF'
import json, os
from cli_anything.gohighlevel.internal.adapter import InternalAdapter
from cli_anything.gohighlevel.utils.workflow_builder import VERIFIED_ACTIONS

loc = os.environ["GOHIGHLEVEL_LOCATION_ID"]
wf_id = os.environ["CAF_PROBE_WORKFLOW_ID"]
adapter = InternalAdapter(loc)

wf = adapter.get_workflow(wf_id)
assert wf.ok, f"GET failed: {wf.error}"

golden = {
    "capture_date": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
    "account_id_redacted": loc[:6] + "...",
    "workflow_get_shape": {
        "top_level_keys": sorted(wf.data.keys()),
        "has_version": "version" in wf.data,
        "has_workflowData_templates": (
            "workflowData" in wf.data and "templates" in wf.data.get("workflowData", {})
        ),
    },
    "strip_keys_present_in_get": sorted(
        k for k in __import__("cli_anything.gohighlevel.internal.contract", fromlist=["STRIP_KEYS"]).STRIP_KEYS
        if k in wf.data
    ),
    "verified_actions_snapshot": sorted(VERIFIED_ACTIONS),
}

out = "cli_anything/gohighlevel/internal/fixtures/contract.golden.json"
with open(out, "w") as f:
    json.dump(golden, f, indent=2)
print(f"Golden fixture written to {out}")
EOF
```

## capture_date

Recorded inside `contract.golden.json` as `capture_date`.  The probe alert
includes this date so the operator knows how stale the fixture is.

## Refresh procedure

When the Sunday probe fires a CONTRACT_DRIFT alert:

1. Re-run the capture command above with the canonical account credentials.
2. Review the diff: `git diff cli_anything/gohighlevel/internal/fixtures/`.
3. Update `contract.schema.json` if the schema must change to match the new shape.
4. Bump skill 44 version (`skill-version.txt`), update CHANGELOG.md.
5. Ship via `scripts/release.sh`.  The Sunday update re-enables fleet-wide writes
   after the probe passes on each box.

## CI mock transport

In CI the backend is mocked.  `run_contract_probe` is pointed at a
`FakeTransport` that replays `contract.golden.json`.  No live CRM call ever.
See `tools/engine/tests/test_adapter_probe.py` for the CI fixture.
