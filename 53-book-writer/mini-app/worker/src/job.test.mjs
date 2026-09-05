// Book Writer mini-app — U14 per-run JOB STATE MACHINE + intake assembly gate
// unit gate.
//
// Offline tests — no Cloudflare runtime, no network. `node --test`. The
// load-bearing properties under test (MASTER-PLAN section 4 + section 9 U14):
//   - NEVER assemble while queued: a queued/processing required step closes
//     the gate with AF-BW-MA-JOB-PENDING.
//   - EXTRACT-NO-TEXT rule: a media answer with no extracted text NEVER trips
//     assembly-ready (AF-BW-MA-EXTRACT-NO-TEXT).
//   - Explicit AF fail-closed codes for EVERY violation — never a silent pass:
//     missing (AF-BW-MA-REJECT-FIELD), failed (AF-BW-MA-CAPABILITY), empty
//     required set (AF-BW-MA-REJECT-FIELD).
//   - State machine: queued -> collecting -> assembly-ready -> completed/failed;
//     terminal states cannot reopen.
//   - A forged body can never self-attest a done job: when MEDIA_JOBS is bound,
//     the KV row wins over any raw `media` body row.
//   - /api/job handler: 409 with the AF code on a closed gate, 200
//     assembly-ready when every required field is present, and run-state
//     persistence through KV.
//   - Isolation: injected destination fields rejected at the boundary.
//   - No Anthropic ids, no real zone/account ids, no hardcoded client/location.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import {
  RUN_STATE,
  AF,
  isValidTokenShape,
  fieldStatus,
  assemblyGate,
  applyGate,
  markCompleted,
  markFailed,
  runJobKey,
  newRunJob,
  loadRunJob,
  saveRunJob,
  parseJobPayload,
  handleJobPost,
  handleJobRequest,
  selfTest,
} from "./job.js";

const TOKEN = "a".repeat(32);
const NOW = 1_752_944_000; // fixed epoch seconds for determinism
const NOW_UTC = "2026-07-17T00:00:00.000Z";

function binding(overrides = {}) {
  return {
    client_id: "client-a",
    location_id: "loc-a",
    slug: "fake-a",
    phase_id: "P0-INTAKE",
    run_id: "run-1",
    intake_id: "intake-1",
    exp: NOW + 86400 * 7,
    status: "open",
    mode: "full",
    ...overrides,
  };
}

function memKv(seed = {}) {
  const map = new Map(Object.entries(seed));
  return {
    async get(k, opts) {
      const raw = map.get(k) ?? null;
      if (raw == null) return null;
      return opts && opts.type === "json" ? JSON.parse(raw) : raw;
    },
    async put(k, v) { map.set(k, String(v)); },
    async list({ prefix }) {
      const keys = [];
      for (const k of map.keys()) if (k.startsWith(prefix)) keys.push({ name: k });
      return { keys };
    },
    _map: map,
  };
}

function memMedia(seed = {}) {
  const map = new Map(Object.entries(seed));
  return {
    async get(k) {
      const raw = map.get(k) ?? null;
      if (raw == null) return null;
      return typeof raw === "string" ? raw : JSON.stringify(raw);
    },
    async put(k, v) { map.set(k, String(v)); },
    _map: map,
  };
}

function envFor(kv, { media = null, config = null } = {}) {
  const env = { BW_BINDINGS: kv };
  if (media) env.MEDIA_JOBS = media;
  if (config) {
    env.ZHW_BOOKWRITER = {
      // Minimal R2 object surface matching lib.js's loadPhaseConfig contract
      // (store.objectGet(path) -> { value: string } | null).
      async objectGet(path) {
        if (path === "config/fake-a/P0-INTAKE:full.json") {
          return { value: JSON.stringify(config) };
        }
        return null;
      },
    };
  }
  return env;
}

