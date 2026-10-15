#!/usr/bin/env node
// CWE-041 fixture driver: drives the REAL council runtime (an
// isolated copy of the accepted skill tree, installed with the
// product installer) through the lifecycle, stale-writer, authority,
// and checkpoint scenarios the CWE-041 batteries assert on. Nothing
// here reimplements product logic: sessions run through CouncilEngine
// + createLocalHost + the product's own DeterministicFixtureTransport
// (which spends nothing), and the canonical store scenarios run
// through CouncilStoreService from the same tree.
//
// The driver loads the runtime sources through tsx, which is how the
// product's own test suite runs them (the tsc output uses bundler
// resolution and is packaged by esbuild into the CLI bundle).
//
// Usage: node --import tsx runtime-driver.mjs <job.json>
// The job file names the op and its inputs. Exactly one line is
// printed on stdout: "CWE041_RESULT <json>". The gated-start op
// additionally writes a mid-flight snapshot file and then stays
// blocked inside the gated transport until the battery kills the
// process (the rollback scenario: the old process dies mid-flight).
//
// Required env: CWE041_SRC_DIR = absolute path to runtime/src of the
// isolated tree copy. CWD must be the copy's runtime/ directory so
// --import tsx resolves.

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const srcDir = process.env.CWE041_SRC_DIR;
if (!srcDir) {
  console.log("CWE041_RESULT " + JSON.stringify({ ok: false, error: "CWE041_SRC_DIR not set" }));
  process.exit(2);
}
const imp = (rel) => import(pathToFileURL(join(srcDir, rel)).href);

const core = await imp("index.ts");
const { CouncilStoreService } = await imp("persistence/store.ts");
const { envelopeFromScope } = await imp("persistence/envelope.ts");
const { DEFAULT_PERSISTENCE_CONFIG } = await imp("persistence/config.ts");
const { ensureInstallationProfile, readInstallationProfile } = await imp(
  "persistence/profile.ts",
);
const { validateSessionStateRecord } = core;

const {
  CouncilEngine,
  createLocalHost,
  buildSampleSession,
  DeterministicFixtureTransport,
  canonicalHash,
  CONTRACT_PACKAGE_VERSION,
} = core;

// ------------------------------------------------------------ transports

class CountingTransport {
  constructor(inner) {
    this.inner = inner;
    this.calls = 0;
  }
  async generate(request) {
    this.calls += 1;
    return this.inner.generate(request);
  }
}

class GatedTransport extends CountingTransport {
  constructor(inner, allowCalls, onGate) {
    super(inner);
    this.allowCalls = allowCalls;
    this.onGate = onGate;
    this.gated = false;
  }
  async generate(request) {
    this.calls += 1;
    if (this.calls > this.allowCalls) {
      if (!this.gated) {
        this.gated = true;
        await this.onGate();
      }
      // Blocked mid-flight: this promise never settles. The battery
      // kills the process here, which is the rollback event.
      await new Promise(() => {});
    }
    return this.inner.generate(request);
  }
}

// ------------------------------------------------------------ host setup

function testGrant(spec, scope) {
  // Mirrors runtime/tests/helpers.ts buildTestGrant (the accepted test
  // pattern): a fixture-only grant so the engine's real admission checks
  // run end to end.
  return {
    schema_version: "wise-elders.run-grant/v1",
    grant_id: "grant-cwe041-fixture",
    authority_mode: "local_interactive_owner",
    issuer_principal: "local-owner",
    scope: { ...scope },
    purpose: "council_run",
    session_id: spec.session_id,
    brief_revision: spec.brief_revision,
    brief_sha256: spec.brief_sha256,
    mode: spec.mode,
    seat_ids: [...spec.seat_ids],
    route_policy_sha256: canonicalHash({ policy: "cwe041-fixture-route-policy" }),
    account_ref: null,
    pack_version: spec.source_pack_version,
    protocol_version: CONTRACT_PACKAGE_VERSION,
    allowed_operation_kinds: ["provider_request"],
    ceilings: {
      max_provider_requests: 50,
      max_output_repairs: 9,
      max_transport_retries: 8,
      max_input_tokens: null,
      max_output_tokens: null,
      max_money: null,
    },
    created_at: "2026-01-01T00:00:00Z",
    expires_at: "2099-01-01T00:00:00Z",
    revocation_epoch: 0,
    status: "active",
    standing_parent_grant_id: null,
    preview_sha256: canonicalHash({ preview: "cwe041-fixture" }),
    consumed: { provider_requests: 0, output_repairs: 0, transport_retries: 0 },
    reserved: { provider_requests: 0, output_repairs: 0, transport_retries: 0 },
  };
}

