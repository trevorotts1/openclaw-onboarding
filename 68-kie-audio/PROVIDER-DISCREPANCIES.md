# PROVIDER-DISCREPANCIES.md — Skill 68 (kie-audio)

Maintained per directive §9.2 item 7. Rule: contradictory official examples are
recorded here, never turned into passing fixtures. Source: W0-02 contract
(`planning/provider-contracts.md` §§2/§4, live docs + registry fetched 2026-10-06).

## 1. V4 example vs V6 text (generate-music)

The generate-music page's code example sets the version to `V4` while the page
schema defaults to `V6` and the surrounding text marks `V4`–`V5_5`
Discontinued. The example is stale, not a passing fixture. The validator
accepts `V4`–`V5_5` with a Discontinued warning and defaults missing
`input.model` to `V6`.

## 2. Sounds body code 422 inside HTTP 200

The sounds page pairs a success message with body code `422` in its enum
(`200, 401, 402, 404, 422, 429, 433, 455, 500, 501, 505`) while the HTTP status
stays 200. Real status lives in the JSON body `code`. Always validate the body
code, the result state, and the artifact — never the HTTP status alone.

## 3. Task-detail URLs 404 (record path UNVERIFIED)

`https://docs.kie.ai/suno-api/get-task-detail` and
`https://docs.kie.ai/suno-api/query-task-detail` both returned HTTP 404 on
2026-10-06. The generate-music content names a "Get Task Details endpoint" /
"Get Music Details endpoint" with no exact path quoted. No verified
recordInfo/task-detail path exists from fetched docs content. Poll/recordInfo
wording in this skill stays generic until an authorized live smoke proves a
path and records request digest, model, task ID, callback/poll outcome, and
downloaded artifact checksum.
