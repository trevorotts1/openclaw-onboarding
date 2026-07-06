# Convert and Flow field layer

Slice: convert-and-flow-field-layer (Wave 1 unit W1.18).
Design source: design/ghl-design.md Sections 2 to 5. Client-visible name is
always Convert and Flow, never GoHighLevel and never GHL.

This layer owns the custom-field read and write plane for the Podcast
Production Engine: credential resolution (the call site), the field-key to
field-id cache, the batch-then-URL-last writer, and byte-for-byte read-back.
The data plane is Skill 44 caf (Tier 0) plus Skill 29 direct REST (Tier 3)
ONLY. There is no Model Context Protocol path here by construction, because a
sub-agent performing a field write would silently have no MCP tools, exactly
the false-done class the quality-control protocol exists to kill.

## Modules

    field_layer/constants.py   endpoints, alias sets, exact field keys, hygiene
    field_layer/redact.py      secrecy wrapper (never print a token value)
    field_layer/resolver.py    ENV-CHECK-BEFORE-FAIL for PIT plus Location ID
    field_layer/state.py       per-client ghl-state.json (field_map section)
    field_layer/transport.py   Tier 0 caf plus Tier 3 REST, no MCP
    field_layer/field_map.py   field-key to field-id build and cache
    field_layer/writer.py      batch-then-URL-last write plus read-back verify
    field_layer/cli.py         runtime entry point for pipeline Steps 14 to 17
    field_layer/tests/         offline unit tests (no network, no subprocess)

## Runtime entry point

    python3 -m field_layer.cli --state-dir <dir> resolve
    python3 -m field_layer.cli --state-dir <dir> --location-id <loc> build-map
    python3 -m field_layer.cli --state-dir <dir> --location-id <loc> \
        write-back --contact-id <id> --values-file <values.json>
    python3 -m field_layer.cli --state-dir <dir> --location-id <loc> \
        verify --contact-id <id> --values-file <values.json>

Exit codes: 0 success, 2 credential not resolved, 3 location mismatch
(isolation), 4 required custom fields missing, 5 rate limit, 1 other error.

The values file is a flat JSON object mapping exact field keys to string
values, for example the five required link-back keys plus optional
full-transcript and book_teaser.

## Credential resolution (design Section 2.3)

The resolver runs the ENV-CHECK-BEFORE-FAIL sequence before any missing verdict:
live process environment first, then every environment-store file, then
openclaw.json in BOTH shapes (env.vars.KEY and root env.KEY), then
auth-profiles.json, for every alias, and a path-only grep sweep last. It calls
the shared fleet resolver as a first-class store (the field-layer call site) and
adds the stores that resolver does not cover, so the field layer stays in
lockstep with the fleet while never falsely reporting a client key missing.

Isolation: only the LOCATION Private Integration Token is resolved. The Agency
PIT and the Firebase refresh token are deliberately excluded from the alias set
and can never be substituted. The webhook payload location_id must equal the
environment location_id or the run aborts with an isolation code.

Secrecy: no token value ever appears in stdout, stderr, logs, JSON output, or
exceptions. Reports say only alias name, store name, found or not found,
prefix_ok, and length. The token travels only in an in-memory Authorization
header for Tier 3 and is never placed on the caf argv (caf resolves its own
credential from the environment).

## Tier routing and a build-time finding

Reads (contact get, custom-field list, read-back) go Tier 0 caf first, Tier 3
REST fallback. Writes are the notable case: the current fleet caf contacts
update command exposes email, phone, name, and tags only, with no custom-field
option. A custom-field write is therefore command-unsupported at Tier 0 and
escalates to Tier 3 per the design Section 1 escalation rule (Tier 0 command
unsupported goes to Tier 3 REST with the same PIT). The transport verifies this
at runtime with a capability probe against caf contacts update help rather than
assuming it blindly, so a future caf release that gains a custom-field write is
picked up automatically. A 429 never escalates or tier-hops: all tiers share one
per-location bucket, so a 429 is raised as RateLimited for the caller to
full-stop on.

## Write ordering (design Sections 3.3 and 3.4)

One batch call carries title, description, Episode Package link, Speech Script
link, and (when present) the optional full transcript and book_teaser. Then a
second, separate call writes contact.podcast_survey_episode_url ALONE and LAST,
because the client account workflow 04-Podcast is Completed is triggered by that
field changing. Writing the URL is a live customer-facing trigger, so it lands
only after every other field is in place and the record is complete.

Read-back verification fetches the contact and compares every written value
byte-for-byte. Only a passing read-back counts as a Convert and Flow save
confirmation. A mismatch retries the failing writes once (batch subset first,
URL alone last, ordering preserved), then raises for the pipeline failure
handler. Value hygiene is enforced before any write: links are bare URLs (no
markdown, no surrounding quotes), and title and description carry no code fences
and no em dash characters.

## book_teaser (Interview mode only)

The book_teaser field may not exist in an account. When absent, the layer
surfaces a founder reminder to create a custom field named book_teaser, notes
the absence in the result, never creates the field silently, and never fails the
episode over it.

## State file

<state-dir>/ghl-state.json is shared across the whole data plane. This layer
owns only the field_map and book_teaser_field_present sections and writes them
with a read-modify-write so sibling sections (folders, workflows, rate,
credential-gate fingerprint) stay intact. No secret material is ever stored
(design Section 8).

## Live-verify items for the canary

- The contacts Version header: design Section 3.2 states 2021-07-28; the Skill
  29 reference documents 2021-04-15 for some endpoints. The header is a single
  named constant (GHL_API_VERSION, overridable with PODCAST_GHL_API_VERSION) so
  the operator-box canary can pin the accepted value against a live response.
- The X-RateLimit header casing and the Retry-After shape on a live 429.

## Tests

    cd 58-podcast-production-engine/scripts/caf
    python3 -m pytest field_layer/tests -q

The suite is fully offline: a FakeDataPlane stands in for the transport, so no
network, no subprocess, and no caf binary are required.
