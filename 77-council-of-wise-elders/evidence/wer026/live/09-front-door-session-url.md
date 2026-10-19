Proof C — real loopback session URL from the standalone front door
===================================================================
Captured 2026-10-18T23:26:20Z.

The front door is the canonical `runtime/src/service/front-door.ts` contract
(`CouncilFrontDoor`), started once from the pinned install. The repository ships
no `service` CLI subcommand, so a 30-line driver in the lane imports the built
`dist/service/index.js` and does exactly what the contract defines:
start → read the returned session URL → stop. The driver is in the lane
(`front-door-driver.mjs`), not in the repository.

Commands and exit codes
-----------------------
node front-door-driver.mjs <receipt> sess-w15u001-live        driver exit 0
curl -s -o ... -w 'http_status=%{http_code}' http://127.0.0.1:8787/healthz
  → http_status=200
curl -s -o ... -w 'http_status=%{http_code} url_effective=%{url_effective}' \
  http://127.0.0.1:8787/council/sess-w15u001-live
  → http_status=200 url_effective=http://127.0.0.1:8787/council/sess-w15u001-live
kill -TERM <driver>  → driver_exit_rc=0
lsof -nP -iTCP:8787 -iTCP:8788 -iTCP:8789 -sTCP:LISTEN → rc=1 (no listener left)

Bind: 127.0.0.1:8787 (first candidate from DEFAULT_SERVICE_PORTS = [8787,8788,8789]);
loopback only; no remote exposure attempted.

TRUE returned session URL (read back from the service, not constructed):
  http://127.0.0.1:8787/council/sess-w15u001-live
Service response to GET /council/sess-w15u001-live: HTTP 200, authority=standalone,
ui=not_bundled (UI_NOT_BUNDLED blocker reported honestly by the slice).

Clean stop: drain() → {drained:true, fenced:true}; stop() → {stopped:true}.

Machine receipt: 10-session-url-receipt.json
