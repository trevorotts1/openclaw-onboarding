// Canonical Council front-door service launcher (host wiring).
//
// Calls the composition root startCouncilService(...), never a bare
// CouncilFrontDoor: the composition root is what binds the durable admission
// sink, the journal event-stream adapter and the repository session reader
// over ONE backend. A bare door leaves those unbound and /events answers 501.
//
// Host-supplied optional deps stay unpassed: materialCatalog (needs an
// installed Skill 22 export) remains honestly null, so readiness reports it
// not-ready. Route limits are always bound (measured or conservative default).
//
// Run (started by the skill's wire.sh from the immutable release under
//        $OPENCLAW_ROOT/council-runtime; nobody hand-runs npm):
//        <node> <release>/node_modules/tsx/dist/cli.mjs <release>/scripts/service-launch.mjs
//        (tsx is installed inside the release; it is required: the launcher imports src/, and the tsc output in
//        dist/ uses extensionless imports that plain node cannot load)
// Env (all optional):
//   COUNCIL_SERVICE_DATA_DIR   durable data dir (default: platform default)
//   COUNCIL_SERVICE_PORT       loopback port (default 8787)
//   COUNCIL_TENANT_ID / COUNCIL_COMPANY_ID   identity overrides
// Stdout is one JSON object per line. SIGTERM/SIGINT stop the service.

const env = process.env;
const entry = new URL("../src/service/index.js", import.meta.url).href;

const port = Number(env.COUNCIL_SERVICE_PORT || 8787);
const options = {
  startedAt: new Date().toISOString(),
  host: "127.0.0.1",
  ports: [port],
  // This launcher owns signal handling so shutdown is logged once.
  handleSignals: false,
};
if (env.COUNCIL_SERVICE_DATA_DIR) options.dataDir = env.COUNCIL_SERVICE_DATA_DIR;
if (env.COUNCIL_TENANT_ID) options.tenantId = env.COUNCIL_TENANT_ID;
if (env.COUNCIL_COMPANY_ID) options.companyId = env.COUNCIL_COMPANY_ID;

let service;
try {
  const { startCouncilService } = await import(entry);
  service = await startCouncilService(options);
} catch (error) {
  console.log(JSON.stringify({
    event: "front_door_start_failed",
    error: String(error && error.stack ? error.stack : error),
    pid: process.pid,
  }));
  process.exit(3);
}

const outcome = service.outcome;
console.log(JSON.stringify({
  event: "front_door_started",
  outcome: outcome.outcome,
  origin: outcome.origin,
  port: outcome.port,
  blockers: outcome.blockers,
  dataDir: service.composition.backend.dataDir,
  pid: process.pid,
}));

if (outcome.outcome === "refused") process.exit(3);

const shutdown = async () => {
  try { await service.stop(); } catch { /* already stopped */ }
  console.log(JSON.stringify({ event: "front_door_stopped", pid: process.pid }));
  process.exit(0);
};
process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
setInterval(() => {}, 1 << 30);
