// Offline, hermetic tests for loop-brake (Skill 61 Fix 9). Run: node --test 61-loop-protection-system/loop-brake/tests/
// No network, no live sends, no OpenClaw host, no client chats. Time is injected; the host is a stub.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { cpSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  BLOCK_REASON, FAIL_CLOSED_REASON, DEFAULT_CONFIG_DIR, createBrake, loadConfig, normalize, payloadHash, register, rolloutEnabled,
} from "../brake-core.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const BRAKE_DIR = join(HERE, "..");
const SKILL_DIR = join(BRAKE_DIR, "..");
const SCRIPTS = join(SKILL_DIR, "scripts");

const read = (p) => JSON.parse(readFileSync(p, "utf8"));
const thresholds = () => read(join(DEFAULT_CONFIG_DIR, "thresholds.json"));
const D7 = () => thresholds().d7_cross_run_resend;
const D6 = () => thresholds().d6_futile_retry_burst;

function rig(cfgDir = DEFAULT_CONFIG_DIR) {
  const clock = { t: 1_000_000 };
  const log = [];
  const brake = createBrake(loadConfig(cfgDir), { now: () => clock.t, say: (level, msg) => log.push([level, msg]) });
  return { brake, clock, log };
}
const send = (brake, message, { src = "agent:a:main", dst = "agent:b:main" } = {}) =>
  brake.beforeSend({ toolName: "sessions_send", params: { sessionKey: dst, message } }, { sessionKey: src });
const refusal = (extra = {}) => ({
  toolName: "exec", runId: "run-1",
  result: { isError: true, content: [{ type: "text", text: '{"error":"Unauthorized"}' }] }, ...extra,
});

// ---- config is read at runtime, never copied ------------------------------------------------
test("thresholds come from config files, not constants", () => {
  const tmp = mkdtempSync(join(tmpdir(), "lane-SKS-006-cfg-"));
  try {
    cpSync(DEFAULT_CONFIG_DIR, tmp, { recursive: true });
    const t = thresholds();
    t.d7_cross_run_resend.p1_repeat = 4;
    t.d7_cross_run_resend.window_seconds = 10;
    writeFileSync(join(tmp, "thresholds.json"), JSON.stringify(t));
    const { brake, clock } = rig(tmp);
    for (let i = 0; i < 3; i++) assert.equal(send(brake, "same"), undefined, `send ${i + 1} passes when p1_repeat is 4`);
    assert.equal(send(brake, "same")?.block, true, "4th is blocked");
    clock.t += 11_000; // window_seconds is 10 in this copy
    assert.equal(send(brake, "same"), undefined, "window of 10s expired");
  } finally { rmSync(tmp, { recursive: true, force: true }); }
});

test("repo thresholds still match the D6/D7 measured safe values", () => {
  assert.deepEqual(
    [D7().window_seconds, D7().warn_repeat, D7().p1_repeat, D6().doctrine_max_attempts, D6().warn_failclosed_calls, D6().p1_failclosed_calls],
    [300, 2, 3, 2, 3, 5],
  );
});

// ---- sessions_send brake --------------------------------------------------------------------
test("first two identical sends pass, third is blocked with the exact reason", () => {
  const { brake } = rig();
  assert.equal(send(brake, "please run the report"), undefined);
  assert.equal(send(brake, "please run the report"), undefined);
  const r = send(brake, "please run the report");
  assert.deepEqual(r, { block: true, blockReason: BLOCK_REASON });
  assert.equal(r.blockReason, "Already delivered; do not resend. Use timeoutSeconds: 0 or wait for the late reply.");
  assert.equal(send(brake, "please run the report")?.block, true, "stays blocked inside the window");
});

test("whitespace and a bracketed preamble do not defeat the hash", () => {
  const { brake } = rig();
  assert.equal(send(brake, "do the thing   now"), undefined);
  assert.equal(send(brake, "[from agent-x via sessions_send]\ndo the thing\nnow"), undefined);
  assert.equal(send(brake, "  do   the thing now \n")?.block, true);
});

