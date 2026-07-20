# Test-target repoint — BlackCEO LLC -> BCEO Client Sandbox (2026-07-20)

Operator ruling (Trevor, 2026-07-20, verbatim): "use this use BCEO Client Sandbox,".
The designated GoHighLevel test sub-account for operator-box test runs moved from
**BlackCEO LLC** (`Mct54Bwi1KlNouGXQcDX`) to **BCEO Client Sandbox**
(`XCgFTEA1oDvsPnTqqgoB`).

## What was repointed (live, operator box, same day)

Six live settings, all previously naming the BlackCEO LLC location id (or an inert
`loc-xyz` placeholder), now name `XCgFTEA1oDvsPnTqqgoB`:

- `~/.openclaw/secrets/.env` — `GOHIGHLEVEL_LOCATION_ID`,
  `GOHIGHLEVEL_ALLOWED_LOCATION_IDS`, `CAF_ALLOWED_LOCATION_IDS`
  (timestamped backup left beside the file).
- `~/.openclaw/openclaw.json` `env.vars` — `CAF_ALLOWED_LOCATION_IDS` (was the
  real BlackCEO LLC id), plus `GOHIGHLEVEL_LOCATION_ID` and
  `GOHIGHLEVEL_ALLOWED_LOCATION_IDS` (were the never-valid placeholder `loc-xyz`,
  a known source of false auth/refusal reports). JSON re-validated after edit;
  timestamped backup left beside the file.

Repo-side designation prose updated in the same change:
`06-ghl-install-pages/tools/gates.json` (`selectors._note`) and
`06-ghl-install-pages/references/golden/README.md` (annotation).

## Live proof recorded at repoint time

- Agency-token listing of all 647 sub-accounts contains exactly one
  "BCEO Client Sandbox", id `XCgFTEA1oDvsPnTqqgoB`; `GET /locations/<id>` via the
  freshly repointed `GOHIGHLEVEL_LOCATION_ID` returned HTTP 200 with that name.
- Write-gate check (`safety_gate.check_write`, no network write sent): a write
  targeting `XCgFTEA1oDvsPnTqqgoB` passes the repointed allowlist; a write
  targeting the old `Mct54Bwi1KlNouGXQcDX` is refused.

## Ownership check (why this target is safe for tests)

- Sub-account registered to an internal blackceo.com operator address; business
  name equals the sub-account name; created 2022-09-26.
- Interior is dormant test material: 76 contacts total, newest contact activity
  2026-02-11; contact email domains include throwaway/test domains and typo'd
  test addresses; 25 workflows, all operator program templates last touched
  2023–2025 (13 published but stale). No live client operations observed.
- Caution retained: 13 stale published workflows exist inside the sandbox, so
  test runs that enroll contacts should keep the draft-only default
  (`CAF_DRAFT_ONLY=true`) unless a test explicitly needs a trigger to fire.

## Credential scope (known follow-up)

- The agency token lists locations and reads location metadata but is refused
  (HTTP 401) on location-level reads (contacts, workflows) and cannot mint a
  location token via the OAuth endpoint.
- The location-scoped GoHighLevel token in `GOHIGHLEVEL_API_KEY` is provably
  scoped to the OLD fixture only (HTTP 200 on `Mct54Bwi1KlNouGXQcDX`,
  HTTP 403 on `XCgFTEA1oDvsPnTqqgoB`). REST flows that use it against the new
  target will fail closed until the operator issues a Private Integration Token
  INSIDE BCEO Client Sandbox (Settings -> Private Integrations) and places it in
  `GOHIGHLEVEL_API_KEY`.
- The Firebase refresh-token (internal/browser) path works against the sandbox
  today — proven by live read-only workflow/contact listings during the
  ownership check above.

## Prior evidence annotation (no rewrites)

Every capture, golden blob, gate note, and evidence bundle in this repository
dated before 2026-07-20 that names BlackCEO LLC / `Mct54Bwi1KlNouGXQcDX` was
produced against the PREVIOUS designated fixture. Those records stay exactly as
written; only the forward-looking designation changed.