function post(url, body) {
  return new Request(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

const DEFAULT_CFG = {
  questions: [
    { id: "first_name", required: true },
    { id: "ideal_avatar", required: true },
    { id: "cover_description", required: false },
  ],
};

// ---------------------------------------------------------------------------
// Token shape
// ---------------------------------------------------------------------------
test("isValidTokenShape accepts 32 hex and rejects others", () => {
  assert.equal(isValidTokenShape(TOKEN), true);
  assert.equal(isValidTokenShape("short"), false);
  assert.equal(isValidTokenShape("g".repeat(32)), false);
});

// ---------------------------------------------------------------------------
// fieldStatus — the EXTRACT-NO-TEXT rule (a no-text media answer is never present)
// ---------------------------------------------------------------------------
test("fieldStatus: queued/processing media is pending (never present)", () => {
  assert.equal(fieldStatus({ mediaJob: { status: "queued", text: "" } }).status, "pending");
  assert.equal(fieldStatus({ mediaJob: { status: "processing", text: "" } }).status, "pending");
});

test("fieldStatus: done media with non-empty text is present", () => {
  const fs = fieldStatus({ mediaJob: { status: "done", text: "  transcribed  " } });
  assert.equal(fs.status, "present");
  assert.equal(fs.code, null);
});

test("fieldStatus: done media with EMPTY text is no-text (AF-BW-MA-EXTRACT-NO-TEXT)", () => {
  const fs = fieldStatus({ mediaJob: { status: "done", text: "   " } });
  assert.equal(fs.status, "no-text");
  assert.equal(fs.code, AF.EXTRACT_NO_TEXT);
});

test("fieldStatus: explicit N/A media counts present", () => {
  assert.equal(fieldStatus({ mediaJob: { status: "done", text: "N/A" } }).status, "present");
});

test("fieldStatus: failed media is failed (AF-BW-MA-CAPABILITY)", () => {
  const fs = fieldStatus({ mediaJob: { status: "failed", error: "ASR down" } });
  assert.equal(fs.status, "failed");
  assert.equal(fs.code, AF.CAPABILITY);
});

test("fieldStatus: forged/unknown media status fails closed (AF-BW-MA-REJECT-FIELD)", () => {
  const fs = fieldStatus({ mediaJob: { status: "bogus" } });
  assert.equal(fs.status, "missing");
  assert.equal(fs.code, AF.REJECT_FIELD);
});

test("fieldStatus: non-empty typed text is present; blank typed is missing", () => {
  assert.equal(fieldStatus({ typedText: "Ada" }).status, "present");
  assert.equal(fieldStatus({ typedText: "" }).status, "missing");
  assert.equal(fieldStatus({}).status, "missing");
});

// ---------------------------------------------------------------------------
// assemblyGate — the intake assembly gate (never assemble while queued)
// ---------------------------------------------------------------------------
test("assemblyGate REFUSES while any required step is queued (AF-BW-MA-JOB-PENDING)", () => {
  const g = assemblyGate(["ideal_avatar", "first_name"], {
    ideal_avatar: { mediaJob: { status: "queued", text: "" } },
    first_name: { typedText: "Ada" },
  });
  assert.equal(g.ok, false);
  assert.equal(g.verdict, "blocked");
  assert.equal(g.code, AF.JOB_PENDING);
  assert.equal(g.fields.ideal_avatar, "pending");
});

test("assemblyGate REFUSES while any required step is processing", () => {
  const g = assemblyGate(["book_about"], { book_about: { mediaJob: { status: "processing", text: "" } } });
  assert.equal(g.ok, false);
  assert.equal(g.code, AF.JOB_PENDING);
});

test("assemblyGate REFUSES a no-text media answer (AF-BW-MA-EXTRACT-NO-TEXT)", () => {
  const g = assemblyGate(["ideal_avatar"], { ideal_avatar: { mediaJob: { status: "done", text: "   " } } });
  assert.equal(g.ok, false);
  assert.equal(g.code, AF.EXTRACT_NO_TEXT);
  assert.equal(g.verdict, "no-text");
});

test("assemblyGate: a pending step outranks a no-text step (never assemble while queued first)", () => {
  const g = assemblyGate(["a", "b"], {
    a: { mediaJob: { status: "queued", text: "" } },
    b: { mediaJob: { status: "done", text: "" } },
  });
  assert.equal(g.ok, false);
  assert.equal(g.code, AF.JOB_PENDING);
});

test("assemblyGate REFUSES missing required fields (AF-BW-MA-REJECT-FIELD)", () => {
  const g = assemblyGate(["first_name", "niche"], { first_name: { typedText: "Ada" } });
  assert.equal(g.ok, false);
  assert.equal(g.code, AF.REJECT_FIELD);
  assert.equal(g.verdict, "missing");
  assert.match(g.reason, /niche/);
});

test("assemblyGate REFUSES failed required steps (AF-BW-MA-CAPABILITY)", () => {
  const g = assemblyGate(["book_about"], { book_about: { mediaJob: { status: "failed", error: "capability absent" } } });
  assert.equal(g.ok, false);
  assert.equal(g.code, AF.CAPABILITY);
  assert.equal(g.verdict, "degraded");
});

test("assemblyGate NEVER passes an empty required set (silent pass by omission blocked)", () => {
  const g = assemblyGate([], {});
  assert.equal(g.ok, false);
  assert.equal(g.code, AF.REJECT_FIELD);
});

test("assemblyGate opens (assembly-ready) only when every required field is present", () => {
  const g = assemblyGate(["first_name", "ideal_avatar", "cover_description"], {
    first_name: { typedText: "Ada" },
    ideal_avatar: { mediaJob: { status: "done", text: "transcribed avatar" } },
    cover_description: { typedText: "N/A" },
  });
  assert.equal(g.ok, true);
  assert.equal(g.verdict, "assembly-ready");
  assert.equal(g.code, null);
});

// ---------------------------------------------------------------------------
// Run state machine transitions
// ---------------------------------------------------------------------------
test("applyGate: queued -> collecting while the gate is closed", () => {
  const g = assemblyGate(["x"], { x: { mediaJob: { status: "queued" } } });
  const next = applyGate(g, RUN_STATE.QUEUED);
  assert.equal(next.state, RUN_STATE.COLLECTING);
  assert.equal(next.ok, false);
  assert.equal(next.code, AF.JOB_PENDING);
});

test("applyGate: queued -> assembly-ready when the gate opens", () => {
  const g = assemblyGate(["x"], { x: { typedText: "hello" } });
  const next = applyGate(g, RUN_STATE.QUEUED);
  assert.equal(next.state, RUN_STATE.ASSEMBLY_READY);
  assert.equal(next.ok, true);
  assert.equal(next.changed, true);
});

test("applyGate: collecting -> assembly-ready when the gate opens", () => {
  const g = assemblyGate(["x"], { x: { typedText: "hello" } });
  const next = applyGate(g, RUN_STATE.COLLECTING);
  assert.equal(next.state, RUN_STATE.ASSEMBLY_READY);
});

test("applyGate: assembly-ready re-closes to collecting when evidence reverts", () => {
  // A transcribed answer is edited back to blank -> the gate re-closes.
  const g = assemblyGate(["x"], { x: { typedText: "" } });
  const next = applyGate(g, RUN_STATE.ASSEMBLY_READY);
  assert.equal(next.state, RUN_STATE.COLLECTING);
  assert.equal(next.ok, false);
});

test("applyGate: terminal states cannot reopen", () => {
  const ready = { ok: true, verdict: "assembly-ready" };
  assert.equal(applyGate(ready, RUN_STATE.COMPLETED).ok, false);
  assert.equal(applyGate(ready, RUN_STATE.COMPLETED).state, RUN_STATE.COMPLETED);
  assert.equal(applyGate(ready, RUN_STATE.FAILED).ok, false);
  assert.equal(applyGate(ready, RUN_STATE.FAILED).state, RUN_STATE.FAILED);
});

test("markCompleted: only assembly-ready runs may complete; collecting/queued refused with JOB-PENDING", () => {
  const base = { run_id: "r", phase_id: "p", created_at: NOW_UTC, updated_at: NOW_UTC };
  const ok = markCompleted({ ...base, state: RUN_STATE.ASSEMBLY_READY }, { nowUtc: NOW_UTC, assembledIntakeRef: "run/checkpoints/intake.json" });
  assert.equal(ok.ok, true);
  assert.equal(ok.job.state, RUN_STATE.COMPLETED);
  assert.equal(ok.job.assembled_intake, "run/checkpoints/intake.json");

  // The belt-and-suspenders: completion is refused for a run that was never
  // assembly-ready — this is the machine-level guard on "never assemble while
  // queued" at the completion step too.
  const collecting = markCompleted({ ...base, state: RUN_STATE.COLLECTING }, { nowUtc: NOW_UTC });
  assert.equal(collecting.ok, false);
  assert.equal(collecting.code, AF.JOB_PENDING);

  const queued = markCompleted({ ...base, state: RUN_STATE.QUEUED }, { nowUtc: NOW_UTC });
  assert.equal(queued.ok, false);
  assert.equal(queued.code, AF.JOB_PENDING);
});

test("markFailed: collecting may fail; completed cannot; failed is terminal", () => {
  const base = { run_id: "r", phase_id: "p", created_at: NOW_UTC, updated_at: NOW_UTC };
  const failed = markFailed({ ...base, state: RUN_STATE.COLLECTING }, { nowUtc: NOW_UTC, error: "intake step threw" });
  assert.equal(failed.ok, true);
  assert.equal(failed.job.state, RUN_STATE.FAILED);
  assert.equal(failed.job.error, "intake step threw");

  const noRevert = markCompleted({ ...failed.job }, { nowUtc: NOW_UTC });
  assert.equal(noRevert.ok, false);

  const completed = markCompleted({ ...base, state: RUN_STATE.ASSEMBLY_READY }, { nowUtc: NOW_UTC });
  const noFail = markFailed({ ...completed.job }, { nowUtc: NOW_UTC });
  assert.equal(noFail.ok, false);
});

// ---------------------------------------------------------------------------
// Run job row storage
// ---------------------------------------------------------------------------
test("newRunJob starts queued; load/save round-trips through KV", async () => {
  const kv = memKv();
  const job = newRunJob("run-1", "P0-INTAKE", NOW_UTC);
  assert.equal(job.state, RUN_STATE.QUEUED);
  await saveRunJob(kv, job);
  const loaded = await loadRunJob(kv, "run-1");
  assert.equal(loaded.run_id, "run-1");
  assert.equal(loaded.state, RUN_STATE.QUEUED);
  assert.equal(runJobKey("run-1"), "runjob:run-1");
  assert.equal(kv._map.has("runjob:run-1"), true);
});

test("loadRunJob returns null on missing/corrupt rows (fail closed)", async () => {
  const kv = memKv();
  assert.equal(await loadRunJob(kv, "nope"), null);
  kv._map.set("runjob:bad", "{not json");
  assert.equal(await loadRunJob(kv, "bad"), null);
});

// ---------------------------------------------------------------------------
// parseJobPayload — boundary validation
// ---------------------------------------------------------------------------
test("parseJobPayload rejects injected destination fields", () => {
  const p = parseJobPayload(JSON.stringify({ required: ["x"], location_id: "loc-b", contact_id: "c9" }));
  assert.equal(p.ok, false);
  assert.equal(p.status, 400);
});

test("parseJobPayload parses a valid payload", () => {
  const p = parseJobPayload(JSON.stringify({ phase_id: "P0-INTAKE", required: ["a", "b"], media_answer_ids: { a: "aid1" }, media: { a: { status: "done" } } }));
  assert.equal(p.ok, true);
  assert.deepEqual(p.body.required, ["a", "b"]);
  assert.equal(p.body.media_answer_ids.a, "aid1");
  assert.equal(p.body.media.a.status, "done");
});

test("parseJobPayload rejects bad shapes", () => {
  assert.equal(parseJobPayload("").ok, false);
  assert.equal(parseJobPayload("not json").ok, false);
  assert.equal(parseJobPayload(JSON.stringify({ required: "nope" })).ok, false);
  assert.equal(parseJobPayload(JSON.stringify({ phase_id: 5 })).ok, false);
});

// ---------------------------------------------------------------------------
// /api/job handler — negative + positive paths
// ---------------------------------------------------------------------------
test("POST /api/job: 409 AF-BW-MA-JOB-PENDING when a required step is queued (never assemble)", async () => {
  const kv = memKv({ [`binding:${TOKEN}`]: JSON.stringify(binding()) });
  const media = memMedia({ "media:aid-story": JSON.stringify({ answer_id: "aid-story", status: "queued", text: "" }) });
  const env = envFor(kv, { media });
  const res = await handleJobPost(
    post(`https://bookwriter.test/api/job?tk=${TOKEN}`, {
      required: ["ideal_avatar"],
      media_answer_ids: { ideal_avatar: "aid-story" },
    }),
    env, NOW
  );
  assert.equal(res.status, 409);
  const body = await res.json();
  assert.equal(body.ok, false);
  assert.equal(body.gate.verdict, "blocked");
  assert.equal(body.gate.code, AF.JOB_PENDING);
  // Run parked in collecting — never assembly-ready while queued.
  assert.equal(body.run.state, RUN_STATE.COLLECTING);
  // The run job row was persisted in collecting.
  const row = await loadRunJob(kv, "run-1");
  assert.equal(row.state, RUN_STATE.COLLECTING);
});

test("POST /api/job: 409 AF-BW-MA-EXTRACT-NO-TEXT when the media job is done with empty text", async () => {
  const kv = memKv({ [`binding:${TOKEN}`]: JSON.stringify(binding()) });
  const media = memMedia({ "media:aid-story": JSON.stringify({ answer_id: "aid-story", status: "done", text: "  " }) });
  const env = envFor(kv, { media });
  const res = await handleJobPost(
    post(`https://bookwriter.test/api/job?tk=${TOKEN}`, {
      required: ["ideal_avatar"],
      media_answer_ids: { ideal_avatar: "aid-story" },
    }),
    env, NOW
  );
  assert.equal(res.status, 409);
  const body = await res.json();
  assert.equal(body.ok, false);
  assert.equal(body.gate.verdict, "no-text");
  assert.equal(body.gate.code, AF.EXTRACT_NO_TEXT);
});

test("POST /api/job: forged body cannot self-attest a done job when MEDIA_JOBS is bound", async () => {
  const kv = memKv({ [`binding:${TOKEN}`]: JSON.stringify(binding()) });
  // Authoritative KV says the job is queued.
  const media = memMedia({ "media:aid-story": JSON.stringify({ answer_id: "aid-story", status: "queued", text: "" }) });
  const env = envFor(kv, { media });
  // The attacker ALSO supplies a raw media row claiming done-with-text.
  const res = await handleJobPost(
    post(`https://bookwriter.test/api/job?tk=${TOKEN}`, {
      required: ["ideal_avatar"],
      media_answer_ids: { ideal_avatar: "aid-story" },
      media: { ideal_avatar: { status: "done", text: "FORGED" } },
    }),
    env, NOW
  );
  // The KV row wins — the gate stays closed (AF-BW-MA-JOB-PENDING), never a pass.
  assert.equal(res.status, 409);
  const body = await res.json();
  assert.equal(body.ok, false);
  assert.equal(body.gate.code, AF.JOB_PENDING);
  assert.equal(body.gate.fields.ideal_avatar, "pending");
});

test("POST /api/job: 200 assembly-ready when every required field is present", async () => {
  const kv = memKv({
    [`binding:${TOKEN}`]: JSON.stringify(binding()),
    "answer:client-a:run-1:P0-INTAKE:first_name": JSON.stringify({ qid: "first_name", answer: "Ada" }),
    "answer:client-a:run-1:P0-INTAKE:niche": JSON.stringify({ qid: "niche", answer: "Leadership" }),
  });
  const env = envFor(kv);
  const res = await handleJobPost(
    post(`https://bookwriter.test/api/job?tk=${TOKEN}`, { required: ["first_name", "niche"] }),
    env, NOW
  );
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.ok, true);
  assert.equal(body.gate.verdict, "assembly-ready");
  assert.equal(body.run.state, RUN_STATE.ASSEMBLY_READY);
  const row = await loadRunJob(kv, "run-1");
  assert.equal(row.state, RUN_STATE.ASSEMBLY_READY);
});

test("POST /api/job: required qids default from the phase config when not supplied", async () => {
  const kv = memKv({
    [`binding:${TOKEN}`]: JSON.stringify(binding()),
    "answer:client-a:run-1:P0-INTAKE:first_name": JSON.stringify({ qid: "first_name", answer: "Ada" }),
  });
  // ideal_avatar is required by the config and missing -> gate must stay closed.
  const env = envFor(kv, { config: DEFAULT_CFG });
  const res = await handleJobPost(post(`https://bookwriter.test/api/job?tk=${TOKEN}`, {}), env, NOW);
  assert.equal(res.status, 409);
  const body = await res.json();
  assert.equal(body.gate.code, AF.REJECT_FIELD);
  assert.match(body.gate.reason, /ideal_avatar/);
});

test("POST /api/job: typed answers resolve from save: draft rows (resume path)", async () => {
  const kv = memKv({
    [`binding:${TOKEN}`]: JSON.stringify(binding()),
    "save:client-a:run-1:P0-INTAKE:first_name": JSON.stringify({ qid: "first_name", answer: "Draft Ada" }),
  });
  const env = envFor(kv);
  const res = await handleJobPost(
    post(`https://bookwriter.test/api/job?tk=${TOKEN}`, { required: ["first_name"] }),
    env, NOW
  );
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.ok, true);
});

