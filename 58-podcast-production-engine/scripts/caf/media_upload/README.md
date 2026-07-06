# Media Upload Layer (PRD Step 14)

Tier 3 direct REST multipart upload of the episode MP3, cover JPEG, and (Interview
mode only) the book-teaser PDF into the client's Convert and Flow media library,
followed by mandatory HEAD-verification of every returned public URL.

## Why Tier 3 only

Media upload is the one operation where Tier 3 REST is not a fallback but the only
path. Tier 0 caf performs no binary multipart. The two Model Context Protocol tiers
are structurally forbidden in this pipeline because sub-agents get no MCP injection.
So this module speaks raw HTTPS to services.leadconnectorhq.com and nothing else.

## Endpoint contract (pinned from Skill 29 references/medias.md)

- POST https://services.leadconnectorhq.com/medias/upload-file (multipart/form-data)
- Header: Authorization Bearer LOCATION_PIT (an agency PIT returns 401 for media)
- Header: Version 2021-07-28
- Form fields: file (binary), locationId, name, hosted=false, optional parentId
- Response: fileId and url. Trust the url field. The CDN host varies by account and
  era, so no host is ever hardcoded or asserted.

## Folders are LOOKUP-ONLY at runtime

Folder creation via REST returns 404 (verified caveat). The engine never creates a
folder mid-episode. It reuses the podcast, podcast images, and podcast episodes
folders when present, matched case-insensitively and trimmed so a manually created
"Podcast" folder is reused, never duplicated. On a duplicate match it uses the oldest
and warns. When a child folder is absent it degrades to the parent podcast folder,
then to the media root, and never fails an episode over folder creation. Folder
provisioning is a one-time onboarding task, not a runtime dependency.

## Public-URL verification (mandatory)

Every returned url is verified with an unauthenticated HEAD (ranged GET fallback)
before it is used anywhere. Requirements: HTTP 200 or 206. A text/html body is a hard
failure because it is a login or error page, which is exactly the downstream Podbean
failure this check exists to prevent. An application/octet-stream type is accepted
with a warning (real CDN behavior); any other family mismatch is a warning but the
URL must still be publicly reachable.

## Filenames (ghl-design.md Section 4.2)

- Cover JPEG: letters, numbers, underscores, dashes only, single extension period,
  form client_name_episode_title.jpg
- Episode MP3: client name first then title, spaces allowed,
  form "Client Name - Episode Title.mp3"
- Teaser PDF: same character rules as the MP3

## Hard rules honored

- Never print or echo a secret value. Reports carry SET or NOT SET, the resolving
  alias, the store, the pit- prefix check, and length only.
- Named client's own Location PIT and own Location ID only. A webhook location_id that
  disagrees with the environment is a hard tenant abort.
- On HTTP 429: full stop. Never blind-retry, never tier-hop (all tiers share one
  per-location bucket). RateLimited surfaces so the caller hold-queues the job.
- The engine stops after media storage in its own lane and never messages a customer.
  Convert and Flow owns all messaging.

## Usage

Self-test (offline, no network):

    python3 upload_media.py --self-test

Store an episode's media (job JSON carries mode, client_name, episode_title,
cover_path, mp3_path, and optionally teaser_path and location_id):

    python3 upload_media.py store --job job.json --state ghl-state.json

Verify one public URL:

    python3 upload_media.py verify --url <url> --family image/

Programmatic entry point: store_media(job, cred, location_id, state=..., transport=...)
returns a dict of per-asset fileId, url, reachability status, and warnings, and raises
before Podbean on any terminal upload or reachability failure so a half-uploaded
episode is never partially published.

## Exit codes

0 ok, 1 generic error, 2 credential missing, 3 usage, 4 reachability failure,
5 rate-limit stop.

## Tests

    python3 -m pytest tests/test_upload_media.py -v

All tests are hermetic. No live CRM or CDN is contacted; every HTTP call goes through
an injected fake transport.
