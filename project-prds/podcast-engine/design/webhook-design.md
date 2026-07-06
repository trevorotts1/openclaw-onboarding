# Podcast Production Engine: Inbound Webhook Layer Design

Version: 1.0 (design)
Scope: the per-client INBOUND path only. From "an intake form was submitted somewhere upstream" to "the client's podcast agent has a durable, deduplicated job and has started Step 1 (Ingest) of the episode construction workflow." Everything after Step 1 belongs to the pipeline design. Public hostname and ingress specifics belong to the Cloudflare Tunnel design document (sibling file in this folder).

Sources honored: PODCAST_EPISODE_GENERATION_SYSTEM.md v3.1 (ingress_and_trigger_boundary, input_payload_reference, custom_field_map, initial_setup_requirements, credit_out_queue, client_dashboard) and CLAUDE_CODE_BUILD_BRIEF.md v1.0.

Terminology: GoHighLevel, Convert and Flow, and GHL are the same system (white-label naming). "Gateway" means the OpenClaw gateway process listening on loopback 127.0.0.1:18789. No client-facing messages are ever sent from this layer; all human alerts go to the operator/founder channel only.

---

## 1. Mechanism decision: Webhooks plugin, not gateway-native hooks

**Decision: use the OpenClaw Webhooks plugin (`POST /plugins/webhooks/<routeId>`) as the standard inbound mechanism on every client box.**

Rationale, mapped to hard requirements of this system:

| Requirement (from the spec) | Webhooks plugin | Gateway-native hooks (/hooks/agent, /hooks/wake, mapped /hooks/<name>) |
|---|---|---|
| Per-client secret, never shared, never commingled | Each route carries its OWN SecretRef (source env, file, or exec), re-resolved on every request, so rotation needs no restart | ONE shared `hooks.token` guards ALL hook endpoints on the box. Any upstream pipeline holding it (Make.com, n8n, a GoHighLevel workflow action) can hit every hook, not just podcast intake. Wider blast radius on leak |
| Long-running, resumable production (credit-out queue holds jobs up to 60 days and resumes) | Drives durable, resumable TaskFlows (create_flow, run_task, resume_flow, finish_flow). A credits-out pause and a later resume are native operations | An isolated agent turn is fire-and-forget. Durability and resume would have to be rebuilt by hand |
| Deterministic session routing to the podcast agent | Each route has its OWN bound sessionKey | Achievable via allowedAgentIds and allowedSessionKeyPrefixes, but the isolation controls sit beside a shared token |
| Dedup that survives restarts | Flow identity keyed on our job key plus a persistent ledger (Section 3) gives durable dedup | idempotencyKey exists but is the only layer; we still want the ledger |
| Secret rotation without downtime | SecretRef re-resolved per request; rotate the env value or file and the next request uses it | Token change touches gateway config for every hook consumer at once |

**When a mapped gateway hook (`hooks.mappings` custom `/hooks/<name>`) is acceptable:** only as a fallback, and only when ALL of these are true: (a) the box's OpenClaw version predates or lacks the Webhooks plugin and cannot be upgraded yet; (b) the shared `hooks.token` on that box is used by NO other integration (single-purpose box); (c) the mapping sets `allowedAgentIds` to the podcast agent only and `allowedSessionKeyPrefixes` to the podcast session namespace only; (d) every delivery carries an `idempotencyKey` equal to the job key defined in Section 3; (e) durability is provided by the intake ledger since TaskFlows are unavailable. Treat this as a temporary degraded mode, record it in the client's setup notes, and migrate to the plugin at the next update window. `/hooks/wake` is never appropriate for intake: a nudge to the main session carries no payload contract, no isolation, and no dedup.

Fleet doctrine applies: prove the whole path on the operator's own box first (canary), pin the working OpenClaw version, then roll to client boxes, then validate config on every box after the fan-out.

---

## 2. Per-client route, secret, and session topology