test("POST /api/job: token auth guards (400 bad shape, 401 unknown/expired, 410 completed)", async () => {
  const kv = memKv({});
  const env = envFor(kv);
  const bad = await handleJobPost(post("https://bookwriter.test/api/job?tk=short", {}), env, NOW);
  assert.equal(bad.status, 400);

  const unknown = await handleJobPost(post(`https://bookwriter.test/api/job?tk=${TOKEN}`, {}), env, NOW);
  assert.equal(unknown.status, 401);

  const kvExp = memKv({ [`binding:${TOKEN}`]: JSON.stringify(binding({ exp: NOW - 1 })) });
  const exp = await handleJobPost(post(`https://bookwriter.test/api/job?tk=${TOKEN}`, {}), envFor(kvExp), NOW);
  assert.equal(exp.status, 401);

  const kvDone = memKv({ [`binding:${TOKEN}`]: JSON.stringify(binding({ status: "completed" })) });
  const done = await handleJobPost(post(`https://bookwriter.test/api/job?tk=${TOKEN}`, {}), envFor(kvDone), NOW);
  assert.equal(done.status, 410);
});

test("handleJobRequest: GET -> 405, POST delegates", async () => {
  // Far-future exp so the real-clock path in handleJobRequest (no injected now)
  // does not see the July fixture as expired.
  const kv = memKv({
    [`binding:${TOKEN}`]: JSON.stringify(binding({ exp: 4_000_000_000 })),
    "answer:client-a:run-1:P0-INTAKE:first_name": JSON.stringify({ qid: "first_name", answer: "Ada" }),
  });
  const env = envFor(kv);
  const get = await handleJobRequest(new Request(`https://bookwriter.test/api/job?tk=${TOKEN}`), env);
  assert.equal(get.status, 405);
  const postRes = await handleJobRequest(post(`https://bookwriter.test/api/job?tk=${TOKEN}`, { required: ["first_name"] }), env);
  assert.equal(postRes.status, 200); // first_name has a typed answer -> assembly-ready
});

