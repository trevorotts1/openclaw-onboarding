// CTR-127 targeted regression source (keeps CTR-124/CTR-125 cases).
// NOT EXECUTED by the implementer.
//
// Run by Trevor (or an independent reviewer) with:
//   node --test test/core.test.mjs
//
// It exercises the plugin core with injected spawn/runtime/clock seams. It
// makes no Telegram, Council, service, provider, or network call: the fake
// spawn never starts a process, and the fake runtime never convenes. The
// runtime-closure cases create throwaway directory trees; they never import
// the real Council runtime.

import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  FRONTDOOR_WORST_CASE_MS,
  handleInbound,
  moduleSpecifiers,
  normalizeConfig,
  resolveRuntimeRoot,
  RUNTIME_CLOSURE_ENTRIES,
  RUNTIME_UNRESOLVED_CODE,
  RuntimeUnresolvedError,
  runtimeClosureProblems,
  sha256,
  TIMEOUT_DEFAULT_MS,
  TIMEOUT_MAX_MS,
  TIMEOUT_MIN_MS,
} from "../lib/core.mjs";
import { authorizedSenderSelection } from "../provision.mjs";

function tempDir() {
  return mkdtempSync(join(tmpdir(), "ctr124-"));
}

function configFor(stateDir, overrides = {}) {
  const parsed = normalizeConfig({
    channel: "telegram",
    accountId: "acct-1",
    conversationId: "chat-1",
    senderIds: ["sender-1"],
    agentId: "council-agent",
    agentWorkspace: "/tmp/agent-workspace",
    councilAskPath: "/tmp/council-ask",
    runtimeRoot: "/tmp/council-runtime",
    stateDir,
    mode: "medium",
    displayTimezone: "UTC",
    timeoutMs: 300000,
    ...overrides,
  });
  assert.equal(parsed.ok, true, parsed.reason);
  return parsed.config;
}

function inbound(overrides = {}) {
  const event = {
    messageId: "m-1",
    content: "ask the council Should I raise prices?",
    channel: "telegram",
    senderId: "sender-1",
    sessionKey: "agent:council-agent:direct:1",
    isGroup: false,
    ...overrides.event,
  };
  const ctx = {
    messageId: "m-1",
    channelId: "telegram",
    accountId: "acct-1",
    conversationId: "chat-1",
    senderId: "sender-1",
    sessionKey: "agent:council-agent:direct:1",
    ...overrides.ctx,
  };
  return { event, ctx };
}

function fakeRuntime(permitted = {}) {
  return {
    async loadRuntime() {
      return {
        assembleBrief() {
          return {
            options: [],
            facts: [],
            constraints: [],
            unknowns: [],
            private_preference_ref: null,
            ...permitted,
          };
        },
        validateDecisionBrief(brief) {
          return { ok: true, value: brief };
        },
      };
    },
  };
}

function fakeRunner({ stdout = "", stderr = "", code = 0, signal = null } = {}) {
  const calls = [];
  function spawn(command, args, options) {
    calls.push({ command, args, options });
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.kill = () => undefined;
    process.nextTick(() => {
      if (stdout) child.stdout.emit("data", Buffer.from(stdout));
      if (stderr) child.stderr.emit("data", Buffer.from(stderr));
      child.emit("close", code, signal);
    });
    return child;
  }
  spawn.calls = calls;
  return spawn;
}

const SUCCESS = JSON.stringify({
  ok: true,
  action: "ask",
  session_id: "sess-1",
  mode: "medium",
  route_id: "deepseek-configured",
  model_label: "deepseek-flash",
  service_origin: "http://127.0.0.1:8787",
  chamber_link: "https://council.blackceo.com/council/sess-1",
  chamber_link_local: false,
  chamber_link_client_safe: true,
  prior_completed_same_question: [],
});

// The literal observed ask from CTR-122 TRACE-EVIDENCE.md line 10, verbatim:
// two spaces after THE, "WAT", "FRIDAAY". The pre-fix phrase gate required a
// single space and let this exact message fall through to the model turn.
const OBSERVED_ASK = "ASK THE  COUNCIL WAT THE BEST PRODUCT FOR MY BLACK FRIDAAY LAUNCH";