Deployment model: every client runs their OWN OpenClaw instance on their own box (Mac mini or Virtual Private Server), gateway on loopback 127.0.0.1:18789, fronted by that client's own Cloudflare Tunnel. There is no multi-tenant box, so isolation is physical first; everything below is belt-and-suspenders on top of that.

**One route per client. Exactly one.**

- **Route ID:** `podcast-intake-<client-slug>` (example slug forms: `client-one`, `acme-media`; lowercase, dash-separated, stable for the life of the client). The slug is embedded even though the box is single-client: it makes logs unambiguous, and if a config file is ever copied between boxes the mismatch between slug and box identity is immediately detectable by the post-fan-out config validator.
- **Bound sessionKey:** `podcast:intake:<client-slug>`. This is the session the plugin drives. It belongs to the client's podcast department agent (Section 7). It is never shared with any other skill's inbound traffic.
- **Secret:** one per client per route, generated at onboarding with `openssl rand -hex 32`. Never reused across clients, never reused across routes, never derived from any other credential. This is the CLIENT'S OWN inbound secret in the client's own environment, consistent with the never-commingle and client-owns-credentials rules.
- **SecretRef:** `source: env`, name `PODCAST_INTAKE_HOOK_SECRET` (preferred, because client boxes already have a managed env store discipline), or `source: file` pointing at `~/.openclaw/secrets/podcast-intake.secret` with mode 0600 owned by the OpenClaw runtime user where the env store is awkward. Never `source: exec` unless a future vault integration demands it. The plaintext value never appears in `openclaw.json`, never in the repo, never in logs, never in chat, and is never printed or grepped; verification is always "is it SET and does a signed test request return 200," never "show me the value."