test("window expiry frees the pair; a blocked attempt does not extend the window", () => {
  const { brake, clock } = rig();
  send(brake, "m"); clock.t += 100_000; send(brake, "m"); clock.t += 100_000;
  assert.equal(send(brake, "m")?.block, true); // t=200s, 2 prior inside window
  clock.t += 150_000; // t=350s: first send (t=0) is now 350s old and out of the window
  assert.equal(send(brake, "m"), undefined);
});

test("distinct-payload fan-out is never blocked", () => {
  const { brake } = rig();
  for (let i = 0; i < 200; i++) assert.equal(send(brake, `task number ${i}`), undefined, `distinct payload ${i}`);
  for (let i = 0; i < 200; i++) assert.equal(send(brake, "broadcast", { dst: `agent:w${i}:main` }), undefined, `distinct target ${i}`);
});

test("source sessions are counted separately", () => {
  const { brake } = rig();
  send(brake, "x", { src: "s1" }); send(brake, "x", { src: "s2" });
  assert.equal(send(brake, "x", { src: "s1" }), undefined);
  assert.equal(send(brake, "x", { src: "s2" }), undefined);
  assert.equal(send(brake, "x", { src: "s1" })?.block, true);
});

test("label and agentId targets work; unknown pair or empty body fails open", () => {
  const { brake } = rig();
  const viaLabel = () => brake.beforeSend({ toolName: "sessions_send", params: { label: "ops", message: "m" } }, { sessionKey: "s" });
  viaLabel(); viaLabel();
  assert.equal(viaLabel()?.block, true);
  for (let i = 0; i < 5; i++) {
    assert.equal(brake.beforeSend({ toolName: "sessions_send", params: { message: "m" } }, { sessionKey: "s" }), undefined);
    assert.equal(brake.beforeSend({ toolName: "sessions_send", params: { sessionKey: "t", message: "   " } }, { sessionKey: "s" }), undefined);
    assert.equal(brake.beforeSend({ toolName: "sessions_send", params: { sessionKey: "t", message: "m" } }, {}), undefined);
  }
});

test("other tools are untouched by the send brake", () => {
  const { brake } = rig();
  for (let i = 0; i < 6; i++) assert.equal(brake.beforeSend({ toolName: "exec", params: { message: "m", sessionKey: "t" } }, { sessionKey: "s" }), undefined);
});

// ---- after_tool_call auth-refusal counting (D6 two-layer) -----------------------------------
test("refusals reach warn at 3 and P1 at 5 per (run, tool), each reported once", () => {
  const { brake, log } = rig();
  const levels = () => log.map((l) => l[0]);
  brake.afterToolCall(refusal()); brake.afterToolCall(refusal());
  assert.deepEqual(levels(), [], "2 refusals: silent");
  brake.afterToolCall(refusal());
  assert.deepEqual(levels(), ["warn"], "3rd: warn");
  brake.afterToolCall(refusal());
  assert.deepEqual(levels(), ["warn"], "4th: no repeat report");
  brake.afterToolCall(refusal());
  assert.deepEqual(levels(), ["warn", "error"], "5th: P1");
  for (let i = 0; i < 5; i++) brake.afterToolCall(refusal());
  assert.deepEqual(levels(), ["warn", "error"], "reported once each");
});

test("counts are per run and per tool", () => {
  const { brake, log } = rig();
  for (let i = 0; i < 2; i++) { brake.afterToolCall(refusal({ runId: "r1" })); brake.afterToolCall(refusal({ runId: "r2" })); brake.afterToolCall(refusal({ toolName: "curl" })); }
  assert.deepEqual(log, []);
  brake.afterToolCall(refusal({ runId: "r1" }));
  assert.equal(log.length, 1);
  assert.match(log[0][1], /tool=exec run=r1/);
});