function hostWithGrant(dataDir, session, transport) {
  const { host, store } = createLocalHost({
    dataDir,
    transports: [{ routeId: session.spec.model_policy.route_id, transport }],
  });
  const grant = testGrant(session.spec, session.scope);
  host.authorize = {
    async resolveRunGrant(grantRef, sessionId) {
      return grantRef === "test-grant" && sessionId === session.spec.session_id
        ? grant
        : null;
    },
  };
  return { host, store };
}

function freshSample(sessionId) {
  const sample = buildSampleSession();
  if (!sessionId) return sample;
  const spec = { ...sample.spec, session_id: sessionId };
  const brief = { ...sample.brief, session_id: sessionId };
  spec.brief_sha256 = canonicalHash(brief);
  return { spec, brief, scope: sample.scope };
}

function summarize(session, events, verdict, extra = {}) {
  return {
    session_id: session.spec.session_id,
    state: session.state.state,
    state_version: session.state.state_version,
    resume_phase: session.state.resume_phase,
    event_count: events.length,
    event_sequences: events.map((e) => e.sequence),
    event_types: events.map((e) => e.event_type ?? e.type ?? null),
    verdict_present: Boolean(verdict),
    ...extra,
  };
}

function errInfo(err) {
  return {
    name: err?.name ?? "Error",
    code: err?.code ?? null,
    message: err instanceof Error ? err.message : String(err),
  };
}

// ------------------------------------------------------------ ops

async function opLifecycle(job) {
  const transport = new CountingTransport(new DeterministicFixtureTransport());
  const sample = freshSample(job.sessionId);
  const { host } = createLocalHost({
    dataDir: job.dataDir,
    transports: [{ routeId: sample.spec.model_policy.route_id, transport }],
  });
  const grant = testGrant(sample.spec, sample.scope);
  host.authorize = {
    async resolveRunGrant(grantRef, sessionId) {
      return grantRef === "test-grant" && sessionId === sample.spec.session_id
        ? grant
        : null;
    },
  };
  const engine = new CouncilEngine(host);
  const created = await engine.createSession({ ...sample, sample: true });
  const finished = await engine.startSession(created.spec.session_id, "test-grant");
  const events = await engine.listEvents(finished.spec.session_id);
  const verdict = await engine.getVerdict(finished.spec.session_id);
  const cards = await host.store.listCards(finished.spec.session_id);
  return {
    ok: true,
    ...summarize(finished, events, verdict, { cards_committed: cards.length }),
    transport_calls: transport.calls,
  };
}

async function opGatedStart(job) {
  const sample = freshSample(job.sessionId);
  let engineRef = null;
  let storeRef = null;
  let createdId = null;
  const transport = new GatedTransport(
    new DeterministicFixtureTransport(),
    job.allowCalls,
    async () => {
      const session = await engineRef.getSession(createdId);
      const events = await engineRef.listEvents(createdId);
      const cards = await storeRef.listCards(createdId);
      writeFileSync(
        job.midflightFile,
        JSON.stringify(
          {
            session_id: createdId,
            state: session.state.state,
            state_version: session.state.state_version,
            event_count: events.length,
            last_sequence: events.length ? events[events.length - 1].sequence : 0,
            cards_committed: cards.length,
            transport_calls_before_gate: job.allowCalls,
          },
          null,
          2,
        ),
      );
    },
  );
  const { host, store } = createLocalHost({
    dataDir: job.dataDir,
    transports: [{ routeId: sample.spec.model_policy.route_id, transport }],
  });
  storeRef = store;
  const grant = testGrant(sample.spec, sample.scope);
  host.authorize = {
    async resolveRunGrant(grantRef, sessionId) {
      return grantRef === "test-grant" && sessionId === sample.spec.session_id
        ? grant
        : null;
    },
  };
  const engine = new CouncilEngine(host);
  engineRef = engine;
  const created = await engine.createSession({ ...sample, sample: true });
  createdId = created.spec.session_id;
  // Never settles: the gated transport blocks mid-flight and the
  // battery kills this process (the rollback event).
  await engine.startSession(createdId, "test-grant");
  return { ok: false, error: "gated start unexpectedly completed" };
}

async function opInspect(job) {
  const { host } = createLocalHost({ dataDir: job.dataDir });
  const engine = new CouncilEngine(host);
  const session = await engine.getSession(job.sessionId);
  if (!session) return { ok: false, error: `session ${job.sessionId} not found` };
  const events = await engine.listEvents(job.sessionId);
  const verdict = await engine.getVerdict(job.sessionId);
  const cards = await host.store.listCards(job.sessionId);
  return {
    ok: true,
    ...summarize(session, events, verdict, { cards_committed: cards.length }),
  };
}

async function opPause(job) {
  const { host } = createLocalHost({ dataDir: job.dataDir });
  const engine = new CouncilEngine(host);
  const paused = await engine.pauseSession(job.sessionId);
  const events = await engine.listEvents(job.sessionId);
  return { ok: true, ...summarize(paused, events, null) };
}