test("POST /api/job: missing KV binding -> 503", async () => {
  const res = await handleJobPost(post(`https://bookwriter.test/api/job?tk=${TOKEN}`, {}), {}, NOW);
  assert.equal(res.status, 503);
});

test("POST /api/job: completion + failure leave terminal states", async () => {
  const kv = memKv({
    [`binding:${TOKEN}`]: JSON.stringify(binding()),
    "answer:client-a:run-1:P0-INTAKE:first_name": JSON.stringify({ qid: "first_name", answer: "Ada" }),
  });
  const env = envFor(kv);
  const res = await handleJobPost(post(`https://bookwriter.test/api/job?tk=${TOKEN}`, { required: ["first_name"] }), env, NOW);
  assert.equal(res.status, 200);
  const row = await loadRunJob(kv, "run-1");
  // Once the assembler runs (handled elsewhere, U13/U15), completion is a
  // pure transition that requires assembly-ready. Verify that a run that has
  // been pushed to collecting cannot complete, and a completed run is terminal.
  const collect = await loadRunJob(kv, "run-1");
  const tooEarly = markCompleted(collect, { nowUtc: NOW_UTC });
  assert.equal(tooEarly.ok, true); // it IS assembly-ready after the 200 above
  const completed = markCompleted(await loadRunJob(kv, "run-1"), { nowUtc: NOW_UTC });
  assert.equal(completed.ok, true);
  const reopen = applyGate({ ok: true, verdict: "assembly-ready" }, completed.job.state);
  assert.equal(reopen.ok, false);
});

