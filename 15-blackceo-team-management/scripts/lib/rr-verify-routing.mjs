#!/usr/bin/env node
/**
 * RR-032 routing acceptance verifier.
 *
 * Field presence is not routing. This runs the ACTUAL resolver shipped with the
 * installed OpenClaw, against the candidate configuration, and asserts the
 * resolved agent + session key for each operator DM and for the client owner.
 *
 * Fail-closed: if the installed resolver cannot be located or imported, the
 * verifier exits non-zero. It never falls back to a field-presence assertion.
 *
 * Usage:
 *   node rr-verify-routing.mjs --config <candidate.json> --module <routing.js> \
 *        [--operator-id N]... [--owner-id N] [--json]
 */
import { pathToFileURL } from "node:url";
import { readFileSync, existsSync } from "node:fs";

function parseArgs(argv) {
  const out = { operators: [], owner: null, channel: "telegram", account: "default" };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--config") out.config = argv[++i];
    else if (a === "--module") out.module = argv[++i];
    else if (a === "--operator-id") out.operators.push(argv[++i]);
    else if (a === "--owner-id") out.owner = argv[++i];
    else if (a === "--channel") out.channel = argv[++i];
    else if (a === "--account") out.account = argv[++i];
    else if (a === "--json") out.json = true;
  }
  return out;
}

function fail(reason, detail) {
  process.stdout.write(JSON.stringify({
    rr: "RR-032", verdict: "BLOCKED", reason, detail,
    note: "routing acceptance could not be executed against the real resolver",
  }, null, 2) + "\n");
  process.exit(2);
}

const args = parseArgs(process.argv.slice(2));
if (!args.config) fail("missing --config", "no candidate supplied");
if (!args.module) fail("missing --module", "no resolver module supplied; refusing to assert on field presence");
if (!existsSync(args.module)) fail("resolver-module-absent", args.module);
if (!existsSync(args.config)) fail("candidate-absent", args.config);

let routing;
try {
  routing = await import(pathToFileURL(args.module).href);
} catch (err) {
  fail("resolver-import-failed", String(err && err.message ? err.message : err));
}
if (typeof routing.resolveAgentRoute !== "function") {
  fail("resolver-has-no-resolveAgentRoute", Object.keys(routing).join(","));
}

let cfg;
try {
  cfg = JSON.parse(readFileSync(args.config, "utf8"));
} catch (err) {
  fail("candidate-unparseable", String(err && err.message ? err.message : err));
}

const defaultAgentId = (() => {
  const agents = cfg.agents;
  if (agents && typeof agents === "object") {
    if (agents.entries && typeof agents.entries === "object") {
      const ids = Object.keys(agents.entries);
      if (ids.includes("main")) return "main";
      if (ids.length > 0) return ids[0];
    }
    if (Array.isArray(agents.list) && agents.list.length > 0) {
      const main = agents.list.find((a) => a && a.id === "main");
      return main ? "main" : agents.list[0].id;
    }
  }
  return "main";
})();

const checks = [];
function check(name, expected, subject) {
  let route;
  try {
    route = routing.resolveAgentRoute({
      cfg,
      channel: args.channel,
      accountId: args.account,
      peer: { kind: "direct", id: subject.id },
      defaultAgentId,
    });
  } catch (err) {
    checks.push({ name, subject: subject.id, ok: false, expected,
                  detail: "resolver threw: " + (err && err.message ? err.message : String(err)) });
    return;
  }
  const ok = route.agentId === expected.agentId &&
             (!expected.sessionKey || route.sessionKey === expected.sessionKey) &&
             (!expected.matchedBy || route.matchedBy === expected.matchedBy);
  checks.push({ name, subject: subject.id, ok, expected,
                actual: { agentId: route.agentId, sessionKey: route.sessionKey,
                          matchedBy: route.matchedBy, dmScope: route.dmScope } });
}

for (const id of args.operators) {
  check("operator DM routes to remote-rescue in its own session", {
    agentId: "remote-rescue", sessionKey: `agent:remote-rescue:direct:${id}`,
    matchedBy: "binding.peer",
  }, { id });
}

if (args.owner) {
  check("client owner DM stays on the owner agent, not the rescue agent", {
    agentId: "main", sessionKey: "agent:main:main", matchedBy: "default",
  }, { id: args.owner });
}

const failed = checks.filter((c) => !c.ok);
const out = {
  rr: "RR-032",
  verdict: failed.length === 0 ? "PASS" : "FAIL",
  resolver: args.module,
  defaultAgentId,
  checks,
  failed: failed.length,
  note: failed.length === 0
    ? "every operator DM resolved to remote-rescue by binding.peer; owner resolved to the owner agent"
    : "resolved routing does not match the required isolation",
};
process.stdout.write(JSON.stringify(out, null, 2) + "\n");
process.exit(failed.length === 0 ? 0 : 1);