async function opResume(job) {
  const probe = createLocalHost({ dataDir: job.dataDir });
  const probeEngine = new CouncilEngine(probe.host);
  const existing = await probeEngine.getSession(job.sessionId);
  if (!existing) return { ok: false, error: `session ${job.sessionId} not found` };
  probe.store.close();
  const transport = new CountingTransport(new DeterministicFixtureTransport());
  const { host } = hostWithGrant(job.dataDir, existing, transport);
  const engine = new CouncilEngine(host);
  const finished = await engine.resumeSession(job.sessionId, "test-grant");
  const events = await engine.listEvents(job.sessionId);
  const verdict = await engine.getVerdict(job.sessionId);
  return {
    ok: true,
    ...summarize(finished, events, verdict),
    transport_calls: transport.calls,
  };
}

async function opStartNoGrant(job) {
  const sample = freshSample(job.sessionId);
  const { host } = createLocalHost({ dataDir: job.dataDir });
  host.authorize = { async resolveRunGrant() { return null; } };
  const engine = new CouncilEngine(host);
  const created = await engine.createSession({ ...sample, sample: true });
  let startError = null;
  try {
    await engine.startSession(created.spec.session_id, "no-such-grant");
  } catch (err) {
    startError = errInfo(err);
  }
  const after = await engine.getSession(created.spec.session_id);
  const events = await engine.listEvents(created.spec.session_id);
  return {
    ok: true,
    start_error: startError,
    state_after_refusal: after.state.state,
    state_version_after_refusal: after.state.state_version,
    event_count: events.length,
  };
}

async function opStaleWorkerLocal(job) {
  // The standalone store the CLI composes (LocalSqliteStore): state
  // writes are compare-and-swap on state_version.
  const { store } = createLocalHost({ dataDir: job.dataDir });
  const sample = freshSample(job.sessionId);
  const stateV0 = {
    schema_version: "wise-elders.session-state/v1",
    session_id: sample.spec.session_id,
    mode: sample.spec.mode,
    state: "DRAFT",
    state_version: 0,
    brief_revision: sample.brief.revision,
    resume_phase: null,
    cancel_generation: 0,
    revocation_generation: 0,
    attempt: 1,
    lease_epoch: 0,
    archived: false,
    updated_at: sample.spec.created_at,
  };
  await store.createSession({
    spec: sample.spec,
    brief: sample.brief,
    scope: sample.scope,
    state: stateV0,
    sample: false,
  });
  // The current (post-upgrade) worker advances the session to v1.
  const stateV1 = { ...stateV0, state: "READY", state_version: 1 };
  await store.updateState(stateV1, 0);
  const advanced = await store.getSession(sample.spec.session_id);
  // A stale worker from the pre-upgrade core still holds the v0 record
  // and tries to write its incompatible output (a forged CANCELLED)
  // into the newer session.
  const forged = { ...stateV0, state: "CANCELLED" };
  let staleError = null;
  try {
    await store.updateState(forged, 0);
  } catch (err) {
    staleError = errInfo(err);
  }
  const after = await store.getSession(sample.spec.session_id);
  store.close();
  return {
    ok: true,
    stale_error: staleError,
    state_after: after.state.state,
    state_version_after: after.state.state_version,
    record_unchanged: JSON.stringify(after.state) === JSON.stringify(advanced.state),
  };
}

const fixedClock = { nowUtc: () => "2026-10-15T12:00:00Z" };
let idCounter = 0;
const fixedIds = { newId: () => `cwe041-id-${(idCounter += 1).toString().padStart(4, "0")}` };

function sampleStored(sessionId) {
  const sample = freshSample(sessionId);
  return {
    ...sample,
    state: {
      schema_version: "wise-elders.session-state/v1",
      session_id: sample.spec.session_id,
      mode: sample.spec.mode,
      state: "DRAFT",
      state_version: 0,
      brief_revision: sample.brief.revision,
      resume_phase: null,
      cancel_generation: 0,
      revocation_generation: 0,
      attempt: 1,
      lease_epoch: 0,
      archived: false,
      updated_at: sample.spec.created_at,
    },
    sample: false,
  };
}