function depsFor(runner, runtime = fakeRuntime(), extra = {}) {
  return {
    spawn: runner,
    loadRuntime: runtime.loadRuntime,
    now: () => new Date("2026-10-29T12:00:00.000Z"),
    ...extra,
  };
}

test("exact observed ask (double space, verbatim casing) reaches the front door once", async (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const config = configFor(dir);
  const runner = fakeRunner({ stdout: SUCCESS });
  const { event, ctx } = inbound({ event: { content: OBSERVED_ASK } });

  const result = await handleInbound({ event, ctx, config, deps: depsFor(runner) });

  assert.equal(runner.calls.length, 1);
  assert.equal(result.handled, true);
  assert.match(result.text, /^Council convened: sess-1/);
  const args = runner.calls[0].args;
  const brief = JSON.parse(readFileSync(args[args.indexOf("--brief") + 1], "utf8"));
  // The ORIGINAL remainder is preserved byte for byte, typos included.
  assert.equal(brief.question, "WAT THE BEST PRODUCT FOR MY BLACK FRIDAAY LAUNCH");
});

test("a recognized ask that cannot be used is answered as a refusal, not left to the model", async (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const config = configFor(dir, { maxQuestionChars: 20 });
  const runner = fakeRunner({ stdout: SUCCESS });
  const { event, ctx } = inbound({
    event: { content: `ask the council ${"a".repeat(50)}` },
  });

  const result = await handleInbound({ event, ctx, config, deps: depsFor(runner) });

  assert.equal(runner.calls.length, 0);
  assert.equal(result.handled, true);
  assert.match(result.text, /^Council did not convene\./);
  assert.match(result.text, /COUNCIL_ASK_TOO_LONG/);
});

test("a loopback chamber link is never rendered as sendable", async (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const config = configFor(dir);
  const runner = fakeRunner({
    stdout: JSON.stringify({
      ...JSON.parse(SUCCESS),
      // The service line legitimately names the local origin; only the chamber
      // link rule is under test, so that line stays loopback here on purpose.
      chamber_link: "http://127.0.0.1:8787/council/sess-1",
      chamber_link_local: true,
      chamber_link_client_safe: false,
    }),
  });
  const { event, ctx } = inbound();

  const result = await handleInbound({ event, ctx, config, deps: depsFor(runner) });

  assert.equal(result.handled, true);
  // Narrow to the Chamber link line: a loopback chamber link must never be
  // emitted as a "Chamber link:" line at all.
  const chamberLinkLines = result.text
    .split("\n")
    .filter((line) => line.trimStart().startsWith("Chamber link:"));
  assert.deepEqual(chamberLinkLines, []);
  assert.match(result.text, /never send it to a client/);
});

test("authorized explicit ask reaches the front door once", async (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const config = configFor(dir);
  const runner = fakeRunner({ stdout: SUCCESS });
  const { event, ctx } = inbound();

  const result = await handleInbound({ event, ctx, config, deps: depsFor(runner) });

  assert.equal(runner.calls.length, 1);
  assert.equal(result.handled, true);
  assert.match(result.text, /^Council convened: sess-1/);
  assert.doesNotMatch(result.text, /\bGO\b/);
});

test("wrong sender is unhandled and never reaches the runner", async (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const config = configFor(dir);
  const runner = fakeRunner({ stdout: SUCCESS });
  const { event, ctx } = inbound({
    event: { senderId: "intruder" },
    ctx: { senderId: "intruder" },
  });

  const result = await handleInbound({ event, ctx, config, deps: depsFor(runner) });

  assert.equal(result, undefined);
  assert.equal(runner.calls.length, 0);
});

