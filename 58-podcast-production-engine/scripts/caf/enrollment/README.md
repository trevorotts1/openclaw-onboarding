# Enrollment Layer (PRD Step 17)

Skill 44 caf (Tier 0) workflow enrollment for Interview-mode episodes:
discovery-then-verify-then-enroll, a double-enrollment guard so no customer is ever
double-notified, and a hard Personal-mode refusal. Everything is verified through caf
reads. Tier 3 REST is the sub-agent-safe fallback for the enroll call only. The two
Model Context Protocol tiers are forbidden here because sub-agents get no MCP
injection.

## The two workflows (exact names, standardized across clients)

- 06-Podcast_Episode_Is_Ready adds the "podcast episode is ready" tag.
- 04-Podcast is Completed is field-triggered by the Podcast Survey Episode URL
  changing; it adds the "Podcast Completed Survey Style" tag.

## Why verification is tag-based (honest, no false done)

The public Convert and Flow API exposes no endpoint that lists a contact's active
workflow enrollments. The caf-observable proof of enrollment is the tag each workflow
applies. So this module verifies enrollment by re-reading the contact through caf and
confirming the workflow's known tag, and, for a workflow it enrolled directly, by the
enroll call's own success acknowledgment. If neither evidence is present after one
retry, the result is UNVERIFIED and the episode is not marked delivered.

## The hard gate

Enrollment runs only after both of the following are true:

1. The Podbean episode exists and its permalink is captured.
2. Every Step 16 field write passed byte-for-byte read-back verification.

Enrolling earlier would notify a customer about an episode that is not there, which
the responsibility-boundary rule makes a total failure. The gate refuses with a typed
GateError.

## Double-enrollment guard

Workflow 04 is field-triggered, so the Step 16 URL write may have already enrolled the
contact. This module reads the contact first and enrolls 04 explicitly only when the
field trigger did not (its tag is absent), making a double SMS impossible from our
side. Workflow 06 is enrolled explicitly by workflow ID, or, when discovery recorded a
tag trigger, by applying the recorded tag.

## Hard Personal-mode refusal

enroll_episode hard-refuses personal_podcast_style with a ModeGuardError before any
caf call. Personal Podcast mode never touches workflows 04 or 06; it updates the
running episode spreadsheet instead (a separate layer) and sends no customer message.
Season-Strategy and Episode-Asset-Pack modes are skipped cleanly (no enrollment).

## No workflow building at runtime

A workflow missing by name is a DiscoveryError: stop setup and surface to the founder.
Building a workflow needs the separate Skill 44 Firebase refresh token and is an
operator decision, never an autonomous runtime act. IDs are discovered once at setup
and cached in the per-client ghl-state.json; they are never guessed.

## Boundary

After enrollment (or the Personal spreadsheet update owned elsewhere) the engine stops.
This module never calls a conversations or messages endpoint. Convert and Flow owns all
customer messaging.

## Rate limits

On HTTP 429 anywhere (caf or the REST fallback) the module full-stops with a typed
RateLimited so the caller hold-queues the job. It never blind-retries and never
tier-hops, because all tiers share one per-location bucket.

## Usage

Self-test (offline, no live CRM):

    python3 enroll.py --self-test

Enroll an Interview-mode episode (job JSON carries mode, contact_id,
podbean_permalink, field_writeback_verified, and optionally location_id):

    python3 enroll.py enroll --job job.json --state ghl-state.json

Programmatic entry point:
enroll_episode(mode, contact_id, state, runner=..., preconditions=...) returns a dict
with the per-workflow action, verification evidence, and the boundary line, and raises
EnrollUnverified when enrollment cannot be confirmed after one retry.

## Exit codes

0 ok, 1 generic, 2 Personal-mode refusal, 3 usage, 4 gate not met, 5 rate-limit stop,
6 unverified after retry, 7 workflow discovery failure.

## Tests

    python3 -m pytest tests/test_enroll.py -v

All tests are hermetic. caf is replaced by an injected fake runner and the one
REST-fallback test monkeypatches requests.post; no live CRM is contacted.
