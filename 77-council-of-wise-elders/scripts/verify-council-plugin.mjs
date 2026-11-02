#!/usr/bin/env node
// CTR-194: read-only readiness probe for the deterministic Council interceptor.
// Proves the installed package, the registry entry, the allow/load wiring, the
// per-box binding against provision.mjs, and the loaded plugin record. It
// writes nothing, starts nothing and calls no provider.
//
// Usage: node verify-council-plugin.mjs --openclaw-root DIR --prefix DIR
// Prints one JSON line:
//   {schema, status: READY|DEGRADED|NOT_READY, code, detail, checks:[...]}
// exit 0 READY/DEGRADED, 1 NOT_READY, 2 tooling (unreadable config).

import { existsSync, readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { homedir } from "node:os";
import { isAbsolute, join, resolve } from "node:path";

import { validateExistingEntry, REQUIRED_FIELDS as ENTRY_FIELDS } from "../extensions/council-before-dispatch/lib/entry-validate.mjs";

const PLUGIN_ID = "council-before-dispatch";
const REQUIRED = ["index.js", "openclaw.plugin.json", "package.json", "lib/core.mjs", "lib/entry-validate.mjs", "lib/binding-predicate.mjs", "provision.mjs"];

function parseArgs(argv) {
  const out = { openclawRoot: null, prefix: null };
  for (let i = 0; i < argv.length; i += 1) {
    const v = argv[i + 1];
    if (!v) break;
    if (argv[i] === "--openclaw-root") { out.openclawRoot = resolve(v); i += 1; }
    else if (argv[i] === "--prefix") { out.prefix = resolve(v); i += 1; }
  }
  return out;
}

function normalizePath(value) {
  if (typeof value !== "string" || !value) return value;
  if (value === "~") return homedir();
  if (value.startsWith("~/")) return join(homedir(), value.slice(2));
  return isAbsolute(value) ? value : resolve(value);
}

function isWildcard(value) {
  const s = String(value).trim().toLowerCase();
  return s === "*" || s === "all" || s === "any" || s.includes("*");
}

function findCli(openclawRoot) {
  const candidates = [
    process.env.COUNCIL_OPENCLAW,
    join(openclawRoot, "bin", "openclaw"),
    join(homedir(), ".local", "bin", "openclaw"),
    join(homedir(), ".npm-global", "bin", "openclaw"),
    "/opt/homebrew/bin/openclaw",
    "/usr/local/bin/openclaw",
    "/usr/bin/openclaw",
  ].filter(Boolean);
  for (const c of candidates) if (existsSync(c)) return c;
  for (const dir of String(process.env.PATH || "").split(":")) {
    if (!dir) continue;
    const c = join(dir, "openclaw");
    if (existsSync(c)) return c;
  }
  return null;
}

function loadedRecord(cli, openclawRoot) {
  if (!cli) return { known: false, detail: "openclaw CLI not found" };
  const r = spawnSync(cli, ["plugins", "list", "--json"], {
    encoding: "utf8",
    timeout: 60000,
    env: { ...process.env, OPENCLAW_ROOT: openclawRoot, OPENCLAW_STATE_DIR: openclawRoot },
  });
  if (r.status !== 0) return { known: false, detail: `plugins list exited ${r.status}` };
  let parsed;
  try { parsed = JSON.parse(r.stdout); } catch { return { known: false, detail: "plugins list output unreadable" }; }
  const plugins = Array.isArray(parsed?.plugins) ? parsed.plugins : [];
  const rec = plugins.find((p) => p?.id === PLUGIN_ID);
  if (!rec) return { known: true, loaded: false, detail: "plugin id absent from the loaded registry" };
  if (rec.enabled !== true) return { known: true, loaded: false, detail: "registry record is disabled" };
  if (rec.status !== "loaded") return { known: true, loaded: false, detail: `registry status is ${rec.status ?? "unknown"}` };
  return { known: true, loaded: true, detail: `status=loaded version=${rec.version ?? "unknown"} origin=${rec.origin ?? "unknown"}` };
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  const openclawRoot = opts.openclawRoot || join(homedir(), ".openclaw");
  const prefix = opts.prefix || join(openclawRoot, "council-runtime");
  const pluginDir = join(openclawRoot, "extensions", PLUGIN_ID);
  const cfgPath = join(openclawRoot, "openclaw.json");
  const checks = [];
  const fail = (code, detail) => {
    checks.push({ result: "FAIL", code, detail });
    return { schema: "council-plugin-box/v1", status: "NOT_READY", code, detail, checks };
  };

  const missing = REQUIRED.filter((f) => !existsSync(join(pluginDir, f)));
  if (missing.length > 0) return fail("PLUGIN_NOT_INSTALLED", `${pluginDir} missing ${missing.join(", ")}`);
  checks.push({ result: "PASS", code: "PLUGIN_PACKAGE", detail: `${pluginDir} holds the declared runtime files` });

  let cfg;
  try { cfg = JSON.parse(readFileSync(cfgPath, "utf8")); }
  catch (error) {
    console.log(JSON.stringify({ schema: "council-plugin-box/v1", status: "UNDETERMINED", code: "OPENCLAW_CONFIG_UNREADABLE", detail: String(error?.message ?? error) }));
    process.exit(2);
  }

  const plugins = cfg.plugins && typeof cfg.plugins === "object" ? cfg.plugins : {};
  const entry = plugins.entries && typeof plugins.entries === "object" ? plugins.entries[PLUGIN_ID] : null;
  if (!entry || entry.enabled !== true) {
    return fail("PLUGIN_NOT_REGISTERED", `plugins.entries.${PLUGIN_ID} is missing or not enabled`);
  }
  checks.push({ result: "PASS", code: "PLUGIN_REGISTERED", detail: `plugins.entries.${PLUGIN_ID}.enabled=true` });

  if (Array.isArray(plugins.allow) && !plugins.allow.includes(PLUGIN_ID)) {
    return fail("PLUGIN_NOT_ALLOWED", `plugins.allow exists and does not list ${PLUGIN_ID}`);
  }
  checks.push({ result: "PASS", code: "PLUGIN_ALLOWED", detail: Array.isArray(plugins.allow) ? "present in plugins.allow" : "no plugins.allow list on this box" });

  const extDir = join(openclawRoot, "extensions");
  const paths = Array.isArray(plugins.load?.paths) ? plugins.load.paths : [];
  if (!paths.some((p) => normalizePath(p) === extDir)) {
    return fail("PLUGIN_LOAD_PATH_MISSING", `plugins.load.paths does not contain ${extDir}`);
  }
  checks.push({ result: "PASS", code: "PLUGIN_LOAD_PATH", detail: extDir });

  const shared = validateExistingEntry({ cfg, entry, openclawRoot, prefix });
  if (!shared.ok) return fail("PLUGIN_BINDING_UNRESOLVED", shared.problems.join("; "));
  checks.push({ result: "PASS", code: "PLUGIN_BINDING_SHARED", detail: "entry-validate.mjs agrees with this box" });

  const config = entry.config && typeof entry.config === "object" ? entry.config : {};

  // An existing, internally valid binding is authoritative. Re-derivation can
  // be ambiguous on a box with several accounts or DMs, and that must not turn
  // a working box into NOT_READY (the operator box has four accounts).
  const existing = validateExistingEntry({ cfg, entry, openclawRoot, prefix });
  if (existing.ok) {
    checks.push({ result: "PASS", code: "PLUGIN_BINDING_SHAPE", detail: `agent=${config.agentId} senderCount=${Array.isArray(config.senderIds) ? config.senderIds.length : 0}` });
  }

  const binding = join(openclawRoot, "council-before-dispatch", "binding.json");
  const provArgs = [
    join(pluginDir, "provision.mjs"),
    "--openclaw-root", openclawRoot,
    "--prefix", prefix,
    "--json",
  ];
  if (existsSync(binding)) provArgs.push("--binding", binding);
  const prov = spawnSync(process.execPath, provArgs, { encoding: "utf8", timeout: 90000 });
  let result = null;
  try {
    const raw = String(prov.stdout || "");
    result = JSON.parse(raw.slice(raw.indexOf("{"), raw.lastIndexOf("}") + 1));
  } catch { result = null; }
  if (!result || result.status !== "READY" || !result.entry) {
    const reason = result?.reasons?.[0];
    if (existing.ok) {
      // The registry entry is valid; only automatic re-derivation is blocked
      // (several accounts/DMs). The per-box binding file can settle it.
      checks.push({ result: "PASS", code: "PLUGIN_BINDING", detail: `existing registry binding is valid; re-derivation: ${reason?.code ?? "not ready"}` });
    } else {
      return fail("PLUGIN_BINDING_UNRESOLVED",
        `${reason?.code ? `${reason.code}: ${reason.detail}` : "existing entry is invalid and provision did not return READY"}; existing problems: ${existing.problems.join("; ")}`);
    }
  } else {
    const derived = result.entry.config ?? {};
    const drift = ENTRY_FIELDS.filter((field) => JSON.stringify(config[field]) !== JSON.stringify(derived[field]));
    if (existing.ok) {
      checks.push({ result: "PASS", code: "PLUGIN_BINDING", detail: drift.length > 0
        ? `existing registry binding is valid; re-derivation differs on ${drift.join(", ")} and the existing binding is kept`
        : "registry config matches provision.mjs for this box" });
    } else {
      return fail("PLUGIN_BINDING_DRIFT", `existing entry is invalid (${existing.problems.join("; ")}); wire.sh would write ${drift.join(", ") || "the derived binding"}`);
    }
  }

  const loaded = loadedRecord(findCli(openclawRoot), openclawRoot);
  if (!loaded.known) {
    checks.push({ result: "WARN", code: "PLUGIN_HOOK_UNVERIFIED", detail: loaded.detail });
    return { schema: "council-plugin-box/v1", status: "DEGRADED", code: "PLUGIN_HOOK_UNVERIFIED", detail: loaded.detail, checks };
  }
  if (!loaded.loaded) return fail("PLUGIN_NOT_LOADED", loaded.detail);
  checks.push({ result: "PASS", code: "PLUGIN_HOOK", detail: loaded.detail });
  return { schema: "council-plugin-box/v1", status: "READY", code: "OK", detail: "plugin package, registry, binding and loaded hook verified", checks };
}

const result = main();
console.log(JSON.stringify(result));
process.exit(result.status === "NOT_READY" ? 1 : 0);
