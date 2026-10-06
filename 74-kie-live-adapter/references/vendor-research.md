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
| 18 | KIE troubleshooting page content | page did not render | UNRESOLVED |
| 19 | Live free-call and one-paid-job smoke from this build | KIE_API_KEY NOT-SET in the build environment | PENDING (not run; see QC.md) |
| 20 | Vendor drift canary | scripts/vendor_skill_probe.sh run once | VERIFIED: MATCH on 2026-10-05 |

Live smoke outputs: none recorded (PENDING). When run, append the printed lines of `bash scripts/live_smoke.sh --paid` here (they never contain key material).