async function opStaleWorkerCanonical(job) {
  const stored = sampleStored(job.sessionId);
  const envelope = envelopeFromScope(stored.scope, "owner-1", "owner", "write");
  const service = CouncilStoreService.open({
    dataDir: job.dataDir,
    clock: fixedClock,
    ids: fixedIds,
    envelope,
  });
  try {
    await service.createSession(stored);
    const v1 = { ...stored.state, state: "READY", state_version: 1 };
    await service.updateState(v1, 0);
    const advanced = await service.getSession(stored.spec.session_id);
    // Stale worker envelope: same session, pre-upgrade view (v0).
    const forged = { ...stored.state, state: "CANCELLED" };
    let staleError = null;
    try {
      await service.updateState(forged, 0);
    } catch (err) {
      staleError = errInfo(err);
    }
    const after = await service.getSession(stored.spec.session_id);
    const chains = service.verifyAllChains();
    // Contract surface: a pre-upgrade worker's session-state output
    // stamped with an old schema version is refused by validation.
    const badRecord = { ...stored.state, schema_version: "wise-elders.session-state/v0" };
    const badValidation = validateSessionStateRecord(badRecord);
    const goodValidation = validateSessionStateRecord(stored.state);
    return {
      ok: true,
      stale_error: staleError,
      state_after: after.state.state,
      state_version_after: after.state.state_version,
      record_unchanged: JSON.stringify(after.state) === JSON.stringify(advanced.state),
      chains,
      bad_schema_validation: {
        ok: badValidation.ok,
        issues: (badValidation.issues ?? []).map((i) => `${i.path}: ${i.message}`),
      },
      good_schema_validation: { ok: goodValidation.ok },
    };
  } finally {
    service.close();
  }
}

async function opAuthority(job) {
  const results = {};
  // Record a standalone profile (the installer's choice at setup).
  const profile = ensureInstallationProfile(job.dataDir, {
    authority_mode: "standalone",
    authority_ref: null,
    installation_id: "cwe041-fixture-installation",
    recorded_at: "2026-10-15T12:00:00Z",
  });
  results.recorded_profile = {
    authority_mode: profile.authority_mode,
    schema_version: profile.schema_version,
    config_schema_version: profile.config_schema_version,
  };
  // A managed-mode caller now tries to open the same data directory:
  // the profile check must refuse before any database is opened.
  const stored = sampleStored(job.sessionId);
  const envelope = envelopeFromScope(stored.scope, "owner-1", "owner", "write");
  let managedOpenError = null;
  try {
    const svc = CouncilStoreService.open({
      dataDir: job.dataDir,
      clock: fixedClock,
      ids: fixedIds,
      envelope,
      config: { ...DEFAULT_PERSISTENCE_CONFIG, authority_mode: "managed" },
    });
    svc.close();
  } catch (err) {
    managedOpenError = errInfo(err);
  }
  results.managed_open_error = managedOpenError;
  results.profile_after_refusal = readInstallationProfile(job.dataDir);
  // Reverse direction: a managed profile opened by the standalone
  // composition refuses rather than opening a second, divergent store.
  const dir2 = job.dataDirManaged;
  ensureInstallationProfile(dir2, {
    authority_mode: "managed",
    authority_ref: "cc-authority-fixture",
    installation_id: "cwe041-fixture-installation-2",
    recorded_at: "2026-10-15T12:00:00Z",
  });
  let standaloneOpenError = null;
  try {
    const svc = CouncilStoreService.open({
      dataDir: dir2,
      clock: fixedClock,
      ids: fixedIds,
      envelope,
      config: { ...DEFAULT_PERSISTENCE_CONFIG, authority_mode: "standalone" },
    });
    svc.close();
  } catch (err) {
    standaloneOpenError = errInfo(err);
  }
  results.standalone_open_error = standaloneOpenError;
  let managedProfileOpenError = null;
  try {
    const svc = CouncilStoreService.open({
      dataDir: dir2,
      clock: fixedClock,
      ids: fixedIds,
      envelope,
      config: { ...DEFAULT_PERSISTENCE_CONFIG, authority_mode: "managed" },
    });
    svc.close();
  } catch (err) {
    managedProfileOpenError = errInfo(err);
  }
  results.managed_profile_via_service_error = managedProfileOpenError;
  return { ok: true, ...results };
}

async function opCli(job) {
  const out = [];
  const err = [];
  const io = {
    out: (s) => out.push(s),
    err: (s) => err.push(s),
  };
  const exit = await core.runCli(job.args, io);
  return { ok: true, exit, stdout: out.join(""), stderr: err.join("") };
}

// ------------------------------------------------------------ main

const job = JSON.parse(readFileSync(process.argv[2], "utf8"));
const ops = {
  lifecycle: opLifecycle,
  "gated-start": opGatedStart,
  inspect: opInspect,
  pause: opPause,
  resume: opResume,
  "start-nogrant": opStartNoGrant,
  "stale-worker-local": opStaleWorkerLocal,
  "stale-worker-canonical": opStaleWorkerCanonical,
  authority: opAuthority,
  cli: opCli,
};
try {
  const fn = ops[job.op];
  if (!fn) throw new Error(`unknown op ${job.op}`);
  const result = await fn(job);
  console.log("CWE041_RESULT " + JSON.stringify(result));
} catch (err) {
  console.log(
    "CWE041_RESULT " + JSON.stringify({ ok: false, error: errInfo(err) }),
  );
  process.exit(1);
}