test("two-layer test: exempt tool, prose-only text, and clean results do not count", () => {
  const { brake, log } = rig();
  const text = (t, extra) => ({ toolName: "exec", runId: "r", result: { content: [{ type: "text", text: t }] }, ...extra });
  for (let i = 0; i < 8; i++) {
    brake.afterToolCall({ toolName: "read", runId: "r", result: { isError: true, content: "unauthorized forbidden" } }); // L1 exempt
    brake.afterToolCall(text("Section 4 explains why a request is unauthorized and what forbidden means.")); // prose, not failed
    brake.afterToolCall(text("all good", { error: undefined })); // no marker
    brake.afterToolCall(text("ok", { error: "boom" })); // failed, but no marker
  }
  assert.deepEqual(log, []);
  assert.deepEqual(brake.snapshot().refusals, {});
});

test("failed marker, error-shaped marker, and details.status all count", () => {
  const { brake } = rig();
  const mk = (r, extra) => ({ toolName: "web_fetch", runId: "r", result: r, ...extra });
  brake.afterToolCall(mk({ isError: true, content: "Invalid API key" }));
  brake.afterToolCall(mk({ content: [{ text: 'HTTP/1.1 403 Forbidden' }] }));
  brake.afterToolCall(mk({ details: { status: "failed" }, content: "authentication failed" }));
  brake.afterToolCall(mk({ content: "x" }, { error: "Not authenticated" }));
  brake.afterToolCall(mk({ content: '{"error":"missing credentials"}' }));
  assert.equal(brake.snapshot().refusals["r|web_fetch"], 5);
});

test("the third call to a tool that refused twice is blocked, others pass", () => {
  const { brake, log } = rig();
  const before = (toolName, runId = "run-1") => brake.beforeRefusal({ toolName, runId }, {});
  assert.equal(before("exec"), undefined);
  brake.afterToolCall(refusal());
  assert.equal(before("exec"), undefined, "after 1 refusal");
  brake.afterToolCall(refusal());
  assert.deepEqual(before("exec"), { block: true, blockReason: FAIL_CLOSED_REASON }, "3rd call blocked");
  assert.equal(before("curl"), undefined, "other tool free");
  assert.equal(before("exec", "run-2"), undefined, "other run free");
  assert.deepEqual(log.map((l) => l[0]), ["warn"], "blocked attempt is the 3rd attempt: warn once");
  before("exec"); before("exec");
  assert.deepEqual(log.map((l) => l[0]), ["warn", "error"], "5th attempt: P1 once");
  assert.equal(FAIL_CLOSED_REASON, "Fail-closed dependency: stop and report once (N40)");
});

// ---- ships DISABLED --------------------------------------------------------------------------
function stubApi() {
  const handlers = [];
  const logs = [];
  const logger = Object.fromEntries(["debug", "info", "warn", "error"].map((l) => [l, (m) => logs.push([l, m])]));
  return { api: { on: (name, fn, opts) => handlers.push({ name, fn, opts }), logger }, handlers, logs };
}

test("rollout gate in the repo is still OFF, and a held gate registers nothing", () => {
  const gate = read(join(DEFAULT_CONFIG_DIR, "rollout.json"));
  assert.equal(gate.fleet_rollout_enabled, false, "config/rollout.json must stay fleet_rollout_enabled:false");
  assert.equal(rolloutEnabled(DEFAULT_CONFIG_DIR, {}), false);
  const { api, handlers, logs } = stubApi();
  assert.equal(register(api, { env: {} }), null);
  assert.deepEqual(handlers, [], "no hook registered while held");
  assert.match(logs[0][1], /held by the Skill 61 rollout gate/);
});

