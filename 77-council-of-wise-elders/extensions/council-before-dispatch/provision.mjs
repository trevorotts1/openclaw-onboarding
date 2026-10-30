#!/usr/bin/env node
// council-before-dispatch — per-box provisioning (portable source).
//
// Reads ONLY this box's own trusted config and prints the exact plugin entry
// this box may use. It writes nothing: it never edits openclaw.json, never
// enables a plugin, never touches credentials, providers, models or auth.
//
// Identity rules (no hardcoded ids, ever):
//   accountId      <- the selected Telegram binding's match.accountId, or an
//                     explicit --account that names an existing account.
//                     If neither is available the result is NOT_READY.
//   conversationId <- the selected binding's match.peer (one DM binding only).
//   senderIds      <- that account's own allowFrom list. Never "everyone": an
//                     empty or missing allowFrom is NOT_READY, not "any sender".
//   agentId        <- an agent that has a Telegram DM binding, or --agent.
//   agentWorkspace <- that agent's own workspace from agents.entries.
//   runtimeRoot    <- NOT emitted. The plugin core resolves the activated
//                     release from <prefix>/active.json itself, so a rollback or
//                     re-activation is honoured without rewriting this config.
//                     Provision only VALIDATES that record and its static
//                     closure here; an explicit runtimeRoot stays available as
//                     a diagnostic override, never the primary binding.
//
// A binding file (--binding) is the explicit per-box authorization surface for
// the cases config cannot settle unambiguously. It is validated against config;
// a disagreement is a typed NOT_READY, never a silent merge.
//
// Readiness is honest: status READY means "the config this box states is
// self-consistent and the runtime closure files are present". It is NOT a claim
// that a Telegram ask works, and runtime closure is static metadata only.
//
// Usage:
//   node provision.mjs [--openclaw-root DIR] [--prefix DIR] [--agent ID]
//                      [--account ID] [--conversation ID] [--binding FILE]
//                      [--timezone IANA] [--json] [--help]
// Exit codes: 0 READY, 1 NOT_READY, 2 usage/config-unreadable.

