// Council front door (scripts/council-entry.mjs) - regressions for the
// 2026-10-28 operator failure recorded in the remote-rescue transcript:
//   * an explicit "ask the council" was answered with a COMPLETED verdict from
//     four days earlier, and no new session was opened;
//   * recovery used `blackceo-council status`, which reads the CLI's LOCAL
//     store, and reported COUNCIL_SESSION_NOT_FOUND while the service held the
//     session;
//   * the chamber link / desktop pop was a second, optional step and was
//     skipped;
//   * the service was down (LaunchAgent written, never bootstrapped) and the
//     agent improvised instead of refusing.
// Every test uses an injected fetch and an injected runner: no network, no
// real council, no paid call.
import assert from "node:assert/strict";
import { chmodSync, mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { clientReach, main, priorSittings, renderAsk } from "../council-entry.mjs";

const SKILL = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

function sandbox(t) {
  const d = realpathSync(mkdtempSync(join(tmpdir(), "cwe-entry-")));
  t.after(() => rmSync(d, { recursive: true, force: true }));
  return d;
}

const capture = () => {
  const out = []; const err = [];
  return { out: (s) => out.push(s), err: (s) => err.push(s), stdout: () => out.join(""), stderr: () => err.join("") };
};

const jsonResponse = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  headers: new Map(),
  json: async () => body,
  text: async () => JSON.stringify(body),
});

// A fetch stub: `routes` maps a path prefix to a response (or a function).
function fakeFetch(routes, calls = []) {
  const impl = async (url, init = {}) => {
    const u = new URL(url);
    calls.push({ path: u.pathname, method: init.method ?? "GET" });
    for (const [prefix, handler] of Object.entries(routes)) {
      if (u.pathname.startsWith(prefix)) {
        return typeof handler === "function" ? handler(u, init) : handler;
      }
    }
    throw new Error(`connection refused: ${u.pathname}`);
  };
  impl.calls = calls;
  return impl;
}

const HEALTHY = { "/healthz": jsonResponse(200, { ok: true }) };

// A runner stub: chamber-visual.sh, the convene CLI, and launchctl.
function fakeRun({ chamber = "Chamber link: https://trevor-council.example.com/chamber/#session=S1\n", convene = { status: 0, stdout: JSON.stringify({ session_id: "S1", route_id: "openrouter-configured", model_label: "openrouter default", selection_source: "harness_default", mode: "medium" }) } } = {}) {
  const calls = [];
  const run = (file, args = [], opts = {}) => {
    calls.push({ file, args, env: opts.env ?? {} });
    if (String(file).includes("chamber-visual.sh") || (file === "bash" && args.some((a) => String(a).includes("chamber-visual.sh")))) {
      return { status: 0, stdout: chamber, stderr: "pop: opened\n" };
    }
    if (file === "launchctl") return { status: 1, stdout: "", stderr: "Could not find service in domain" };
    return convene;
  };
  run.calls = calls;
  return run;
}

function fakeCli(d) {
  const cli = join(d, "blackceo-council");
  writeFileSync(cli, "#!/usr/bin/env node\nprocess.exit(0)\n");
  chmodSync(cli, 0o755);
  return cli;
}

test("an explicit ask always opens a NEW session, even when a COMPLETED sitting on the same question exists", async (t) => {
  const d = sandbox(t);
  const io = capture();
  const fetchImpl = fakeFetch({
    ...HEALTHY,
    "/api/council/sessions": jsonResponse(200, {
      sessions: [{ session_id: "S-OLD", state: "COMPLETED", mode: "medium", question: "What is the best day to launch a Black Friday offer in 2026?", created_at: "2026-10-25T23:04:46Z", sample: false }],
    }),
  });
  const run = fakeRun();
  const briefPath = join(d, "brief.json");
  writeFileSync(briefPath, JSON.stringify({ schema_version: "wise-elders.brief/v1", question: "What is the best day to launch a Black Friday offer in 2026?", options: [] }));

  const code = await main(["ask", "--brief", briefPath], io, { env: { HOME: d, COUNCIL_CLI: fakeCli(d) }, fetchImpl, run, skillRoot: SKILL });
  assert.equal(code, 0);

  const convene = run.calls.find((c) => c.args.includes("convene"));
  assert.ok(convene, "the ask must convene a new session (the recorded failure skipped this)");
  assert.equal(convene.args[convene.args.indexOf("--brief") + 1], briefPath);

  const text = io.stdout();
  assert.match(text, /Council convened: S1/);
  assert.match(text, /this ask still opened the NEW session S1/);
  assert.match(text, /Prior verdicts are context, never the answer/);
  // The prior verdict is never presented as the answer.
  assert.doesNotMatch(text, /WAIT/);
});

