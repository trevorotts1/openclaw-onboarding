# Podcast Production Engine: independent webhook layer tests

These tests are the INDEPENDENT check on the inbound webhook mapper, job-key module,
and intake ledger authored by the webhook-layer slice (W1.16). They own only files
under this directory. They cover CHECKLIST Part C item 2 (deterministic mapper with
fixture unit tests for the Convert and Flow, Make.com, and n8n families, plus job-key
collision and divergence) and item 3 (idempotency: an identical redelivery yields one
episode record and a duplicate acknowledgment; a one-answer change yields a new job).
Every behavior traces to design/webhook-design.md Sections 3 and 4 and the T5 to T8
verification tests in Section 8.

## What is proven

- Mapping is by MEANING, not field name. Three fixtures carry ONE submission with
  identical meaning but different field spellings, casing, nesting, whitespace, and
  volatile transport fields; the mapper collapses all three to the same canonical
  hash fields (test_webhook_mapper_meaning.py).
- The job key collides on an identical redelivery and across pipeline families, and
  diverges on a genuinely changed answer; volatile transport fields and non-hash
  canonical extras never move the key (test_webhook_job_key.py).
- Idempotency end to end through intake(): one record and a duplicate ack on
  redelivery, a new job on a changed answer, dedup across families, the
  exclusive-create claim settling a same-submission race, failed-job retry gating,
  and the _test flag recording a test rather than a live episode
  (test_webhook_idempotency_ledger.py).
- Tenant isolation (a wrong location_id is quarantined, nothing written) and the
  required-field gate (a missing required field is held for the operator, never
  guessed), covering T7 and T8 (test_webhook_tenant_and_required.py).

## System under test (SUT)

The default SUT is the executable-specification oracle in spec_reference/. It is NOT
the production mapper; it encodes the same contract, derived from webhook-design.md
Sections 3 and 4, so the tests are self-verifying and provable on any branch before
the production mapper is merged in. The production mapper is owned by W1.16 and ships
under 58-podcast-production-engine/scripts/webhook/.

To run the SAME tests against the shipped mapper (the independent-check role), bind it
as the SUT in one of two ways:

- Set the environment variable PODCAST_WEBHOOK_SUT to an importable module name that
  exposes the contract below. A failed import is a hard error, never a silent fallback.
- Or drop a module named podcast_webhook_sut on the Python path (a thin adapter that
  re-exports the contract names from the shipped mapper). conftest.py picks it up
  automatically.

If the shipped mapper diverges from the contract, these tests fail. That is the intent.

## The contract the SUT must expose

    map_payload(raw, tenant_location_id, aliases=None, style_transparency_slot=None)
        -> result with .status in {accepted, accepted-incomplete, quarantine},
           .canonical (dict), .missing (list), .alerts (list), .tenant_ok (bool)

    compute_job_key(canonical) -> "pd-<contact_id>-<16 lowercase hex>"
        raises when contact_id is absent

    Ledger(base_dir) -> object with:
        claim(job_key, canonical, state="received")  # O_CREAT|O_EXCL; None if already claimed
        read(job_key) -> record or None
        touch_duplicate(job_key) -> record  # increments attempts.delivery_count
        set_state(job_key, state) -> record
        count() -> int  # number of episode records

    intake(raw, tenant_location_id, ledger, on_accept=None, aliases=None,
           test_contact_id=None, style_transparency_slot=None) -> response dict
        accepted            -> {"status": "accepted", "job": job_key}
        duplicate           -> {"status": "duplicate", "job": job_key}
        accepted-incomplete -> {"status": "accepted-incomplete", "job": job_key|None, "missing": [...]}
        quarantine          -> {"status": "quarantine"}
        on_accept(job_key, canonical, record) fires exactly once per genuinely new job
        and never on a duplicate, quarantine, or needs_input record.

The list of fields that participate in the canonical hash is the contract's authority
and lives in spec_reference/job_key.py as HASH_FIELDS. Fields the mapper carries but
that must NOT affect the key (writing_model, web_research_tool, workflow_trigger,
retry, _test) are deliberately excluded from that list.

## Running

    ./run-webhook-tests.sh
    ./run-webhook-tests.sh -k idempotency
    PODCAST_WEBHOOK_SUT=<module> ./run-webhook-tests.sh   # bind the shipped mapper

No network, no language model, no Model Context Protocol, no secrets. Ledgers are
written under a throwaway pytest tmp directory; nothing touches a real box.