test("read/control asks do not create a new sitting", async (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const config = configFor(dir);
  for (const content of [
    "ask the council what did they decide",
    "ask the council stop that council",
    "ask the council read the verdict",
    "ask the council resume",
  ]) {
    const runner = fakeRunner({ stdout: SUCCESS });
    const { event, ctx } = inbound({ event: { content } });
    const result = await handleInbound({ event, ctx, config, deps: depsFor(runner) });
    assert.equal(result, undefined, content);
    assert.equal(runner.calls.length, 0, content);
  }
});

test("duplicate message id spends once and replays the stored result", async (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const config = configFor(dir);
  const runner = fakeRunner({ stdout: SUCCESS });
  const deps = depsFor(runner);
  const { event, ctx } = inbound();

  const first = await handleInbound({ event, ctx, config, deps });
  const second = await handleInbound({ event, ctx, config, deps });

  assert.equal(runner.calls.length, 1);
  assert.match(first.text, /^Council convened: sess-1/);
  assert.match(second.text, /^Council convened: sess-1/);
});

test("configured caller workspace is passed and no route is guessed", async (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const config = configFor(dir);
  const runner = fakeRunner({ stdout: SUCCESS });
  const { event, ctx } = inbound();

  await handleInbound({ event, ctx, config, deps: depsFor(runner) });

  const call = runner.calls[0];
  assert.equal(call.command, config.councilAskPath);
  assert.equal(call.options.cwd, config.agentWorkspace);
  assert.equal(call.options.shell, false);
  assert.equal(call.options.env.OPENCLAW_WORKSPACE_DIR, undefined);
  assert.equal(call.args.includes("--route"), false);
  assert.equal(call.args.includes("--model"), false);
  assert.equal(call.args[0], "ask");
  assert.equal(call.args.includes("--json"), true);
});

test("brief is honest: original question, explicit unknowns, no invented options", async (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const config = configFor(dir);
  const runner = fakeRunner({ stdout: SUCCESS });
  const runtime = fakeRuntime({
    options: [],
    facts: [{ statement: "The operator wants to keep the current price.", source: "memory.md" }],
    constraints: ["Must stay within the current budget."],
    unknowns: ["The launch date is unknown."],
  });
  const { event, ctx } = inbound({
    event: { content: "ask the council Should I raise prices by ten percent?" },
  });

  await handleInbound({
    event,
    ctx,
    config,
    deps: depsFor(runner, runtime, {
      readFile: () => Buffer.from("permitted memory bytes"),
    }),
  });

  const args = runner.calls[0].args;
  const briefPath = args[args.indexOf("--brief") + 1];
  const brief = JSON.parse(readFileSync(briefPath, "utf8"));

  assert.equal(brief.question, "Should I raise prices by ten percent?");
  assert.deepEqual(brief.options, [
    {
      id: "option-explore",
      label: "Explore the question with the Council; no option has been chosen yet.",
      kind: "other",
    },
  ]);
  assert.equal(brief.relevance_weights && Object.keys(brief.relevance_weights).length, 0);
  assert.deepEqual(brief.critical_domains, []);
  assert.equal(brief.evidence_manifest.length, 1);
  assert.equal(brief.evidence_manifest[0].sha256, sha256("permitted memory bytes"));
  assert.deepEqual(brief.facts[0].evidence_ids, [brief.evidence_manifest[0].evidence_id]);
  const unknownText = brief.unknowns.map((u) => u.statement).join("\n");
  assert.match(unknownText, /no critical-domain classification was performed/);
  assert.match(unknownText, /hardness not established/);
  assert.match(unknownText, /must not assume a product catalog/);
});

test("front-door failure is returned as failure, never as success", async (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const config = configFor(dir);
  const runner = fakeRunner({
    code: 3,
    stderr: JSON.stringify({
      ok: false,
      error: {
        code: "COUNCIL_SERVICE_DOWN",
        message: "The council service did not answer.",
        action: "Start the service, then retry.",
      },
    }),
  });
  const { event, ctx } = inbound();

  const result = await handleInbound({ event, ctx, config, deps: depsFor(runner) });

  assert.equal(result.handled, true);
  assert.match(result.text, /^Council did not convene\./);
  assert.match(result.text, /COUNCIL_SERVICE_DOWN/);
  assert.doesNotMatch(result.text, /^Council convened:/);
});