test("the chamber line and the desktop pop come from the convene itself, not a second optional step", async (t) => {
  const d = sandbox(t);
  const io = capture();
  const fetchImpl = fakeFetch({ ...HEALTHY, "/api/council/sessions": jsonResponse(200, { sessions: [] }) });
  const run = fakeRun();
  const briefPath = join(d, "brief.json");
  writeFileSync(briefPath, JSON.stringify({ question: "q" }));

  await main(["ask", "--brief", briefPath], io, { env: { HOME: d, COUNCIL_CLI: fakeCli(d) }, fetchImpl, run, skillRoot: SKILL });

  const visual = run.calls.find((c) => c.args.some((a) => String(a).includes("chamber-visual.sh")));
  assert.ok(visual, "chamber-visual.sh must run inside the ask (it prints the link and fires the pop)");
  assert.equal(visual.args[visual.args.indexOf("--session") + 1], "S1");
  assert.match(io.stdout(), /Chamber link: https:\/\/trevor-council\.example\.com\/chamber\/#session=S1/);
});

test("a documentation/fixture host is not a client link either", () => {
  // The operator box's service.json was rewritten to a fixture host mid-run
  // (public_origin https://fixed.example.com): a link like that is dead for a
  // client, so the entry command must flag it exactly like loopback.
  assert.deepEqual(clientReach("Chamber link: https://fixed.example.com/chamber/#session=S1"), { local: false, clientSafe: false });
  assert.deepEqual(clientReach("Chamber link: https://box.test/chamber/"), { local: false, clientSafe: false });
  assert.deepEqual(clientReach("Chamber link: https://trevor-council.zerohumanworkforce.com/chamber/"), { local: false, clientSafe: true });
  assert.deepEqual(clientReach("Chamber link: http://127.0.0.1:8787/chamber/"), { local: true, clientSafe: false });
  assert.deepEqual(clientReach("not a link"), { local: false, clientSafe: false });
});

test("a loopback chamber link is never offered as a client link", async (t) => {
  const payload = {
    ok: true, action: "ask", session_id: "S1", route_id: "r", model_label: "m", selection_source: "s",
    mode: "medium", service_origin: "http://127.0.0.1:8787", service_state: "up", service_repaired: false,
    chamber_link: "http://127.0.0.1:8787/chamber/", chamber_link_local: true,
    prior_completed_same_question: [], session_url: null, events_url: null,
  };
  const text = renderAsk(payload, { line: "Chamber link: http://127.0.0.1:8787/chamber/", local: true });
  assert.match(text, /never send it to a client/);
});

test("service down is a typed refusal: no convene, no session, no invented link", async (t) => {
  const d = sandbox(t);
  const io = capture();
  const fetchImpl = fakeFetch({}); // every probe throws: the service is down
  const run = fakeRun();
  const briefPath = join(d, "brief.json");
  writeFileSync(briefPath, JSON.stringify({ question: "q" }));

  const code = await main(["ask", "--brief", briefPath], io, { env: { HOME: d, COUNCIL_CLI: fakeCli(d) }, fetchImpl, run, skillRoot: SKILL });

  assert.equal(code, 3);
  const refusal = JSON.parse(io.stderr().trim());
  assert.equal(refusal.error.code, "COUNCIL_SERVICE_DOWN");
  assert.equal(run.calls.some((c) => c.args.includes("convene")), false, "never convene against a service that is down");
  assert.doesNotMatch(io.stdout(), /Chamber link:/);
});

test("a session read uses the SERVICE, not the CLI's local store (the COUNCIL_SESSION_NOT_FOUND trap)", async (t) => {
  const d = sandbox(t);
  const io = capture();
  const fetchImpl = fakeFetch({
    ...HEALTHY,
    "/council/S-LIVE": jsonResponse(200, {
      session_id: "S-LIVE", authority: "standalone", url: "http://127.0.0.1:8787/council/S-LIVE",
      session: { session_id: "S-LIVE", spec: { mode: "light", question: "q" }, state: { state: "ROUND_1" } },
    }),
  });
  const run = fakeRun();
  const code = await main(["session", "S-LIVE"], io, { env: { HOME: d, COUNCIL_CLI: fakeCli(d) }, fetchImpl, run, skillRoot: SKILL });

  assert.equal(code, 0);
  assert.match(io.stdout(), /store=service/);
  assert.match(io.stdout(), /state: ROUND_1/);
  assert.equal(run.calls.some((c) => c.args.includes("status")), false, "the CLI's local-store status must never answer a service session");
  assert.ok(fetchImpl.calls.some((c) => c.path === "/council/S-LIVE"));
});

test("a session the service does not hold reports store=service, not a bare not-found", async (t) => {
  const d = sandbox(t);
  const io = capture();
  const fetchImpl = fakeFetch({ ...HEALTHY, "/council/S-MISSING": jsonResponse(404, { code: "SERVICE_SESSION_NOT_FOUND", detail: "no such session" }) });
  const run = fakeRun();
  const code = await main(["session", "S-MISSING"], io, { env: { HOME: d }, fetchImpl, run, skillRoot: SKILL });

  assert.equal(code, 3);
  const refusal = JSON.parse(io.stderr().trim());
  assert.equal(refusal.error.code, "COUNCIL_SESSION_NOT_FOUND");
  assert.match(refusal.error.message, /store=service/);
  assert.equal(refusal.error.detail.store, "service");
});

test("sessions lists the service store and refuses an unbound list instead of an empty one", async (t) => {
  const d = sandbox(t);
  const io = capture();
  const ok = fakeFetch({ ...HEALTHY, "/api/council/sessions": jsonResponse(200, { sessions: [{ session_id: "S1", state: "COMPLETED", mode: "medium", question: "q", created_at: "2026-10-25T11:57:57Z" }] }) });
  assert.equal(await main(["sessions"], io, { env: { HOME: d }, fetchImpl: ok, run: fakeRun() }), 0);
  assert.match(io.stdout(), /S1\s+COMPLETED/);

  const io2 = capture();
  const unbound = fakeFetch({ ...HEALTHY, "/api/council/sessions": jsonResponse(501, { code: "SESSION_LIST_NOT_BOUND" }) });
  const code = await main(["sessions"], io2, { env: { HOME: d }, fetchImpl: unbound, run: fakeRun() });
  assert.equal(code, 3);
  assert.equal(JSON.parse(io2.stderr().trim()).error.code, "SESSION_LIST_NOT_BOUND");
});

test("authority reports the box's real service state, not a guess", async (t) => {
  const d = sandbox(t);
  const io = capture();
  const sj = join(d, "service.json");
  writeFileSync(sj, JSON.stringify({ origin: "http://127.0.0.1:8787", public_origin: "https://trevor-council.example.com", manager: "launchd", name: "ai.blackceo.council-service", release_id: "rel-abc" }));
  const code = await main(["authority"], io, { env: { HOME: d, WISE_ELDERS_SERVICE_JSON: sj }, fetchImpl: fakeFetch(HEALTHY), run: fakeRun() });
  assert.equal(code, 0);
  const text = io.stdout();
  assert.match(text, /service health: up/);
  assert.match(text, /public_origin: https:\/\/trevor-council\.example\.com/);
  assert.match(text, /release: rel-abc/);
  assert.match(text, /status\/verdict read its local store/);
});

test("prior sittings compare the question, never match on state alone", () => {
  const sessions = [
    { session_id: "A", state: "COMPLETED", question: "Best day to launch a Black Friday offer?" },
    { session_id: "B", state: "BLOCKED", question: "Best day to launch a Black Friday offer?" },
    { session_id: "C", state: "COMPLETED", question: "Something else entirely" },
  ];
  assert.deepEqual(priorSittings(sessions, "best day to launch a BLACK FRIDAY offer").map((s) => s.session_id), ["A"]);
  assert.deepEqual(priorSittings(sessions, ""), []);
});

test("an unknown command is usage, exit 2, and touches nothing", async () => {
  const io = capture();
  const code = await main(["frobnicate"], io);
  assert.equal(code, 2);
  assert.equal(JSON.parse(io.stderr().trim()).error.code, "USAGE");
});

// ------------------------------------------------ --json (CTR-103 repair)
// The usage header advertised [--json] on every subcommand while every writer
// ignored it and printed text. A machine caller must get exactly one JSON
// document, or the flag must not be advertised at all.
test("--json is honoured by all four subcommands", async (t) => {
  const d = sandbox(t);
  const sj = join(d, "service.json");
  writeFileSync(sj, JSON.stringify({ origin: "http://127.0.0.1:8787", public_origin: "https://trevor-council.example.com", manager: "launchd", name: "ai.blackceo.council-service", release_id: "rel-abc" }));
  const env = { HOME: d, WISE_ELDERS_SERVICE_JSON: sj, COUNCIL_CLI: fakeCli(d) };
  const fetchImpl = fakeFetch({
    ...HEALTHY,
    "/api/council/sessions": jsonResponse(200, { sessions: [{ session_id: "S1", state: "COMPLETED", mode: "medium", question: "q", created_at: "2026-10-25T11:57:57Z" }] }),
    "/council/S1": jsonResponse(200, { session: { session_id: "S1", spec: { mode: "medium", question: "q" }, state: { state: "COMPLETED" }, verdict: { label: "WAIT" } } }),
  });
  const briefPath = join(d, "brief.json");
  writeFileSync(briefPath, JSON.stringify({ question: "q" }));

  const cases = [
    ["authority", ["authority", "--json"], (o) => { assert.equal(o.action, "authority"); assert.equal(o.service_up, true); assert.ok(o.front_door.endsWith("council-entry.mjs")); }],
    ["sessions", ["sessions", "--json"], (o) => { assert.equal(o.store, "service"); assert.equal(o.sessions[0].session_id, "S1"); }],
    ["session", ["session", "S1", "--json"], (o) => { assert.equal(o.store, "service"); assert.equal(o.verdict_label, "WAIT"); assert.equal(o.desktop_pop, "opened"); }],
    ["ask", ["ask", "--brief", briefPath, "--json"], (o) => { assert.equal(o.session_id, "S1"); assert.equal(o.action, "ask"); assert.equal(o.desktop_pop, "opened"); }],
  ];
  for (const [name, argv, check] of cases) {
    const io = capture();
    const code = await main(argv, io, { env, fetchImpl, run: fakeRun(), skillRoot: SKILL });
    assert.equal(code, 0, `${name}: ${io.stderr()}`);
    const raw = io.stdout().trim();
    assert.match(raw, /^\{.*\}$/s, `${name} must print exactly one JSON document`);
    check(JSON.parse(raw));
  }
});

// --------------------------------- exactly one opener (CTR-101 + CTR-103)
// The runtime `convene` opens the chamber itself on a desktop box (CTR-101:
// --no-open / COUNCIL_CHAMBER_OPEN). council-ask delegates the convene, so
// without suppression a wired box would open TWO windows. The wrapper sets
// COUNCIL_CHAMBER_OPEN=0 on the convene child only and chamber-visual.sh owns
// the single pop. A legacy runtime ignores the variable and never opens, so
// "exactly one" holds in both generations.
for (const generation of ["new", "legacy"]) {
  test(`exactly one opener in the integrated flow (${generation} runtime)`, async (t) => {
    const d = sandbox(t);
    const io = capture();
    const fetchImpl = fakeFetch({ ...HEALTHY, "/api/council/sessions": jsonResponse(200, { sessions: [] }) });
    const briefPath = join(d, "brief.json");
    writeFileSync(briefPath, JSON.stringify({ question: "q" }));

    let runtimeOpens = 0;
    let helperCalls = 0;
    const calls = [];
    const run = (file, args = [], opts = {}) => {
      calls.push({ file, args, env: opts.env ?? {} });
      if (String(file).includes("chamber-visual.sh") || (file === "bash" && args.some((a) => String(a).includes("chamber-visual.sh")))) {
        helperCalls += 1;
        return { status: 0, stdout: "Chamber link: https://trevor-council.example.com/chamber/#session=S1\n", stderr: "pop: opened\n" };
      }
      if (args.includes("convene")) {
        const childEnv = opts.env ?? {};
        // The NEW runtime opens unless COUNCIL_CHAMBER_OPEN is 0/no/false;
        // the legacy runtime has no desktop opener at all.
        const wantsOpen = !["0", "no", "false"].includes(String(childEnv.COUNCIL_CHAMBER_OPEN));
        if (generation === "new" && wantsOpen) runtimeOpens += 1;
        return { status: 0, stdout: JSON.stringify({ session_id: "S1", route_id: "r", model_label: "m", selection_source: "s", mode: "medium" }) };
      }
      return { status: 0, stdout: "", stderr: "" };
    };

    const code = await main(["ask", "--brief", briefPath], io, { env: { HOME: d, COUNCIL_CLI: fakeCli(d) }, fetchImpl, run, skillRoot: SKILL });
    assert.equal(code, 0, io.stderr());

    const convene = calls.find((c) => c.args.includes("convene"));
    assert.ok(convene, "the ask must convene");
    assert.equal(convene.env.COUNCIL_CHAMBER_OPEN, "0", "the convene child must carry the CTR-101 single-opener control");
    assert.equal(runtimeOpens, 0, "the runtime convene must not open a second browser");
    assert.equal(helperCalls, 1, "chamber-visual.sh is invoked exactly once");
    assert.equal(runtimeOpens + helperCalls, 1, "exactly one opener in total");
  });
}