test("manifest default state is OFF and carries no approval gate", () => {
  const m = read(join(BRAKE_DIR, "openclaw.plugin.json"));
  assert.equal(m.id, "loop-brake");
  assert.ok(!("enabledByDefault" in m), "omitting enabledByDefault leaves a plugin disabled by default");
  assert.ok(!("enabledByDefaultOnPlatforms" in m));
  assert.equal(typeof m.configSchema, "object");
  const gateWord = ["require", "Approval"].join("");
  for (const f of readdirSync(BRAKE_DIR, { recursive: true })) {
    if (!/\.(mjs|json|md)$/.test(f) || f.includes("brake.test")) continue;
    assert.ok(!readFileSync(join(BRAKE_DIR, f), "utf8").includes(gateWord), `${f} must not use an approval gate`);
  }
  assert.ok(!readFileSync(join(HERE, "brake.test.mjs"), "utf8").includes(`${gateWord}:`), "tests never request approval");
});

test("only the gate being enabled registers the hooks, with the spec matcher", () => {
  const tmp = mkdtempSync(join(tmpdir(), "lane-SKS-006-gate-"));
  try {
    cpSync(DEFAULT_CONFIG_DIR, tmp, { recursive: true });
    writeFileSync(join(tmp, "rollout.json"), JSON.stringify({ fleet_rollout_enabled: true }));
    const { api, handlers } = stubApi();
    assert.ok(register(api, { configDir: tmp, env: {} }));
    const names = handlers.map((h) => h.name).sort();
    assert.deepEqual(names, ["after_tool_call", "before_tool_call", "before_tool_call"]);
    const sendHook = handlers.find((h) => h.opts?.matcher);
    assert.deepEqual(sendHook.opts.matcher, ["sessions_send"]);
    // env override: same precedence as activate-loop-protection.sh
    const held = stubApi();
    assert.equal(register(held.api, { env: { OPENCLAW_LOOP_PROTECTION_ROLLOUT: "0" } }), null);
    const forced = stubApi();
    assert.ok(register(forced.api, { env: { OPENCLAW_LOOP_PROTECTION_ROLLOUT: "1" } }));
  } finally { rmSync(tmp, { recursive: true, force: true }); }
});

test("a registered hook returns the block through the host contract", () => {
  const tmp = mkdtempSync(join(tmpdir(), "lane-SKS-006-host-"));
  try {
    cpSync(DEFAULT_CONFIG_DIR, tmp, { recursive: true });
    writeFileSync(join(tmp, "rollout.json"), JSON.stringify({ fleet_rollout_enabled: true }));
    const { api, handlers } = stubApi();
    register(api, { configDir: tmp, env: {}, now: () => 5 });
    const hook = handlers.find((h) => h.opts?.matcher).fn;
    const ev = { toolName: "sessions_send", params: { sessionKey: "t", message: "m" } };
    assert.equal(hook(ev, { sessionKey: "s" }), undefined);
    assert.equal(hook(ev, { sessionKey: "s" }), undefined);
    assert.deepEqual(hook(ev, { sessionKey: "s" }), { block: true, blockReason: BLOCK_REASON });
  } finally { rmSync(tmp, { recursive: true, force: true }); }
});

test("unreadable config fails open: nothing registered, nothing blocked", () => {
  const tmp = mkdtempSync(join(tmpdir(), "lane-SKS-006-bad-"));
  try {
    writeFileSync(join(tmp, "rollout.json"), JSON.stringify({ fleet_rollout_enabled: true }));
    writeFileSync(join(tmp, "thresholds.json"), "{not json");
    const { api, handlers, logs } = stubApi();
    assert.equal(register(api, { configDir: tmp, env: {} }), null);
    assert.deepEqual(handlers, []);
    assert.equal(logs.at(-1)[0], "warn");
  } finally { rmSync(tmp, { recursive: true, force: true }); }
});