import { existsSync, readFileSync, realpathSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { isAbsolute, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { RUNTIME_CLOSURE_ENTRIES, runtimeClosureProblems } from "./lib/core.mjs";

const SCHEMA = "blackceo.council-before-dispatch.provision/v1";
const BINDING_SCHEMA = "blackceo.council-before-dispatch.binding/v1";

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function parseArgs(argv) {
  const options = {
    openclawRoot: process.env.OPENCLAW_ROOT ? resolve(process.env.OPENCLAW_ROOT) : join(homedir(), ".openclaw"),
    prefix: null,
    agent: null,
    account: null,
    conversation: null,
    binding: null,
    timezone: null,
    json: false,
    help: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const take = (name) => {
      const value = argv[i + 1];
      if (!value || value.startsWith("--")) throw new Error(`${name} requires a value`);
      i += 1;
      return value;
    };
    switch (arg) {
      case "--openclaw-root": options.openclawRoot = resolve(take(arg)); break;
      case "--prefix": options.prefix = resolve(take(arg)); break;
      case "--agent": options.agent = take(arg); break;
      case "--account": options.account = take(arg); break;
      case "--conversation": options.conversation = take(arg); break;
      case "--binding": options.binding = resolve(take(arg)); break;
      case "--timezone": options.timezone = take(arg); break;
      case "--json": options.json = true; break;
      case "--help":
      case "-h": options.help = true; break;
      default: throw new Error(`unknown option: ${arg}`);
    }
  }
  options.prefix = options.prefix ?? join(options.openclawRoot, "council-runtime");
  return options;
}

const HELP = [
  "Usage: node provision.mjs [options]",
  "  --openclaw-root <dir>   OpenClaw config root (default $OPENCLAW_ROOT or ~/.openclaw)",
  "  --prefix <dir>          council-runtime prefix holding active.json (default <root>/council-runtime)",
  "  --agent <id>            calling agent (default: derived, must be unambiguous)",
  "  --account <id>          telegram account id (default: derived from the binding)",
  "  --conversation <id>     DM chat id (default: derived from the binding peer)",
  "  --binding <file>        explicit per-box authorization binding (JSON)",
  "  --timezone <IANA>       displayTimezone (default: this process's resolved zone, else UTC)",
  "  --json                  machine-readable (the only output format)",
  "Prints a plugins entry for this box, or a typed NOT_READY. Writes nothing.",
].join("\n");

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function stringList(value) {
  if (!Array.isArray(value)) return [];
  const out = [];
  for (const item of value) {
    if (typeof item !== "string") continue;
    const trimmed = item.trim();
    if (trimmed && !out.includes(trimmed)) out.push(trimmed);
  }
  return out;
}

/**
 * The authorized sender set for one account.
 *
 * The account's own allowFrom is the only source of authorization: an empty or
 * missing list authorizes nobody, and a binding file may only narrow the set to
 * a subset of it. A binding list can never widen authorization, not even when
 * allowFrom is empty. A wildcard entry (*, all, any, or any entry containing *)
 * is never expanded: it authorizes nothing.
 *
 * Returns { ok: true, senderIds, source } or { ok: false, code, outside? }.
 */
export function isWildcardEntry(entry) {
  const normalized = String(entry).trim().toLowerCase();
  return normalized === "*" || normalized === "all" || normalized === "any" || normalized.includes("*");
}

export function authorizedSenderSelection(account, binding) {
  const entries = stringList(account?.allowFrom);
  if (entries.some(isWildcardEntry)) return { ok: false, code: "ACCOUNT_ALLOWLIST_WILDCARD" };
  const allowed = entries;
  if (allowed.length === 0) return { ok: false, code: "NO_AUTHORIZED_SENDERS" };
  const explicit = stringList(binding?.telegram?.senderIds);
  if (explicit.length === 0) return { ok: true, senderIds: allowed, source: "allowFrom" };
  const outside = explicit.filter((id) => !allowed.includes(id));
  if (outside.length > 0) return { ok: false, code: "BINDING_SENDER_NOT_AUTHORIZED", outside };
  return { ok: true, senderIds: explicit, source: "binding" };
}

function telegramBindings(bindings, agentId) {
  return bindings.filter(
    (binding) =>
      isPlainObject(binding) &&
      binding.agentId === agentId &&
      isPlainObject(binding.match) &&
      binding.match.channel === "telegram"
  );
}

/**
 * Static closure check of an activated release. Mirrors the installer's
 * dependency receipt shape, but never imports or executes anything: a pass is
 * file presence and metadata agreement only, and is reported as such.
 */
function inspectRuntimeClosure(releasePath) {
  const problems = [];
  const closureFiles = RUNTIME_CLOSURE_ENTRIES;
  for (const relativePath of closureFiles) {
    if (!existsSync(join(releasePath, ...relativePath.split("/")))) {
      problems.push({ code: "RUNTIME_ENTRY_MISSING", detail: relativePath });
    }
  }
  if (!existsSync(join(releasePath, "dist", "contracts"))) {
    problems.push({ code: "RUNTIME_CONTRACTS_MISSING", detail: "dist/contracts" });
  }
  const packagePath = join(releasePath, "package.json");
  const dependencies = [];
  if (!existsSync(packagePath)) {
    problems.push({ code: "RUNTIME_PACKAGE_JSON_MISSING", detail: packagePath });
  } else {
    try {
      const pkg = readJson(packagePath);
      for (const name of Object.keys(pkg.dependencies ?? {}).sort()) {
        const installed = join(releasePath, "node_modules", ...name.split("/"), "package.json");
        if (!existsSync(installed)) {
          problems.push({ code: "RUNTIME_DEPENDENCY_MISSING", detail: `${name} (${installed})` });
        } else {
          dependencies.push(`${name}@${readJson(installed).version ?? "unknown"}`);
        }
      }
    } catch (error) {
      problems.push({ code: "RUNTIME_PACKAGE_JSON_UNREADABLE", detail: String(error.message ?? error) });
    }
  }
  if (!existsSync(join(releasePath, "package-lock.json"))) {
    problems.push({ code: "RUNTIME_LOCK_MISSING", detail: join(releasePath, "package-lock.json") });
  }
  // Presence is not loadability. The plugin imports these entries with plain
  // Node ESM, so the emitted graph itself must resolve: every relative
  // specifier carries an extension, every target exists, every bare package is
  // installed. Static text and file existence only; nothing is imported.
  for (const problem of runtimeClosureProblems(releasePath, RUNTIME_CLOSURE_ENTRIES)) {
    problems.push({ code: "RUNTIME_IMPORT_UNRESOLVED", detail: problem });
  }
  return { problems, dependencies };
}

function looksLikeSkillTree(path) {
  // update-skills.sh rewrites numbered skill trees; a runtime there is not a
  // dependency-complete, update-durable root.
  return path.split(/[\\/]/).some((segment) => /^\d\d-[a-z0-9-]+$/.test(segment));
}

function main(argv) {
  let options;
  try {
    options = parseArgs(argv);
  } catch (error) {
    console.error(`FAIL ${error.message}`);
    return 2;
  }
  if (options.help) {
    console.log(HELP);
    return 0;
  }

  const reasons = [];
  const notReady = (code, detail, action) => {
    reasons.push({ code, detail, action });
    return null;
  };
  const derivation = [];

  const configPath = join(options.openclawRoot, "openclaw.json");
  let config;
  try {
    config = readJson(configPath);
  } catch (error) {
    console.log(JSON.stringify({
      schema: SCHEMA,
      status: "NOT_READY",
      readiness: "not_ready",
      reasons: [{
        code: "OPENCLAW_CONFIG_UNREADABLE",
        detail: `cannot read ${configPath}: ${String(error.message ?? error)}`,
        action: "Run provision on the box itself, or pass --openclaw-root.",
      }],
      entry: null,
    }, null, 2));
    return 1;
  }

  const telegram = isPlainObject(config.channels?.telegram) ? config.channels.telegram : null;
  const accounts = isPlainObject(telegram?.accounts) ? telegram.accounts : {};
  const agents = isPlainObject(config.agents?.entries) ? config.agents.entries : {};
  const bindings = Array.isArray(config.bindings) ? config.bindings : [];

  if (!telegram) {
    notReady("TELEGRAM_CHANNEL_ABSENT", "channels.telegram is not configured on this box",
      "Nothing to bind. Do not install the plugin on a box with no Telegram channel.");
  }
  if (telegram && telegram.enabled === false) {
    notReady("TELEGRAM_CHANNEL_DISABLED", "channels.telegram.enabled is false",
      "Enable Telegram through the supported installer; provision will not change it.");
  }

  // ---- explicit binding file (optional) ----
  let binding = null;
  if (options.binding) {
    try {
      binding = readJson(options.binding);
    } catch (error) {
      notReady("BINDING_UNREADABLE", `cannot read ${options.binding}: ${String(error.message ?? error)}`,
        "Fix the binding file path or omit --binding to derive from config.");
    }
    if (binding && binding.schema !== BINDING_SCHEMA) {
      notReady("BINDING_SCHEMA_MISMATCH", `binding schema is ${JSON.stringify(binding.schema)}, expected ${BINDING_SCHEMA}`,
        "Use the schema documented in extensions/council-before-dispatch/INSTALL.md.");
      binding = null;
    }
  }

  // ---- agent ----
  const explicitAgent = binding?.agent?.id ?? options.agent ?? null;
  let agentId = explicitAgent;
  if (!agentId) {
    const candidates = Object.keys(agents).filter((id) =>
      telegramBindings(bindings, id).some((one) => typeof one.match.peer === "string" || typeof one.match.peer === "number")
    );
    if (candidates.length === 1) {
      agentId = candidates[0];
      derivation.push({ field: "agentId", source: "single telegram DM binding", value: agentId });
    } else if (candidates.length === 0) {
      notReady("NO_TELEGRAM_DM_BINDING", "no agent has a telegram binding carrying match.peer",
        "Pass --agent for the intended calling agent, or add the box's own DM binding through the supported routing config.");
    } else {
      notReady("AMBIGUOUS_AGENT", `more than one agent has a telegram DM binding: ${candidates.join(", ")}`,
        "Pass --agent (one of those ids) or --binding.");
    }
  } else if (!agents[agentId]) {
    notReady("AGENT_NOT_FOUND", `agent ${agentId} is not in agents.entries`,
      "Pass the exact id from this box's agents.entries.");
  } else {
    derivation.push({ field: "agentId", source: binding ? "binding file" : "operator flag", value: agentId });
  }

  // ---- agent workspace ----
  let agentWorkspace = null;
  if (agentId && agents[agentId]) {
    const workspace = agents[agentId].workspace;
    // Same absolute-path contract the plugin's own config validator applies;
    // "~" is expanded, anything else non-absolute is a config fault.
    const expanded = typeof workspace === "string"
      ? (workspace === "~" ? homedir() : workspace.startsWith("~/") ? join(homedir(), workspace.slice(2)) : workspace)
      : "";
    if (expanded && isAbsolute(expanded)) {
      agentWorkspace = resolve(expanded);
      derivation.push({ field: "agentWorkspace", source: `agents.entries.${agentId}.workspace`, value: agentWorkspace });
    } else {
      notReady("AGENT_WORKSPACE_MISSING", `agents.entries.${agentId}.workspace is missing or not absolute`,
        "Set the agent workspace through the supported onboarding flow; provision will not invent one.");
    }
  }
  if (binding?.agent?.workspace && agentWorkspace && resolve(binding.agent.workspace) !== agentWorkspace) {
    notReady("BINDING_CONFLICT", `binding agent.workspace ${binding.agent.workspace} != config ${agentWorkspace}`,
      "Correct the binding file or the box config. Provision will not override either.");
  }

  // ---- conversation + account from the trusted binding ----
  const agentTelegram = agentId ? telegramBindings(bindings, agentId) : [];
  const peerBindings = agentTelegram.filter(
    (one) => typeof one.match.peer === "string" || typeof one.match.peer === "number"
  );
  const explicitConversation = binding?.telegram?.conversationId ?? options.conversation ?? null;
  let conversationId = explicitConversation ? String(explicitConversation).trim() : null;
  if (!conversationId) {
    if (peerBindings.length === 1) {
      conversationId = String(peerBindings[0].match.peer);
      derivation.push({ field: "conversationId", source: `bindings[agentId=${agentId}].match.peer`, value: conversationId });
    } else if (peerBindings.length === 0) {
      notReady("NO_DM_BINDING", `agent ${agentId} has no telegram binding carrying match.peer`,
        "Add the DM binding through the supported routing config, or pass --conversation with the box's own DM chat id.");
    } else {
      notReady("AMBIGUOUS_CONVERSATION",
        `agent ${agentId} has ${peerBindings.length} telegram peer bindings: ${peerBindings.map((one) => String(one.match.peer)).join(", ")}`,
        "Pass --conversation (the DM chat id) or --binding. A group chat is never a Council DM.");
    }
  } else {
    derivation.push({ field: "conversationId", source: binding ? "binding file" : "operator flag", value: conversationId });
  }

  const explicitAccount = binding?.telegram?.accountId ?? options.account ?? null;
  const boundAccounts = [...new Set(agentTelegram
    .map((one) => (typeof one.match.accountId === "string" ? one.match.accountId : null))
    .filter(Boolean))];
  let accountId = explicitAccount ? String(explicitAccount).trim() : (boundAccounts.length === 1 ? boundAccounts[0] : null);
  if (!accountId) {
    notReady("AMBIGUOUS_ACCOUNT",
      boundAccounts.length === 0
        ? `agent ${agentId}'s telegram bindings record no match.accountId and this box has ${Object.keys(accounts).length} telegram account(s): ${Object.keys(accounts).sort().join(", ")}`
        : `agent ${agentId}'s telegram bindings name more than one account: ${boundAccounts.join(", ")}`,
      "Pass --account with the exact account id from this box's channels.telegram.accounts, or use --binding.");
  } else if (!accounts[accountId]) {
    notReady("ACCOUNT_NOT_FOUND", `telegram account ${accountId} is not in channels.telegram.accounts`,
      "Pass an account id that exists on this box.");
  } else {
    derivation.push({ field: "accountId", source: explicitAccount ? (binding ? "binding file" : "operator flag") : "binding match.accountId", value: accountId });
    const account = accounts[accountId];
    if (isPlainObject(account) && account.enabled === false) {
      notReady("ACCOUNT_DISABLED", `channels.telegram.accounts.${accountId}.enabled is false`,
        "Enable the account through the supported installer; provision will not change it.");
    }
  }

  // ---- authorized senders: only the account's own allowFrom ----
  let senderIds = [];
  if (accountId && accounts[accountId]) {
    // The account's own allowFrom is the ONLY source of authorization. An empty
    // allowFrom authorizes nobody, so a binding file cannot widen it: the
    // binding may only narrow the list to a subset.
    const selection = authorizedSenderSelection(accounts[accountId], binding);
    if (!selection.ok && selection.code === "ACCOUNT_ALLOWLIST_WILDCARD") {
      notReady("ACCOUNT_ALLOWLIST_WILDCARD",
        `channels.telegram.accounts.${accountId}.allowFrom contains a wildcard entry`,
        "Replace the wildcard with the exact sender ids this account may answer. Provision never expands a wildcard.");
    } else if (!selection.ok && selection.code === "BINDING_SENDER_NOT_AUTHORIZED") {
      notReady("BINDING_SENDER_NOT_AUTHORIZED",
        `binding senderIds not present in channels.telegram.accounts.${accountId}.allowFrom: ${selection.outside.join(", ")}`,
        "Add the sender through the supported Telegram allowlist flow. Provision never widens authorization.");
    } else if (!selection.ok) {
      notReady("NO_AUTHORIZED_SENDERS",
        `channels.telegram.accounts.${accountId}.allowFrom is empty or missing`,
        "Authorize the sender through the supported Telegram allowlist flow. Provision never installs an all-sender capture.");
    } else {
      senderIds = selection.senderIds;
      derivation.push({
        field: "senderIds",
        source: selection.source === "binding"
          ? "binding file (subset of account allowFrom)"
          : `channels.telegram.accounts.${accountId}.allowFrom`,
        value: senderIds.join(","),
      });
    }
  }

  // ---- runtime root: active.json only, static closure ----
  let runtimeRoot = null;
  const activePath = join(options.prefix, "active.json");
  if (!existsSync(activePath)) {
    notReady("RUNTIME_NOT_ACTIVATED", `no active release receipt at ${activePath}`,
      "Run the skill's install-runtime.mjs for this box, then re-run provision.");
  } else {
    try {
      const active = readJson(activePath);
      const releasePath = typeof active.releasePath === "string" ? active.releasePath : "";
      if (!releasePath) {
        notReady("RUNTIME_ACTIVE_NO_RELEASE_PATH", `${activePath} records no releasePath`,
          "Re-run install-runtime.mjs so active.json is written by the installer.");
      } else if (!existsSync(releasePath) || !statSync(releasePath).isDirectory()) {
        notReady("RUNTIME_RELEASE_MISSING", `active release path does not exist: ${releasePath}`,
          "Re-run install-runtime.mjs on this box.");
      } else if (looksLikeSkillTree(releasePath)) {
        notReady("RUNTIME_ROOT_IS_SOURCE_SKILL", `active release path is inside a numbered skill tree: ${releasePath}`,
          "Activate an external release prefix (install-runtime.mjs --prefix) so update-skills.sh cannot rewrite the runtime.");
      } else {
        const closure = inspectRuntimeClosure(releasePath);
        if (closure.problems.length > 0) {
          for (const problem of closure.problems) {
            notReady(problem.code, `${problem.detail} under ${releasePath}`,
              "Re-run install-runtime.mjs; the activated release is not dependency-complete.");
          }
        } else {
          runtimeRoot = releasePath;
          derivation.push({
            field: "runtimeRoot",
            source: `active.json releaseId=${active.releaseId ?? "unknown"}`,
            value: runtimeRoot,
          });
        }
      }
    } catch (error) {
      notReady("RUNTIME_ACTIVE_UNREADABLE", `cannot read ${activePath}: ${String(error.message ?? error)}`,
        "Re-run install-runtime.mjs on this box.");
    }
  }

  // ---- remaining paths ----
  let councilAskPath = null;
  const candidateAsk = join(options.prefix, "bin", "council-ask");
  if (existsSync(candidateAsk)) {
    councilAskPath = candidateAsk;
    derivation.push({ field: "councilAskPath", source: "council-runtime bin", value: councilAskPath });
  } else {
    notReady("COUNCIL_ASK_MISSING", `no council-ask shim at ${candidateAsk}`,
      "Install the front door through the supported skill install, then re-run provision.");
  }

  const stateDir = join(options.openclawRoot, "council-before-dispatch");
  derivation.push({ field: "stateDir", source: "openclaw root", value: stateDir });

  let displayTimezone = options.timezone;
  if (!displayTimezone) {
    try {
      displayTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    } catch {
      displayTimezone = "UTC";
    }
    derivation.push({ field: "displayTimezone", source: "this process's resolved time zone", value: displayTimezone });
  } else {
    derivation.push({ field: "displayTimezone", source: "operator flag", value: displayTimezone });
  }

  const ready = reasons.length === 0
    && Boolean(agentId && accountId && conversationId && agentWorkspace && senderIds.length > 0 && runtimeRoot && councilAskPath);

  const entry = ready
    ? {
        enabled: true,
        config: {
          channel: "telegram",
          accountId,
          conversationId,
          senderIds,
          agentId,
          agentWorkspace,
          councilAskPath,
          stateDir,
          mode: "medium",
          displayTimezone,
          timeoutMs: 300000,
        },
      }
    : null;

  const result = {
    schema: SCHEMA,
    status: ready ? "READY" : "NOT_READY",
    readiness: ready ? "ready" : "not_ready",
    claims: {
      derivedFromBoxConfig: true,
      identityUnambiguous: ready,
      runtimeClosure: "static_metadata_only",
      runtimeResolutionProven: false,
      runtimeRootEmitted: false,
      pluginEnabledByThisTool: false,
      configWritten: false,
      credentialsTouched: false,
      providersChanged: false,
    },
    entry,
    derivation: ready ? derivation : undefined,
    reasons,
  };
  console.log(JSON.stringify(result, null, 2));
  return ready ? 0 : 1;
}

// Same guard as install-runtime.mjs: importing this module (the regression
// tests do) must not run provisioning or exit the process.
const invokedDirectly = (() => {
  const entry = process.argv[1];
  if (!entry) return false;
  const self = fileURLToPath(import.meta.url);
  try {
    return realpathSync(entry) === realpathSync(self);
  } catch {
    return resolve(entry) === resolve(self);
  }
})();

if (invokedDirectly) {
  process.exit(main(process.argv.slice(2)));
}