Config sketch (shape illustrative; validate against the installed OpenClaw version's schema before shipping, given known schema drift between releases):

    plugins.webhooks.routes:
      - id: podcast-intake-<client-slug>
        sessionKey: podcast:intake:<client-slug>
        secret:
          source: env
          name: PODCAST_INTAKE_HOOK_SECRET
        # route drives TaskFlows; flow identity supplied per-request by the handler (Section 3)

Flow identity within the session: each accepted submission becomes one TaskFlow whose flow key IS the job key (Section 3). The route session is long-lived; flows come and go inside it. Two submissions never share a flow.

Per-client isolation summary: own box, own gateway, own tunnel, own route, own secret, own session, own flows, own GoHighLevel private integration token and Location ID downstream. Nothing in this layer references another client's identifiers, and the skill never accepts a payload whose `location_id` does not match the Location ID configured for THIS client at onboarding (see Section 4, validation): a mismatched Location ID is quarantined, never processed, because processing it would write into another tenant's account.

---

## 3. Idempotency and dedup: a redelivered webhook can never make a second episode

Upstream pipelines retry. Make.com retries on timeout, n8n retries on error, GoHighLevel workflows can re-fire on contact updates, and a human can double-submit a form. The invariant this layer guarantees: **one distinct submission produces at most one episode and at most one publish, no matter how many times its webhook is delivered.**

### 3.1 The job key

    job_key = "pd-" + <contact_id> + "-" + first16hex( sha256( canonical_submission ) )

- `contact_id` is the GoHighLevel contact record identifier extracted by the mapper (Section 4). It anchors the key to a person.
- `canonical_submission` is built AFTER meaning-mapping, from canonical fields only, so the same submission arriving via Make.com and via a GoHighLevel webhook (different field spellings, same meaning) hashes identically:
  1. Take exactly these canonical fields when present: `mode, style, show_name, host_name, first_name, last_name, preferred_pronoun, q1_answer ... q7_answer, transparency_answer, additional_info, target_runtime, tts_model, podcast_id, location_id, contact_id, publish_timestamp, episode_type, explicit`. The `transparency_answer` (the mapped SMIQ answer, Section 4.2) is a contact-authored survey answer and is hashed like any q-slot answer: two submissions differing only in the transparency answer are two distinct episodes, never a false duplicate. When the per-style positional q-slot table is populated at onboarding and the transparency answer lands in a q-slot instead, it is already covered by `q1_answer ... q7_answer`; either way it participates in the hash exactly once.
  2. EXCLUDE volatile transport fields: delivery timestamps, event ids, execution ids, signatures, retry counters, `_test` flags, and anything not in the canonical list. These change per delivery attempt and must not defeat dedup.
  3. Normalize: trim whitespace, collapse internal runs of whitespace in answer text to single spaces, lowercase enum values, drop empty/null fields.
  4. Serialize as `key=value` lines sorted by key, joined with newlines; hash that.

Consequences: an identical redelivery collides (dedup fires); the same contact submitting a genuinely NEW survey (any answer changed) produces a new hash and a new episode, which is correct behavior for a weekly Personal Podcast.

### 3.2 The intake ledger

A persistent, per-client, append-oriented ledger on the client's box (this is durable pipeline state, not scratch, so it does NOT live in /tmp):

    ~/.openclaw/state/podcast-engine/intake-ledger/<job_key>.json

One file per job. Atomic claim via exclusive create (`O_CREAT|O_EXCL`); the filesystem is the lock, which also settles races between two concurrent deliveries of the same submission: exactly one claims the job, the other reads the existing file and answers as a duplicate. Each record carries:

    {
      "job_key": "...",
      "state": "received | needs_input | researching | writing | qc | art | audio | publishing | enrolling | complete | queued_credit_out | aged_out | failed | test",
      "received_at": "...", "updated_at": "...",
      "attempts": { "delivery_count": N, "qc_failures": N },
      "contact_id": "...", "location_id": "...", "podcast_id": "...",
      "mode": "...", "style": "...",
      "canonical_payload_path": "sibling .payload.json file",
      "flow_id": "<job_key>",
      "podbean_permalink": null,
      "notes": []
    }

The state enum is deliberately the client dashboard's status vocabulary plus the queue states, so the dashboard reads this ledger (plus the custom fields) with no separate data entry step, exactly as the spec's client_dashboard section requires. Retention: keep ledger records at least 90 days (covers the 60-day credit-out maximum hold plus margin); `aged_out` per the credit_out_queue rules.

### 3.3 Dedup decision on every delivery

1. Compute `job_key`.
2. Ledger record exists?
   - **No:** claim it (exclusive create), persist canonical payload, state `received`, `delivery_count = 1`, then trigger the flow (Section 7). Respond `200 {"status":"accepted","job":"<job_key>"}`.
   - **Yes, any state except `failed`:** increment `delivery_count`, touch `updated_at`, do NOTHING else. Respond `200 {"status":"duplicate","job":"<job_key>"}`. A duplicate is a success response on purpose: returning an error would make well-behaved upstreams retry forever.
   - **Yes, state `failed`:** the founder was already alerted for that failure; a redelivery is treated as an operator-sanctioned retry ONLY if a `retry: true` canonical field is present in the payload; otherwise duplicate-ack as above. This prevents an upstream retry storm from hammering a three-strike Quality Control failure.
3. If the flow layer is asked to `create_flow` for a flow id that already exists (belt over the ledger's suspenders), treat as duplicate: do not run a second task.

### 3.4 Double-publish guard (last line of defense)

Dedup at the door prevents a second JOB. A crash-and-resume inside one job could still re-run the publish step, so the pipeline's publish step (Step 15) must itself be idempotent, and this layer defines the contract:

- Before Podbean publish, the flow re-reads its ledger record; if `podbean_permalink` is already set, skip publish and proceed to link-back verification.
- Before writing custom fields (Step 16), read `contact.podcast_survey_episode_url` on the contact; if it already equals this job's permalink, the write already happened.
- Workflow enrollment (Step 17) runs only after permalink and field writes are confirmed, and the ledger records `enrolling` before and `complete` after, so a resume never re-enrolls. Note the spec's own warning that the 04-Podcast is Completed workflow may be field-change triggered: idempotent field writes (skip when value already correct) also prevent double-triggering that workflow.

---

## 4. Payload mapping: by MEANING, not by field name

The same intake survey can arrive through Make.com, n8n, a Convert and Flow (GoHighLevel) workflow webhook action, or a direct OpenClaw-aware sender. Field names, casing, and nesting all differ. The mapper is a deterministic normalization layer that runs before anything else touches the payload.

### 4.1 Canonical schema (target of the mapping)

Exactly the input_payload_reference fields from the spec: `mode, style, show_name, host_name, first_name, last_name, preferred_pronoun, q1_answer..q7_answer, additional_info, target_runtime, tts_model, writing_model, web_research_tool, podcast_id, location_id, contact_id, publish_timestamp, episode_type, explicit, workflow_trigger`, plus layer-local extras: `retry` (Section 3.3) and `_test` (Section 8).

### 4.2 Mapping algorithm (in order; first hit wins per field)

1. **Container flattening.** Search the JSON body root, then these known containers, in order: `customData` (GoHighLevel workflow webhooks put custom values here), `data`, `body`, `payload`, `contact`, `fields`, `answers`. Flatten one level at a time; deeper nesting is walked only inside these containers.
2. **Exact alias match.** Per-field alias tables, seeded as below and extended at onboarding when a client's pipeline is inspected:
   - `contact_id`: contact_id, contactId, contact.id, id (only when inside a `contact` container)
   - `location_id`: location_id, locationId, location.id
   - `podcast_id`: podcast_id, podcastId, podbean_podcast_id
   - `mode`: mode, production_mode, podcast_mode, podcast_type
   - `style`: style, presentation_style, writing_style, podcast_survey_writing_style, select_your_presentation_style_personal_podcast
   - `preferred_pronoun`: preferred_pronoun, my_preferred_pronoun, pronoun, pronouns
   - `q1_answer..q7_answer`: q1..q7, question_1..question_7, answer_1..answer_7, and the GoHighLevel survey field keys (the Podcast Survey per-style question fields whose internal labels are Barry/Brene/Dan/Jia Q-numbers; mapped positionally by the chosen style's path order; those internal labels never appear in any output)
   - `additional_info`: additional_info, podcast_survey__additional_info (double underscore, exactly as the custom_field_map warns), additional_information
   - transparency answer: podcast_interview_smiq, smiq, transparency_answer (lands in the correct q-slot for the chosen style's path)
   - `publish_timestamp`: publish_timestamp, publish_date, date_for_release
   - names: first_name/firstName/contact.first_name; last_name/lastName/contact.last_name
3. **Fuzzy key normalization.** Strip every non-alphanumeric character from candidate keys, lowercase, and compare to the alias table normalized the same way (so `Contact-ID`, `contact id`, `ContactId` all converge). This pass runs only for keys not consumed by pass 2.
4. **Value-shape validation.** A mapping is accepted only if the VALUE is plausible for the MEANING:
   - `mode` must normalize to `personal_podcast_style` or `interview_style_podcast` (accept human forms: "Personal", "Personal Podcast", "Interview", "Interview Style Podcast").
   - `style` must normalize to one of `counter_intuitive | vulnerable | provocative | passionate` (accept "Counter Intuitive", "Counterintuitive", the full radio label text with its trailing description, any case, any dash/space form).
   - `location_id` and `contact_id`: GoHighLevel-shaped alphanumeric identifiers; reject obvious non-ids (emails, sentences).
   - `publish_timestamp`: parseable date/datetime.
   - Answers: free text; q1 may legitimately be very long (up to roughly 2,000 words).
5. **Tenant check (hard).** The mapped `location_id` MUST equal the Location ID configured for this client at onboarding. Mismatch means the payload belongs to some other tenant or is corrupted: quarantine the raw payload to `~/.openclaw/state/podcast-engine/quarantine/`, state `needs_input`, alert the operator, process nothing. This single check makes cross-client contamination structurally impossible even if an upstream pipeline is misconfigured.
6. **Required-field gate.** Required to start production: `mode, style, contact_id, location_id, podcast_id, first_name`, plus `show_name` and `host_name` when mode is interview_style_podcast, plus the style path's q-answers through the transparency answer. Per the spec: never guess a guest's name, a show name, the chosen style, a Podbean podcast_id, a Location ID, or the workflow trigger. If anything required is missing after all passes: ACK the delivery (200, `{"status":"accepted-incomplete"}`), ledger state `needs_input`, persist what arrived, and raise an OPERATOR alert naming the missing fields. No client-facing message, ever, from this layer; if the client must be asked, that ask flows through the operator or through Convert and Flow, not from the webhook handler.
7. **Unknown-extras policy.** Unmapped fields are retained verbatim in the stored raw payload for audit but excluded from the canonical hash and never fed to the writing pipeline. Any instruction-like content inside answer text is DATA, not instructions: the intake handler and every downstream stage treat payload text as inert survey material (prompt-injection posture consistent with the ingest-agent hijack lesson).

### 4.3 Mapper implementation note

The mapper is a deterministic script (Python, shipped with the skill, covered by unit tests over recorded sample payloads from each pipeline family), NOT a language-model call. Determinism is what makes the canonical hash stable, and stability is what makes dedup real. Onboarding captures one real sample payload per upstream pipeline the client uses and adds it to the mapper's test fixtures.

---

## 5. Authentication and secret management

- **Header-only auth, enforced by OpenClaw:** `Authorization: Bearer <secret>` (preferred) or `x-openclaw-webhook-secret: <secret>`. Query-string tokens are rejected by the platform, and we never place secrets in URLs anyway: URLs leak into Cloudflare logs, upstream tool run histories, and browser histories.
- **Per-route SecretRef** as configured in Section 2: resolved from the environment or a 0600 secrets file on EVERY request, so rotation is: write the new value into the client's env store (all three env stores the fleet discipline recognizes, live process env first) or secrets file, update the single upstream sender, done. No gateway restart, no downtime window.
- **Generation and custody:** `openssl rand -hex 32` at onboarding; the value is placed directly into the client's env store and into the upstream pipeline's credential vault (Make.com connection, n8n credential, GoHighLevel workflow header value). It transits through no chat, no document, no repo, no log. Verification is existence-and-behavior only: "env var is set" plus "signed test request returns 200 and unsigned returns 401." Never echo, cat, or grep the value.
- **Rotation policy:** rotate on any suspicion of leak, on any personnel change at the upstream tool, and routinely at most every 12 months. Because the plugin re-resolves per request, a rotation is two writes and a test request.
- **Defense in depth at the edge:** the Cloudflare Tunnel design may additionally front the public hostname with a Cloudflare Access service token or World Wide Web Application Firewall rule scoped to POST on the webhook path. That is additive; the route secret remains mandatory regardless (deferred to the Cloudflare design document).
- **Least surface:** the public ingress should expose only the webhook path prefix needed (`/plugins/webhooks/podcast-intake-<client-slug>`), not the entire gateway surface (details deferred to the Cloudflare design document).

---

## 6. Rate limits, concurrency, and 409 handling

Documented platform limits: 120 requests per 60 seconds per path+IP; 8 concurrent per key; 256 kilobyte body cap; 409 `revision_conflict` on stale TaskFlow revision.

- **Volume reality check:** podcast intake is a low-single-digits-per-week event per client. The 120/60s limit is three orders of magnitude above normal load; the only thing that ever trips it is an upstream retry storm or a misconfigured loop, and in that case the limiter is a friend: the dedup ledger makes every duplicate delivery a cheap no-op, and the limiter caps the noise. No special engineering is needed to live under it; senders are told (Section 8 runbook) to back off exponentially on HyperText Transfer Protocol status 429 and honor Retry-After when present.
- **Concurrency (8 per key) and the fast-ACK rule:** an episode takes minutes to hours to produce; a webhook request must NEVER be held open for production. The intake handler does only: auth (platform), parse, map, tenant-check, dedup-claim, persist, `create_flow` + `run_task` (fire the durable flow), respond. Milliseconds of work. The response means "durably recorded," not "produced." This keeps the 8-concurrent budget irrelevant even if several submissions land together.
- **Body cap 256 kilobytes:** worst-case legitimate payload (seven long-form answers, 2,000 words each at roughly six characters per word) is under 90 kilobytes. Comfortable. Onboarding instructs upstream pipelines to send text only: no base64 files, no attachments, no embedded images (the visual description is text; the image itself is generated downstream by Kie.ai).
- **409 revision_conflict:** arises when `resume_flow` or `finish_flow` is called with a stale revision (two workers, or a resume racing a crash recovery). Handling contract for every flow mutation in this skill: on 409, re-read the flow's current state and revision; if the intended transition already happened (someone else did it), stop, success; otherwise re-apply against the fresh revision; maximum 3 attempts with short jittered backoff; on the third failure, park the job (ledger state unchanged, note appended) and alert the operator. Never blind-retry a mutation without re-reading state; that is how double transitions happen.
- **Same-submission race:** two deliveries of one submission arriving in the same second are settled by the ledger's exclusive-create claim (Section 3.2) before any flow call is made, so the 409 path is not the dedup mechanism, only the consistency mechanism.

---

## 7. From payload to production: triggering the skill and routing to the client's podcast department

Chain of custody for one accepted submission:

1. **Delivery:** upstream POSTs to the client's public URL; Cloudflare Tunnel carries it to loopback 127.0.0.1:18789; the Webhooks plugin authenticates against the route's SecretRef.
2. **Intake handler (deterministic, no language model, no Model Context Protocol):** parse, map (Section 4), tenant-check, dedup-claim (Section 3), persist canonical payload + ledger record, respond fast.
3. **Flow creation:** `create_flow` binds the job to a durable managed flow whose `controllerId` runbook advances Step 1 onward in the podcast agent's OWN turn (the bound sessionKey `podcast:intake:<client-slug>` is the client's podcast department agent). The compact, pointer-based payload location rides in the flow's `stateJson` (`ledger_payload_path`), never payload-inlined: the controller reads `~/.openclaw/state/podcast-engine/intake-ledger/<job_key>.payload.json` and executes the episode construction workflow from Step 1 per the skill. The intake handler does NOT dispatch the pipeline via `run_task(runtime: subagent)`: a sub-agent has no Model Context Protocol access and Step 1 onward is tool-bearing (see step 5). `run_task(runtime: subagent)` is reserved for pure-content sub-steps the controller runbook itself delegates (research synthesis, drafting, improvement passes, Quality Control reads that touch only text and files). In the primary in-flow path the plugin has already created the flow and the handler is its first deterministic step, so the same controller runbook simply continues; in the degraded trigger-flow path the handler creates the managed flow itself, with identical own-turn advancement.
4. **Department and persona routing:** the build wires a Podcast department onto the floor (created if absent, per the build brief) with persona matching; the route's sessionKey is bound to that department's agent so the correct persona picks the job up, the job appears on the kanban board via the ledger/status contract (Section 3.2's state enum), and the Quality Control protocol governs it from Step 9 onward. Exact department/persona wiring lives in the department design (sibling document); this layer's contract is: one sessionKey, owned by the podcast agent, no other consumer.
5. **Sub-agent boundary (hard rule):** sub-agents get NO Model Context Protocol access. Therefore every pipeline step that requires Model Context Protocol tooling (GoHighLevel media uploads, custom field writes, Skill 44 workflow enrollment, Podbean via any tool wrapper) executes in the podcast agent's OWN turn within the flow. Sub-agents may be used for pure-content work (research synthesis, drafting, improvement pass, Quality Control reads) that touches only text and files. The flow's task structure must be written so that tool-bearing steps and delegable steps are cleanly separated; the webhook layer guarantees the job arrives in the tool-bearing session to begin with.
6. **Status propagation:** each pipeline stage updates the ledger record's `state` as it moves (received, researching, writing, qc, art, audio, publishing, enrolling, complete, queued_credit_out, aged_out, failed). The client dashboard and the kanban both read this; the webhook layer owns states `received`, `needs_input`, `test`, and `duplicate` accounting; the pipeline owns the rest.
7. **Silence discipline:** this entire chain emits zero client-facing messages. Client notification happens exclusively via Convert and Flow workflows at Step 17, exactly at the responsibility boundary the spec draws. Operator alerts (missing fields, tenant mismatch, 409 exhaustion, ledger corruption) go to the founder/operator alert channel only.

---

## 8. Per-client onboarding: setup steps and test-submission verification

Run once per client, after the AI Workforce Interview gate and as part of podcast engine enablement. All steps are operator-driven; the client is never spammed.

**Setup:**

1. Generate the route secret (`openssl rand -hex 32`); write it to the client's env store as `PODCAST_INTAKE_HOOK_SECRET` (verify SET in the live process environment, not just in a file), or to `~/.openclaw/secrets/podcast-intake.secret` mode 0600.
2. Add the route to the client's OpenClaw config: id `podcast-intake-<client-slug>`, sessionKey `podcast:intake:<client-slug>`, SecretRef per Section 2. Validate the config against the INSTALLED OpenClaw version's schema (schema drift between releases is a known trap) before applying. Config writes as the correct runtime user, never root.
3. Reload/restart the gateway per the platform's restart doctrine for that box type (Mac: the kickstart-then-stop sequence; Virtual Private Server: compose recreate, not bare restart, so env changes load). Confirm the gateway is healthy after.
4. Wire the public path: Cloudflare Tunnel ingress mapping the client's public hostname + webhook path to `http://127.0.0.1:18789` (hostname, Access policy, and revocation lever are specified in the Cloudflare design document; revocation of the tunnel hostname is also the kill switch that cuts a departed client's intake off cleanly).
5. Configure the ONE upstream sender the client actually uses (GoHighLevel workflow webhook action, Make.com, or n8n): method POST, the public URL, header `Authorization: Bearer <secret>` (value pasted from the credential store, never from chat), JSON body carrying the survey fields plus `contact_id`, `location_id`, `podcast_id`, mode and style. Capture one real sample payload from this pipeline and add it to the mapper's test fixtures.
6. Record in the client's setup notes: route id, sessionKey, secret LOCATION (env var name or file path, never the value), upstream pipeline type, sample payload fixture path, date.

**Test-submission verification (all must pass before go-live; the spec's initial_setup_requirements mandates a received test submission):**

| # | Test | Expected |
|---|---|---|
| T1 | POST with NO auth header | 401, nothing written |
| T2 | POST with wrong secret | 401, nothing written |
| T3 | POST with secret in query string only | rejected (platform refuses query tokens), nothing written |
| T4 | POST full synthetic payload with `_test: true`, correct secret | 200 accepted; ledger record created in state `test`; mapper output shows every canonical field correctly extracted; flow runs Step 0/Step 1 dry checks ONLY and stops; no research, no draft, no publish, no enrollment, no client message |
| T5 | Re-POST the identical T4 payload | 200 duplicate; `delivery_count` = 2; no second ledger record, no second flow |
| T6 | POST T4 payload with one answer changed | 200 accepted; NEW job key, NEW ledger record in state `test` (proves hash sensitivity) |
| T7 | POST payload with `location_id` of a different tenant | 200 accepted-incomplete or quarantine per Section 4.2 step 5; operator alert fired; nothing processed |
| T8 | POST payload missing `style` | ACK; state `needs_input`; operator alert names the missing field |
| T9 | Confirm end to end from the ORIGIN: run T4 through the real public Cloudflare URL, not loopback | Same result as T4 (proves tunnel + edge config, not just local wiring) |

`_test: true` handling: the flag is honored ONLY for payloads whose contact identifiers match the designated test contact recorded at onboarding; it short-circuits the flow after ingest validation and marks the ledger record `test` so dashboards can filter it. Test records never touch Podbean, never write custom fields, never enroll workflows: nothing downstream can fabricate or notify. Cleanup deletes `test` ledger records after verification.

Independent verification rule applies: onboarding is not "done" until T1 through T9 have actually been executed and observed, end to end, on that client's box, with results noted in the setup record.

---

## 9. Cloudflare Tunnel public wiring (interface contract; specifics deferred)

The gateway listens ONLY on loopback 127.0.0.1:18789. Public HyperText Transfer Protocol Secure exposure is exclusively via the client's Cloudflare Tunnel, which terminates Transport Layer Security at Cloudflare's edge and forwards to loopback. This layer's requirements on the tunnel design (owned by the Cloudflare design document in this folder):

1. **Path contract:** the public URL forwards to `http://127.0.0.1:18789/plugins/webhooks/podcast-intake-<client-slug>` unchanged. Whether the public path is identical or vanity-mapped is the tunnel design's choice; the origin path is fixed.
2. **Method and scope:** expose POST on the webhook path. Do not expose the gateway's other surfaces publicly unless another design explicitly requires it; narrower ingress is the default.
3. **No query-string secrets anywhere** (edge logs URLs; the platform rejects them anyway).
4. **Optional edge auth is additive:** a Cloudflare Access service token or firewall rule on the path is welcome defense in depth, but the route SecretRef remains the authoritative auth and must be enforced regardless.
5. **Revocation lever:** disabling the tunnel hostname (or the Access policy) must cleanly cut a departed client's intake without touching the box, aligning with the engine-wide access-revocation requirement in the build brief.
6. **Body size:** edge must permit bodies up to the platform's 256 kilobyte cap on this path.
7. **Never Tailscale; Cloudflare Tunnel only** (fleet doctrine).
8. **Hostname naming, certificate handling, and BlackCEO-hosted versus client-hosted decisions:** deferred entirely to the Cloudflare design document; this layer is agnostic as long as points 1 through 6 hold.

---

## 10. Failure modes summary

| Failure | Behavior |
|---|---|
| Upstream retry storm | Rate limiter caps it; dedup ledger no-ops every duplicate; zero duplicate episodes |
| Duplicate delivery (normal retries) | 200 duplicate ack; delivery_count incremented; nothing re-runs |
| Missing required field | ACK + `needs_input` + operator alert; never guessed, never client-spammed |
| Wrong tenant location_id | Quarantine + operator alert; structurally cannot write to another client |
| Secret leak suspected | Rotate SecretRef source value + upstream credential; zero-downtime |
| 409 revision_conflict | Read-check-reapply, max 3, then park + operator alert |
| Crash mid-production | Durable TaskFlow + ledger resume; publish/link-back/enrollment steps individually idempotent (Section 3.4) |
| Credits out mid-run | Pipeline moves job to `queued_credit_out` (60-day cap per spec); webhook layer unaffected; resume via resume_flow |
| Gateway down at delivery time | Upstream gets connection failure and retries per its policy; dedup makes late success safe |
| Payload is non-JSON or over 256 kilobytes | Platform-level 4xx; nothing written; persistent repetition surfaces via operator log review |

---

## 11. Build checklist for this layer

- [ ] Webhooks plugin route + SecretRef config template added to the skill, schema-validated per installed OpenClaw version
- [ ] Deterministic mapper script with alias tables, fuzzy pass, value-shape validation, tenant check; unit tests over fixture payloads from GoHighLevel, Make.com, n8n samples
- [ ] Canonical-hash + job-key module with tests (identical redelivery collides; one-character answer change diverges; volatile fields ignored)
- [ ] Ledger module: exclusive-create claim, state transitions, dashboard-readable schema, 90-day retention sweep
- [ ] Flow trigger: create_flow/run_task wiring to sessionKey `podcast:intake:<client-slug>`; 409 read-check-reapply helper
- [ ] Idempotent publish/link-back/enrollment guards specified into the pipeline design (Section 3.4 contract)
- [ ] Onboarding runbook + T1-T9 verification script (executable, so verification is observed, not asserted)
- [ ] Operator-alert pathways for needs_input, quarantine, 409 exhaustion
- [ ] Canary proof on the operator's own box before any client rollout; config validation on every box after fan-out
