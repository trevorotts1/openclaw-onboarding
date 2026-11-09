# Vendor research receipt

Dated 2026-10-05. Verified live by the orchestrator against api.kie.ai unless noted. Vendor text = KIE's official kie-models reference (references/en.md), fetched through https://kie.ai/.well-known/agent-skills/index.json (skills CLI 1.7.0).

| # | Fact | Source | Status |
|---|---|---|---|
| 1 | GET https://api.kie.ai/api/v1/models returns the catalog; filters taskType, provider, q; not paginated; shape {code,msg,data:{total,models[]}} | live probe; vendor text "Discovering models" | VERIFIED. Contradicts the architecture memo assumption that no catalog exists. |
| 2 | GET /api/v1/models/<model>/schema returns data {model, openapi}; openapi is inline OpenAPI 3.1 or null; $ref not inlined; keys literal, %20 spaces, some trailing spaces | live probe; vendor text "Reading the schema" | VERIFIED |
| 3 | Slash in the model name is not URL-encoded | vendor rule 4 | VERIFIED |
| 4 | models, schema, price, success-rate share one budget of 1 request per second per account | vendor text "Rate limits" | VERIFIED |
| 5 | HTTP 200 can carry body code 401, 402, 404, 422, 429, 433, 455 | vendor text, live probe | VERIFIED |
| 6 | createTask body {model, input, callBackUrl?} returns data.taskId; recordId is not the polling key | vendor text, live probe | VERIFIED |
| 7 | recordInfo states waiting, queuing, generating (running), success, fail; data.response is parsed resultJson; creditsConsumed present | vendor text, live probe | VERIFIED |
| 8 | Results at response.resultUrls; Suno audio at response.data[].audio_url; Suno text at response.resultObject | vendor text | VERIFIED (text); Suno shapes not exercised live |
| 9 | recordInfo limit 10 requests per second per taskId; createTask 20 per 10 seconds | vendor text | VERIFIED (text) |
| 10 | Upload host https://kieai.redpandaai.co with base64 (10 MB or less), stream (multipart), url (30 s fetch timeout); uploadPath required with no leading or trailing slash; result data.downloadUrl | vendor text, live probe | VERIFIED |
| 11 | Uploaded files are deleted after 24 hours | vendor reference says 24 hours; skill 07 notes say 3 days | CONTRADICTED. Adapter honors expiresAt if returned, else assumes 24 hours. |
| 12 | Generated media kept 14 days | vendor text says 14 days; KIE task-detail page says result URLs typically expire after 24 hours (page URL not recorded) | CONTRADICTED. Adapter saves immediately. |
| 13 | POST /api/v1/common/download-url {url} returns a bare string URL valid 20 minutes, KIE-hosted URLs only (else 422) | vendor text, live probe | VERIFIED |
| 14 | GET /api/v1/chat/credit returns data as a number | vendor text, live probe | VERIFIED |
| 15 | Dead endpoints: /api/v1/account/balance, /api/v1/user/credits, /api/v1/jobs/create, /api/v1/veo/task | live probe, each 404 | VERIFIED dead |
| 16 | Auth is Authorization: Bearer; a header named apikey returns 401 | live probe | VERIFIED |
| 17 | Vendor kie-models is instruction-only (no scripts) | install inspection; tree hash 3871a627...09ac | VERIFIED |
| 18 | KIE troubleshooting page content | https://docs.kie.ai/ai-agent/troubleshooting.md loads; table covers 401, key missing, PowerShell curl, jq missing, failed task, not enough credits, link expired | VERIFIED 2026-10-09 (page loads; row closed) |
| 19 | Live free-call and one-paid-job smoke from this build | KIE_API_KEY NOT-SET in the build environment | PENDING (not run; see QC.md) |
| 20 | Vendor drift probe | scripts/vendor_skill_probe.sh run once | VERIFIED: MATCH on 2026-10-05 |

2026-10-09 re-check: both archive digests match the approval (kie-models f6247b73..., kie-chat-agents f1cbf185...). The official agent pages were re-fetched the same day and digested at `07-kie-setup/references/kie-official-agent-docs-digest.md`.

Live smoke outputs: none recorded (PENDING). When run, append the printed lines of `bash scripts/live_smoke.sh --paid` here (they never contain key material).

## v1.1.0 live evidence (2026-10-05, operator box, key presence SET via shared-utils key_resolver, no key material recorded)

- Registry built from the live API: 218 catalog models, 217 with a readable schema (1 `openapi: null`: google/gemini-3-8-flash-tts), 178 createTask and 39 synchronous, 155 with a prompt field (141 with a known max), 14 with verbatim fields, 199 with a parsed credit price. Catalog once, one schema call per model, spaced 1.1 seconds by the adapter.
- `latest-family --family gpt-image` (live): 2.5 generation, variants flare and sunburst both eligible; chosen sunburst by variant-match; routes gpt-image-2-5-sunburst-text-to-image and gpt-image-2-5-sunburst-image-to-image; changed false.
- Paid smoke (exactly one, `run --mode active`, gpt-image-2-5-sunburst-text-to-image, 1K, 1:1): prompt 19,387 characters = 96.9 percent of maxLength 20,000 (prompt-budget exit 0, status OK; floor 16,000, target 19,000 to 20,000). validate: validated. preflight: estimate 16.0, required 20.8, ok.
  - task_id aaff13916b2be113fc4abf6b1787e9a1, state success, credits_consumed 6.0.
  - credits balance before 3043.03, after 3037.03 (difference 6.00, equal to the reported credits_consumed 6.0).
  - saved file: valid PNG, 1254 x 1254, 2,287,284 bytes, IEND present.