test("question and message text stay data: argv is fixed, no shell interpolation", async (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const config = configFor(dir);
  const runner = fakeRunner({ stdout: SUCCESS });
  const hostile = "Should I keep this vendor; rm -rf / && echo pwned";
  const { event, ctx } = inbound({ event: { content: `ask the council ${hostile}` } });

  await handleInbound({ event, ctx, config, deps: depsFor(runner) });

  const call = runner.calls[0];
  assert.equal(call.options.shell, false);
  assert.deepEqual(call.args.slice(0, 1), ["ask"]);
  assert.equal(call.args.some((arg) => arg.includes("rm -rf")), false);
  const briefPath = call.args[call.args.indexOf("--brief") + 1];
  const brief = JSON.parse(readFileSync(briefPath, "utf8"));
  assert.equal(brief.question, hostile);
});

// A state-dir fault (mkdir/open/claim) must be answered INSIDE the bounded
// handler as a typed refusal. Falling through to `undefined` would hand the
// authorized ask to a model that can invent a GO, and spawning before the
// claim exists would break the one-sitting-per-message property.
test("state-dir fault is refused inside the handler: handled, no spawn", async (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  // A regular file where the state directory should be: mkdir cannot succeed.
  const blocker = join(dir, "blocker");
  writeFileSync(blocker, "not a directory");
  const config = configFor(join(blocker, "state"));
  const runner = fakeRunner({ stdout: SUCCESS });
  const { event, ctx } = inbound();

  const result = await handleInbound({
    event,
    ctx,
    config,
    deps: depsFor(runner, fakeRuntime(), { logger: { error: () => undefined } }),
  });

  assert.notEqual(result, undefined, "a recognized authorized ask must never become undefined");
  assert.equal(result.handled, true);
  assert.match(result.text, /^Council did not convene\./);
  assert.match(result.text, /COUNCIL_CLAIM_FAILED/);
  assert.match(result.text, /no Council sitting was started|Fix the plugin state directory/i);
  assert.equal(runner.calls.length, 0);
  assert.equal(existsSync(join(blocker, "state", "claims")), false);
});

// The hook budget must be coherent across the manifest schema and the core, and
// must exceed the front door's own worst case. A too-short value is refused
// before any state write or spend; it is never clamped over a running sitting.
test("timeout floor/default/ceiling agree across schema and core, and a short value fails closed", async (t) => {
  const manifest = JSON.parse(
    readFileSync(new URL("../openclaw.plugin.json", import.meta.url), "utf8"),
  );
  const schema = manifest.configSchema.properties.timeoutMs;

  assert.equal(schema.minimum, TIMEOUT_MIN_MS);
  assert.equal(schema.default, TIMEOUT_DEFAULT_MS);
  assert.equal(schema.maximum, TIMEOUT_MAX_MS);
  assert.ok(
    TIMEOUT_MIN_MS > FRONTDOOR_WORST_CASE_MS,
    `hook floor ${TIMEOUT_MIN_MS} must exceed the front door's ${FRONTDOOR_WORST_CASE_MS} ms worst case`,
  );

  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const config = configFor(dir, { timeoutMs: 1000 });
  assert.equal(config.timeoutMs, TIMEOUT_DEFAULT_MS, "the hook timer falls back to the safe default");
  assert.ok(config.timeoutBlocked, "a too-short timeoutMs is blocked, never clamped silently");

  const runner = fakeRunner({ stdout: SUCCESS });
  const { event, ctx } = inbound();
  const result = await handleInbound({ event, ctx, config, deps: depsFor(runner) });

  assert.equal(result.handled, true);
  assert.match(result.text, /^Council did not convene\./);
  assert.match(result.text, /COUNCIL_TIMEOUT_CONFIG_INVALID/);
  assert.equal(runner.calls.length, 0);
  assert.equal(existsSync(join(dir, "claims")), false, "refused before any claim was written");
});