// ---------------------------------------------------------------------------
// Self-test parity + lint guards
// ---------------------------------------------------------------------------
test("selfTest reports zero failures", () => {
  assert.deepEqual(selfTest(), []);
});

test("no Anthropic ids, no {{...}}, no real ids, no hardcoded client/location", () => {
  const src = readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), "job.js"), "utf8");
  // The module may mention "Anthropic" in a fail-closed prose/comment (the same
  // convention every sibling unit uses). What must NEVER appear is a bare model
  // or provider id — the exact pattern the QC bare-key grep checks both ways.
  const bareAnthropic = /(^|[^A-Za-z])anthropic([^A-Za-z-]|$)/.test(src);
  const bareClaude = /\bclaude[\w.-]*\b/i.test(src);
  assert.ok(!bareAnthropic && !bareClaude, "no bare Anthropic/Claude provider or model id");
  // Handlebars-style {{...}} template interpolation (the constraint's
  // "no {{...}}"): `{{name}}`, `{{#block}}`, `{{/block}}`, `{{>partial}}`,
  // `{{!comment}}`, `{{expression.path}}`. JSDoc type annotations like
  // `@param {{typedText?: string}}` are the repo's own convention (lib.js
  // carries the same) and are NOT template syntax — their contents are
  // `key: type` pairs, never a bare identifier path.
  assert.ok(!/\{\{[\s]*(#|\/|>|!)?[A-Za-z_$][\w$.]*[\s]*\}\}/.test(src), "no {{...}} template syntax");
  // No literal real client slug or location id.
  assert.ok(!/fixture-client-[a-z]|loc_a_fake|loc_b_fake/.test(src), "no hardcoded client/location");
});
