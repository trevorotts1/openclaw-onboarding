#!/usr/bin/env node
// CTR-194: official install/register/provision path for the deterministic
// council-before-dispatch interceptor.
//
// WHY THIS EXISTS. The extension shipped inside the skill but no install or
// update path ever copied it, registered its plugin id, or provisioned its
// per-box binding. An explicit Council ask therefore reached the model, which
// followed the task-routing policy and created a Command Center card instead of
// convening the Council. This script makes the package, the registry entry and
// the trusted binding one idempotent step, owned by wire.sh.
//
// WHAT IT DOES
//   1. copies the whole declared package over the existing extension directory
//      (no delete step, so box-owned extras survive);
//   2. checks the installed OpenClaw version against the package's own
//      openclaw.compat floor;
//   3. runs the package's provision.mjs against THIS box's config;
//   4. on READY, writes the exact derived entry, adds the extensions directory
//      to plugins.load.paths, and extends an EXISTING plugins.allow only;
//   5. on a binding refusal, DISABLES an existing entry instead of leaving it
//      on a stale binding, and reports the typed code.
//
// It never widens allowFrom, never creates an allowlist, never substitutes an
// operator identity, never touches a provider, model or credential, and never
// writes a temp path outside the OpenClaw root. Config writes are atomic and
// JSON-validated; `openclaw config validate` is honoured when the CLI is
// available, and a rejected candidate is rolled back byte-for-byte.
//
// Usage: node install-council-plugin.mjs --skill-dir DIR --openclaw-root DIR
//        --prefix DIR [--openclaw-cli PATH] [--openclaw-version X.Y.Z]
// Prints exactly one COUNCIL_PLUGIN line. Exit: 0 typed state, 2 usage.

import { cpSync, existsSync, mkdirSync, readFileSync, renameSync, statSync } from "node:fs";
import { openSync, closeSync, fsyncSync, writeSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { homedir } from "node:os";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const PLUGIN_ID = "council-before-dispatch";
const REQUIRED = [
  "index.js", "openclaw.plugin.json", "package.json", "lib/core.mjs",
  "lib/entry-validate.mjs", "lib/binding-predicate.mjs", "provision.mjs", "INSTALL.md", "CONTRACT.md",
];
const REQUIRED_FIELDS = [
  "channel", "accountId", "conversationId", "senderIds", "agentId",
  "agentWorkspace", "councilAskPath", "stateDir",
];
const OPTIONAL_FIELDS = [
  "mode", "displayTimezone", "maxQuestionChars", "maxMessageChars",
  "timeoutMs", "staleClaimMs",
];

function say(code, detail) {
  console.log(`COUNCIL_PLUGIN: ${code}${detail ? ` ${detail}` : ""}`);
}

function usage(message) {
  console.error(`COUNCIL_PLUGIN: NOT_READY PLUGIN_USAGE ${message}`);
  process.exit(2);
}

function parseArgs(argv) {
  const out = { skillDir: null, openclawRoot: null, prefix: null, openclawCli: null, openclawVersion: null, binding: null };
  for (let i = 0; i < argv.length; i += 1) {
    const take = (name) => {
      const v = argv[i + 1];
      if (!v || v.startsWith("--")) usage(`${name} requires a value`);
      i += 1;
      return v;
    };
    switch (argv[i]) {
      case "--skill-dir": out.skillDir = resolve(take(argv[i])); break;
      case "--openclaw-root": out.openclawRoot = resolve(take(argv[i])); break;
      case "--prefix": out.prefix = resolve(take(argv[i])); break;
      case "--openclaw-cli": out.openclawCli = resolve(take(argv[i])); break;
      case "--openclaw-version": out.openclawVersion = take(argv[i]); break;
      case "--binding": out.binding = resolve(take(argv[i])); break;
      default: usage(`unknown option ${argv[i]}`);
    }
  }
  if (!out.skillDir) usage("--skill-dir is required");
  if (!out.openclawRoot) usage("--openclaw-root is required");
  if (!out.prefix) out.prefix = join(out.openclawRoot, "council-runtime");
  return out;
}

function versionParts(value) {
  const m = String(value ?? "").match(/(\d+)\.(\d+)\.(\d+)/);
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
}

function versionAtLeast(have, need) {
  for (let i = 0; i < 3; i += 1) {
    if (have[i] > need[i]) return true;
    if (have[i] < need[i]) return false;
  }
  return true;
}

function findCli(explicit, openclawRoot) {
  if (explicit) return existsSync(explicit) ? explicit : null;
  const candidates = [
    process.env.COUNCIL_OPENCLAW,
    join(openclawRoot, "bin", "openclaw"),
    join(homedir(), ".local", "bin", "openclaw"),
    join(homedir(), ".npm-global", "bin", "openclaw"),
    "/opt/homebrew/bin/openclaw",
    "/usr/local/bin/openclaw",
    "/usr/bin/openclaw",
  ].filter(Boolean);
  for (const c of candidates) {
    if (existsSync(c)) return c;
  }
  for (const dir of String(process.env.PATH || "").split(":")) {
    if (!dir) continue;
    const c = join(dir, "openclaw");
    if (existsSync(c)) return c;
  }
  return null;
}

function detectVersion(cli, explicit) {
  if (explicit) return explicit;
  if (process.env.COUNCIL_OPENCLAW_VERSION) return process.env.COUNCIL_OPENCLAW_VERSION;
  if (!cli) return null;
  const r = spawnSync(cli, ["--version"], { encoding: "utf8", timeout: 30000 });
  if (r.status === 0) {
    const m = String(r.stdout || "").match(/\d+\.\d+\.\d+/);
    if (m) return m[0];
  }
  return null;
}

function atomicWrite(path, text) {
  const dir = dirname(path);
  mkdirSync(dir, { recursive: true });
  const tmp = join(dir, `.${PLUGIN_ID}.tmp.${process.pid}`);
  let mode = 0o600;
  try { mode = statSync(path).mode & 0o777; } catch { /* new file */ }
  const fd = openSync(tmp, "w", mode);
  try {
    writeSync(fd, text);
    fsyncSync(fd);
  } finally {
    closeSync(fd);
  }
  renameSync(tmp, path);
}

function validate(cli, cfgPath, openclawRoot) {
  if (!cli) return { ok: true, unverified: true };
  const r = spawnSync(cli, ["config", "validate"], {
    encoding: "utf8",
    timeout: 60000,
    env: { ...process.env, OPENCLAW_CONFIG_PATH: cfgPath, OPENCLAW_STATE_DIR: openclawRoot, OPENCLAW_ROOT: openclawRoot },
  });
  if (r.status === 0) return { ok: true, unverified: false };
  const line = String(r.stderr || r.stdout || "").trim().split("\n").filter(Boolean)[0] || `exit ${r.status}`;
  return { ok: false, unverified: false, detail: line };
}

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((k) => [k, stable(value[k])]));
  }
  return value;
}