// ---------------------------------------------------------------------------
// CTR-127 runtime-closure regressions.
//
// These are filesystem/static only: nothing here imports the real Council
// runtime, spawns council-ask, or touches the network. They pin the rule that
// the brief builder may load only from a dependency-complete root, because the
// live failure was a capture of a root that could not resolve zod.

function writeJson(path, value) {
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);
}

function fakeRelease(
  prefix,
  {
    releaseId = "rel-test00000000",
    zodVersion = "4.4.3",
    includeZod = true,
    includeSchemas = true,
    barrel = "export function validateDecisionBrief() {}\n",
  } = {},
) {
  const releaseDir = join(prefix, "releases", releaseId);
  mkdirSync(join(releaseDir, "dist", "brief"), { recursive: true });
  mkdirSync(join(releaseDir, "dist", "contracts"), { recursive: true });
  writeFileSync(join(releaseDir, "dist", "brief", "permitted-brief.js"), "export function assembleBrief() {}\n");
  writeFileSync(join(releaseDir, "dist", "contracts", "index.js"), barrel);
  writeFileSync(join(releaseDir, "dist", "index.js"), "export {};\n");
  if (includeSchemas) {
    writeFileSync(join(releaseDir, "dist", "contracts", "schemas.js"), "export {};\n");
  }
  writeJson(join(releaseDir, "package.json"), {
    name: "@example/council-runtime",
    version: "0.0.0",
    type: "module",
    dependencies: { zod: "4.4.3" },
  });
  if (includeZod) {
    mkdirSync(join(releaseDir, "node_modules", "zod"), { recursive: true });
    writeJson(join(releaseDir, "node_modules", "zod", "package.json"), {
      name: "zod",
      version: zodVersion,
      type: "module",
      exports: { ".": { import: "./index.js" } },
    });
    writeFileSync(join(releaseDir, "node_modules", "zod", "index.js"), "export {};\n");
  }
  mkdirSync(join(prefix, "receipts"), { recursive: true });
  mkdirSync(join(prefix, "bin"), { recursive: true });
  const receiptPath = join(prefix, "receipts", `${releaseId}.release.json`);
  writeJson(receiptPath, {
    schema: "wise-elders.council-runtime-release/v1",
    releaseId,
    artifactDigest: "a".repeat(64),
    sourceManifestDigest: "b".repeat(64),
  });
  const councilAskPath = join(prefix, "bin", "council-ask");
  writeFileSync(councilAskPath, "#!/bin/sh\nexit 0\n");
  writeJson(join(prefix, "active.json"), {
    schema: "wise-elders.council-runtime-active/v1",
    releaseId,
    releasePath: releaseDir,
    receiptPath,
    artifactDigest: "a".repeat(64),
    sourceManifestDigest: "b".repeat(64),
  });
  return { releaseDir, councilAskPath, receiptPath };
}

test("config omitting runtimeRoot is valid and follows the activated release", (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const { releaseDir, councilAskPath } = fakeRelease(dir);

  const config = configFor(join(dir, "state"), { runtimeRoot: "" });
  assert.equal(config.runtimeRoot, "", "an omitted override stays empty, not a guessed path");

  const resolved = resolveRuntimeRoot({ runtimeRoot: config.runtimeRoot, councilAskPath });
  assert.equal(resolved.ok, true, resolved.detail);
  assert.equal(resolved.source, "active.json");
  assert.equal(resolved.root, realpathSync(releaseDir));
  assert.equal(resolved.releaseId, "rel-test00000000");
});

test("an explicit dependency-complete runtimeRoot is accepted as the override", (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const { releaseDir } = fakeRelease(dir);

  const resolved = resolveRuntimeRoot({
    runtimeRoot: releaseDir,
    // Deliberately useless: an explicit override must not depend on active.json.
    councilAskPath: join(dir, "missing", "bin", "council-ask"),
  });

  assert.equal(resolved.ok, true, resolved.detail);
  assert.equal(resolved.source, "config");
  assert.equal(resolved.root, realpathSync(releaseDir));
});