// ---- no content stored, nothing on disk -------------------------------------------------------
test("no message or result content is kept: snapshot and logs carry only hashes and counts", () => {
  const TRACERS = ["TRACERBODYsecretmessage", "TRACERARGtoolparam", "TRACERRESULTbearertoken"];
  const { brake, log } = rig();
  for (let i = 0; i < 4; i++) {
    brake.beforeSend({ toolName: "sessions_send", params: { sessionKey: "agent:b", message: `${TRACERS[0]} do it` } }, { sessionKey: "agent:a" });
    brake.beforeRefusal({ toolName: "exec", runId: "r", params: { cmd: TRACERS[1] } }, {});
    brake.afterToolCall({ toolName: "exec", runId: "r", params: { cmd: TRACERS[1] },
      result: { isError: true, content: `unauthorized ${TRACERS[2]}` }, error: `forbidden ${TRACERS[2]}` });
  }
  const dump = JSON.stringify([brake.snapshot(), log]);
  for (const t of TRACERS) assert.ok(!dump.includes(t), `${t} must not be retained or logged`);
  assert.match(Object.keys(brake.snapshot().sends)[0], /^[0-9a-f]{16}$/);
});

test("writes nothing to disk: process run in an empty cwd and HOME leaves both empty", () => {
  const cwd = mkdtempSync(join(tmpdir(), "lane-SKS-006-cwd-"));
  const home = mkdtempSync(join(tmpdir(), "lane-SKS-006-home-"));
  try {
    const code = `
      import { createBrake, loadConfig } from ${JSON.stringify(join(BRAKE_DIR, "brake-core.mjs"))};
      const b = createBrake(loadConfig(${JSON.stringify(DEFAULT_CONFIG_DIR)}), { say: () => {} });
      for (let i = 0; i < 6; i++) {
        b.beforeSend({ toolName: "sessions_send", params: { sessionKey: "t", message: "m" } }, { sessionKey: "s" });
        b.afterToolCall({ toolName: "exec", runId: "r", result: { isError: true, content: "unauthorized" } });
      }`;
    execFileSync(process.execPath, ["--input-type=module", "-e", code], { cwd, env: { PATH: process.env.PATH, HOME: home }, stdio: "pipe" });
    assert.deepEqual(readdirSync(cwd), []);
    assert.deepEqual(readdirSync(home), []);
  } finally { rmSync(cwd, { recursive: true, force: true }); rmSync(home, { recursive: true, force: true }); }
});

test("source imports no write path (static)", () => {
  const src = readFileSync(join(BRAKE_DIR, "brake-core.mjs"), "utf8");
  assert.match(src, /import \{ readFileSync \} from "node:fs"/);
  for (const bad of ["writeFile", "appendFile", "createWriteStream", "mkdir", "node:child_process", "fetch(", "node:net", "node:http"]) {
    assert.ok(!src.includes(bad), `brake-core.mjs must not use ${bad}`);
  }
});

// ---- hash parity with the Python detector ------------------------------------------------------
test("payload hash matches scripts/loop_common.py cross_run_payload_hash byte for byte", () => {
  const vectors = [
    ["a", "b", "hello world"],
    ["a", "b", "[from agent-x via sessions_send]\nhello    world\n"],
    ["agent:main:main", "agent:ops:main", "  tabs\tand\r\nnewlines  "],
    ["s", "t", "unicode  nbsp  emsp 　ideographic café \u{1F600}"],
    ["s", "t", "\u0085nel and  ls and \u001cfs"],
    ["", "t", ""],
    ["s", "t", "[only a header]"],
    ["s", "t", "[a]\n[b] second header stays"],
  ];
  const py = `
import json, sys
sys.path.insert(0, ${JSON.stringify(SCRIPTS)})
import loop_common as C
print(json.dumps([C.cross_run_payload_hash(*v) for v in json.load(sys.stdin)]))`;
  const home = mkdtempSync(join(tmpdir(), "lane-SKS-006-py-"));
  try {
    const out = execFileSync("python3", ["-c", py], {
      input: JSON.stringify(vectors), encoding: "utf8", env: { PATH: process.env.PATH, HOME: home, LOOP_NO_PROBES: "1" },
    });
    assert.deepEqual(vectors.map((v) => payloadHash(...v)), JSON.parse(out));
  } finally { rmSync(home, { recursive: true, force: true }); }
  assert.equal(normalize("[x]\n a   b "), "a b");
});