function same(a, b) {
  return JSON.stringify(stable(a)) === JSON.stringify(stable(b));
}

function normalizePath(value) {
  if (typeof value !== "string" || !value) return value;
  if (value === "~") return homedir();
  if (value.startsWith("~/")) return join(homedir(), value.slice(2));
  return isAbsolute(value) ? value : resolve(value);
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const src = join(opts.skillDir, "extensions", PLUGIN_ID);
  const dst = join(opts.openclawRoot, "extensions", PLUGIN_ID);
  if (!existsSync(join(src, "package.json"))) {
    say("NOT_READY PLUGIN_INSTALL_FAILED", `distribution package missing at ${src}`);
    return 0;
  }

  // 1. Whole declared package over the existing directory; never delete extras.
  try {
    mkdirSync(dst, { recursive: true });
    cpSync(src, dst, {
      recursive: true,
      force: true,
      filter: (p) => {
        const rel = p.slice(src.length).replace(/^[\\/]+/, "");
        return rel !== "node_modules" && !rel.startsWith(".git");
      },
    });
  } catch (error) {
    say("NOT_READY PLUGIN_INSTALL_FAILED", `copy failed: ${String(error?.message ?? error).split("\n")[0]}`);
    return 0;
  }
  const missing = REQUIRED.filter((f) => !existsSync(join(dst, f)));
  if (missing.length > 0) {
    say("NOT_READY PLUGIN_INSTALL_FAILED", `package incomplete: ${missing.join(", ")}`);
    return 0;
  }

  // The validator ships with the package, so the install path and the verifier
  // share one definition of a valid existing entry.
  const { validateExistingEntry } = await import(pathToFileURL(join(dst, "lib", "entry-validate.mjs")).href);
  const pkg = JSON.parse(readFileSync(join(dst, "package.json"), "utf8"));
  const requiredVersion = pkg?.openclaw?.compat?.minGatewayVersion || pkg?.peerDependencies?.openclaw?.replace(/[^0-9.]/g, "") || "";
  const cli = findCli(opts.openclawCli, opts.openclawRoot);
  const haveRaw = detectVersion(cli, opts.openclawVersion);
  const have = versionParts(haveRaw);
  const need = versionParts(requiredVersion);

  // 2. Compatibility is checked, never assumed. No config is written on an
  // unknown or too-old gateway: an unloadable plugin must not be registered.
  if (!have) {
    say("NOT_READY PLUGIN_API_UNKNOWN", `installed OpenClaw version could not be read (required >=${requiredVersion || "unknown"}); plugin files copied, config untouched`);
    return 0;
  }
  if (!need || !versionAtLeast(have, need)) {
    say("NOT_READY PLUGIN_API_INCOMPATIBLE", `found ${haveRaw} required >=${requiredVersion}; plugin files copied, config untouched`);
    return 0;
  }

  const cfgPath = join(opts.openclawRoot, "openclaw.json");
  if (!existsSync(cfgPath)) {
    say("NOT_READY PLUGIN_BINDING_UNRESOLVED", `OPENCLAW_CONFIG_UNREADABLE no file at ${cfgPath}`);
    return 0;
  }
  const original = readFileSync(cfgPath, "utf8");
  let cfg;
  try {
    cfg = JSON.parse(original);
  } catch (error) {
    say("NOT_READY PLUGIN_BINDING_UNRESOLVED", `OPENCLAW_CONFIG_UNREADABLE ${String(error?.message ?? error).split("\n")[0]}`);
    return 0;
  }

  // 3. Provision against this box's own trusted config only.
  const provArgs = [
    join(dst, "provision.mjs"),
    "--openclaw-root", opts.openclawRoot,
    "--prefix", opts.prefix,
    "--json",
  ];
  // An explicit per-box binding is the documented way to settle a box with
  // several Telegram accounts or DMs. provision.mjs validates it against this
  // box and only ever narrows; the file never ships and is never synthesized.
  if (opts.binding) provArgs.push("--binding", opts.binding);
  const prov = spawnSync(process.execPath, provArgs, { encoding: "utf8", timeout: 90000 });

  let result = null;
  try {
    const raw = String(prov.stdout || "");
    result = JSON.parse(raw.slice(raw.indexOf("{"), raw.lastIndexOf("}") + 1));
  } catch {
    result = null;
  }

  if (cfg.plugins !== undefined && (cfg.plugins === null || typeof cfg.plugins !== "object")) {
    say("NOT_READY PLUGIN_CONFIG_INVALID", "plugins is not an object; refusing to replace it");
    return 0;
  }
  cfg.plugins = cfg.plugins && typeof cfg.plugins === "object" ? cfg.plugins : {};
  if (cfg.plugins.entries !== undefined && (cfg.plugins.entries === null || typeof cfg.plugins.entries !== "object" || Array.isArray(cfg.plugins.entries))) {
    say("NOT_READY PLUGIN_CONFIG_INVALID", "plugins.entries is not an object; refusing to replace it");
    return 0;
  }
  cfg.plugins.entries = cfg.plugins.entries && typeof cfg.plugins.entries === "object" ? cfg.plugins.entries : {};

  const disableExisting = (code) => {
    const entry = cfg.plugins.entries[PLUGIN_ID];
    if (entry && typeof entry === "object" && entry.enabled !== false) {
      cfg.plugins.entries[PLUGIN_ID] = { ...entry, enabled: false };
      const text = `${JSON.stringify(cfg, null, 2)}\n`;
      try {
        atomicWrite(cfgPath, text);
        const v = validate(cli, cfgPath, opts.openclawRoot);
        if (!v.ok) atomicWrite(cfgPath, original);
      } catch (error) {
        say("NOT_READY PLUGIN_CONFIG_INVALID", `could not disable the stale entry: ${String(error?.message ?? error).split("\n")[0]}`);
        return 0;
      }
    }
    say("NOT_READY", `${code} plugin files copied; any existing entry left disabled, no fallback identity used`);
    return 0;
  };

  // An existing, internally valid entry is authoritative. Re-derivation can be
  // ambiguous on a box with several Telegram accounts or DMs; that must not
  // disable a binding that already works (the operator box has four accounts
  // and three authorized DMs). Only a valid entry gets this protection.
  const existingEntry = cfg.plugins.entries[PLUGIN_ID];
  const existingCheck = existingEntry
    ? validateExistingEntry({ cfg, entry: existingEntry, openclawRoot: opts.openclawRoot, prefix: opts.prefix })
    : { ok: false, problems: ["no existing entry"] };
  let source = "derived";
  let rederive = null;
  if (!result || result.status !== "READY" || !result.entry) {
    const reason = result?.reasons?.[0];
    const code = reason?.code ? `PLUGIN_BINDING_UNRESOLVED ${reason.code}` : "PLUGIN_BINDING_UNRESOLVED";
    if (!existingCheck.ok) return disableExisting(code);
    source = "existing-binding";
    rederive = code;
  }

  // 4. Merge only the derived identity, preserving operator-set optional values.
  const derived = result?.status === "READY" && result.entry ? (result.entry.config ?? {}) : (existingEntry.config ?? {});
  const existing = cfg.plugins.entries[PLUGIN_ID] ?? {};
  const existingConfig = existing.config && typeof existing.config === "object" ? existing.config : {};
  // The schema is additionalProperties:false. Rebuild from the known fields so
  // a stale runtimeRoot or an old unknown key can never poison the entry.
  const nextConfig = {};
  for (const field of REQUIRED_FIELDS) nextConfig[field] = derived[field];
  for (const field of OPTIONAL_FIELDS) {
    nextConfig[field] = existingConfig[field] !== undefined ? existingConfig[field] : derived[field];
    if (nextConfig[field] === undefined) delete nextConfig[field];
  }
  cfg.plugins.entries[PLUGIN_ID] = { ...existing, enabled: true, config: nextConfig };

  if (cfg.plugins.load !== undefined && (cfg.plugins.load === null || typeof cfg.plugins.load !== "object")) {
    say("NOT_READY PLUGIN_CONFIG_INVALID", "plugins.load is not an object; refusing to replace it");
    return 0;
  }
  cfg.plugins.load = cfg.plugins.load && typeof cfg.plugins.load === "object" ? cfg.plugins.load : {};
  if (cfg.plugins.load.paths !== undefined && !Array.isArray(cfg.plugins.load.paths)) {
    say("NOT_READY PLUGIN_CONFIG_INVALID", "plugins.load.paths is not an array; refusing to replace it");
    return 0;
  }
  cfg.plugins.load.paths = Array.isArray(cfg.plugins.load.paths) ? cfg.plugins.load.paths : [];
  const extDir = join(opts.openclawRoot, "extensions");
  if (!cfg.plugins.load.paths.some((p) => normalizePath(p) === extDir)) {
    cfg.plugins.load.paths.push(extDir);
  }
  if (Array.isArray(cfg.plugins.allow) && !cfg.plugins.allow.includes(PLUGIN_ID)) {
    cfg.plugins.allow.push(PLUGIN_ID);
  }

  const before = JSON.parse(original);
  const unchanged = same(before, cfg);
  if (unchanged) {
    say("NOOP", `plugin=${PLUGIN_ID}@${pkg.version} api=${haveRaw} agent=${derived.agentId} senderCount=${derived.senderIds.length} source=${source}${rederive ? ` rederive=${rederive}` : ""} activation=next-gateway-start`);
    return 0;
  }

  const text = `${JSON.stringify(cfg, null, 2)}\n`;
  try {
    atomicWrite(cfgPath, text);
  } catch (error) {
    say("NOT_READY PLUGIN_CONFIG_INVALID", `write failed: ${String(error?.message ?? error).split("\n")[0]}`);
    return 0;
  }
  const v = validate(cli, cfgPath, opts.openclawRoot);
  if (!v.ok) {
    try { atomicWrite(cfgPath, original); } catch { /* reported below */ }
    say("NOT_READY PLUGIN_CONFIG_INVALID", `${v.detail}; previous config restored`);
    return 0;
  }
  say("READY", `plugin=${PLUGIN_ID}@${pkg.version} api=${haveRaw} agent=${derived.agentId} senderCount=${derived.senderIds.length} source=${source}${rederive ? ` rederive=${rederive}` : ""} activation=next-gateway-start${v.unverified ? " validation=unverified" : ""}`);
  return 0;
}

main().then((code) => process.exit(code)).catch((error) => {
  say("NOT_READY PLUGIN_INSTALL_FAILED", String(error?.message ?? error).split("\n")[0]);
  process.exit(0);
});