test("an incomplete explicit runtimeRoot is refused, never silently replaced by the active release", (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const { councilAskPath } = fakeRelease(dir);
  const emptyRoot = join(dir, "empty-runtime");
  mkdirSync(emptyRoot, { recursive: true });

  const resolved = resolveRuntimeRoot({ runtimeRoot: emptyRoot, councilAskPath });

  assert.equal(resolved.ok, false);
  assert.equal(resolved.code, RUNTIME_UNRESOLVED_CODE);
  assert.match(resolved.detail, /not dependency-complete/);
  assert.match(resolved.detail, /dist\/brief\/permitted-brief\.js is missing/);
});

test("a captured-style root without node_modules/zod is refused", (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const { councilAskPath } = fakeRelease(dir, { includeZod: false });

  const resolved = resolveRuntimeRoot({ councilAskPath });

  assert.equal(resolved.ok, false);
  assert.equal(resolved.code, RUNTIME_UNRESOLVED_CODE);
  assert.match(resolved.detail, /node_modules\/zod\/package\.json is missing/);
});

test("a zod version that does not satisfy the runtime pin is refused", (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const { councilAskPath } = fakeRelease(dir, { zodVersion: "4.4.2" });

  const resolved = resolveRuntimeRoot({ councilAskPath });

  assert.equal(resolved.ok, false);
  assert.equal(resolved.code, RUNTIME_UNRESOLVED_CODE);
  assert.match(resolved.detail, /node_modules\/zod is 4\.4\.2, the runtime declares 4\.4\.3/);
});

test("a missing active.json is named in the refusal, not guessed around", (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  mkdirSync(join(dir, "bin"), { recursive: true });

  const resolved = resolveRuntimeRoot({ councilAskPath: join(dir, "bin", "council-ask") });

  assert.equal(resolved.ok, false);
  assert.equal(resolved.code, RUNTIME_UNRESOLVED_CODE);
  assert.match(resolved.detail, /no readable runtime activation record/);
  assert.match(resolved.detail, /active\.json/);
});

test("an activated release outside <prefix>/releases is refused by scope", (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const { councilAskPath, receiptPath } = fakeRelease(dir);
  const outside = join(dir, "outside-release");
  mkdirSync(outside, { recursive: true });
  writeJson(join(dir, "active.json"), {
    schema: "wise-elders.council-runtime-active/v1",
    releaseId: "outside-release",
    releasePath: outside,
    receiptPath,
    artifactDigest: "a".repeat(64),
    sourceManifestDigest: "b".repeat(64),
  });

  const resolved = resolveRuntimeRoot({ councilAskPath });

  assert.equal(resolved.ok, false);
  assert.equal(resolved.code, RUNTIME_UNRESOLVED_CODE);
  assert.match(resolved.detail, /is outside .*releases/);
});

test("a relative runtimeRoot is a config fault, not a path guess", () => {
  const base = {
    channel: "telegram",
    accountId: "acct-1",
    conversationId: "chat-1",
    senderIds: ["sender-1"],
    agentId: "council-agent",
    agentWorkspace: "/tmp/agent-workspace",
    councilAskPath: "/tmp/council-runtime/bin/council-ask",
    stateDir: "/tmp/council-state",
  };
  assert.equal(normalizeConfig(base).ok, true);
  assert.equal(normalizeConfig({ ...base, runtimeRoot: "relative/runtime" }).ok, false);
});

test("an unresolved runtime is a typed refusal: no spawn, no brief file", async (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const stateDir = join(dir, "state");
  const config = configFor(stateDir, { runtimeRoot: "" });
  const runner = fakeRunner({ stdout: SUCCESS });
  const { event, ctx } = inbound();

  const result = await handleInbound({
    event,
    ctx,
    config,
    deps: {
      spawn: runner,
      loadRuntime: async () => {
        throw new RuntimeUnresolvedError({
          detail: "runtime root is not dependency-complete",
          action: "Install the Council runtime, then send a new ask.",
        });
      },
      now: () => new Date("2026-10-29T12:00:00.000Z"),
    },
  });

  assert.equal(result.handled, true);
  assert.match(result.text, /^Council did not convene\./);
  assert.match(result.text, /COUNCIL_RUNTIME_UNRESOLVED/);
  assert.match(result.text, /Install the Council runtime/);
  assert.equal(runner.calls.length, 0, "no front door may start from an unresolved runtime");
  assert.equal(existsSync(join(stateDir, "briefs")), false, "no brief may be written");
});

// ---------------------------------------------------------------------------
// CTR-128 closure regressions: the emitted graph, not just file presence.

test("the module-specifier parser reads imports and never prose", () => {
  const source = [
    "// prose mentioning from 'nowhere.js'",
    "/* export * from './commented.js' */",
    "import { createHash } from 'node:crypto';",
    "import 'side-effect';",
    "export * from './errors.js';",
    "export {",
    "  a,",
    "  b,",
    "} from './generate.js';",
    "export type * from './types.js';",
    "const door = { note: \"read from 'memory.md'\" };",
    "const fake = 'export * from \\'./fake.js\\'';",
  ].join("\n");

  assert.deepEqual(
    moduleSpecifiers(source).map((one) => one.specifier),
    ["node:crypto", "side-effect", "./errors.js", "./generate.js", "./types.js"],
  );
});

test("an emitted barrel with extensionless relatives is refused before any import", (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const { councilAskPath } = fakeRelease(dir, { barrel: "export * from './errors';\n" });

  const resolved = resolveRuntimeRoot({ councilAskPath });

  assert.equal(resolved.ok, false);
  assert.equal(resolved.code, RUNTIME_UNRESOLVED_CODE);
  assert.match(
    resolved.detail,
    /dist\/contracts\/index\.js:1 imports \.\/errors with no file extension/,
  );
});

test("a relative import whose target is absent is refused", (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const { councilAskPath } = fakeRelease(dir, { barrel: "export * from './missing.js';\n" });

  const resolved = resolveRuntimeRoot({ councilAskPath });

  assert.equal(resolved.ok, false);
  assert.match(resolved.detail, /imports \.\/missing\.js, which does not exist/);
});

test("a barrel whose relatives carry extensions passes the static closure", (t) => {
  const dir = tempDir();
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const { councilAskPath } = fakeRelease(dir, { barrel: "export * from './schemas.js';\n" });

  const resolved = resolveRuntimeRoot({ councilAskPath });

  assert.equal(resolved.ok, true, resolved.detail);
  assert.deepEqual(runtimeClosureProblems(resolved.root, RUNTIME_CLOSURE_ENTRIES), []);
});

test("a binding file can never widen the account allowlist", () => {
  const binding = { telegram: { senderIds: ["sender-9"] } };

  assert.deepEqual(
    authorizedSenderSelection({ allowFrom: [] }, binding),
    { ok: false, code: "NO_AUTHORIZED_SENDERS" },
    "an empty allowFrom authorizes nobody, even with binding senders",
  );
  assert.deepEqual(
    authorizedSenderSelection({}, binding),
    { ok: false, code: "NO_AUTHORIZED_SENDERS" },
    "a missing allowFrom authorizes nobody",
  );
  assert.deepEqual(
    authorizedSenderSelection({ allowFrom: ["sender-1"] }, binding),
    { ok: false, code: "BINDING_SENDER_NOT_AUTHORIZED", outside: ["sender-9"] },
  );
  assert.deepEqual(
    authorizedSenderSelection({ allowFrom: ["sender-1", "sender-9"] }, binding),
    { ok: true, senderIds: ["sender-9"], source: "binding" },
  );
  assert.deepEqual(
    authorizedSenderSelection({ allowFrom: ["sender-1"] }, null),
    { ok: true, senderIds: ["sender-1"], source: "allowFrom" },
  );
});
