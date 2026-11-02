// CTR-194: validate an EXISTING plugins.entries["council-before-dispatch"]
// against this box's own config. The installer must not disable a binding that
// already works merely because re-derivation is ambiguous on a box with several
// Telegram accounts or DMs (the operator box has four accounts and three
// authorized DMs). A valid existing entry is preserved; this module only reads.
//
// It never widens authorization: senderIds must be a non-empty subset of the
// account's own allowFrom, with no wildcard.

import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { isAbsolute, join, resolve } from "node:path";

export const PLUGIN_ID = "council-before-dispatch";
export const REQUIRED_FIELDS = [
  "channel", "accountId", "conversationId", "senderIds", "agentId",
  "agentWorkspace", "councilAskPath", "stateDir",
];
const RUNTIME_FILES = [
  "dist/brief/permitted-brief.js",
  "dist/contracts/index.js",
  "dist/index.js",
  "dist/contracts/schemas.js",
  "node_modules/zod/package.json",
];

export function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function isWildcard(value) {
  const s = String(value).trim().toLowerCase();
  return s === "*" || s === "all" || s === "any" || s.includes("*");
}

export function normalizePath(value) {
  if (typeof value !== "string" || !value) return value;
  if (value === "~") return homedir();
  if (value.startsWith("~/")) return join(homedir(), value.slice(2));
  return isAbsolute(value) ? value : resolve(value);
}

export function peerId(match) {
  const peer = match?.peer;
  if (typeof peer === "string" || typeof peer === "number") {
    const value = String(peer).trim();
    return value || null;
  }
  if (isPlainObject(peer) && (typeof peer.id === "string" || typeof peer.id === "number")) {
    const value = String(peer.id).trim();
    return value || null;
  }
  return null;
}

export function isDirectPeer(match) {
  const peer = match?.peer;
  if (!isPlainObject(peer)) return true; // legacy scalar peer
  const kind = typeof peer.kind === "string" ? peer.kind.trim().toLowerCase() : "";
  return kind === "direct" || kind === "dm" || kind === "private";
}

function activeRuntime(config, prefix) {
  const ask = normalizePath(config.councilAskPath || "");
  const root = prefix || (ask ? resolve(join(ask, "..", "..")) : "");
  const activePath = join(root, "active.json");
  if (!existsSync(activePath)) return { ok: false, detail: `no active release receipt at ${activePath}` };
  let active;
  try { active = JSON.parse(readFileSync(activePath, "utf8")); }
  catch (error) { return { ok: false, detail: `active.json unreadable: ${String(error?.message ?? error)}` }; }
  const releasePath = typeof active.releasePath === "string" ? active.releasePath : "";
  if (!releasePath || !existsSync(releasePath)) return { ok: false, detail: `active release path is missing: ${releasePath || "(none)"}` };
  const missing = RUNTIME_FILES.filter((rel) => !existsSync(join(releasePath, rel)));
  if (missing.length > 0) return { ok: false, detail: `activated release is incomplete: ${missing.join(", ")}` };
  return { ok: true, releasePath };
}

export function validateExistingEntry({ cfg, entry, openclawRoot, prefix }) {
  const problems = [];
  if (!isPlainObject(entry) || entry.enabled !== true) return { ok: false, problems: ["entry is missing or not enabled"] };
  const config = isPlainObject(entry.config) ? entry.config : {};
  for (const field of REQUIRED_FIELDS) {
    if (config[field] === undefined || config[field] === null || config[field] === "") problems.push(`config.${field} is missing`);
  }
  if (problems.length > 0) return { ok: false, problems };
  if (config.channel !== "telegram") problems.push("config.channel is not telegram");
  if (typeof config.runtimeRoot === "string" && config.runtimeRoot.length > 0) problems.push("config.runtimeRoot overrides the activated release");
  if (!Array.isArray(config.senderIds) || config.senderIds.length === 0) problems.push("config.senderIds is empty");
  if (Array.isArray(config.senderIds) && config.senderIds.some(isWildcard)) problems.push("config.senderIds contains a wildcard");
  if (!isAbsolute(config.agentWorkspace)) problems.push("config.agentWorkspace is not absolute");

  const accounts = isPlainObject(cfg?.channels?.telegram?.accounts) ? cfg.channels.telegram.accounts : {};
  const account = accounts[config.accountId];
  if (!isPlainObject(account)) problems.push(`account ${config.accountId} does not exist`);
  else {
    if (account.enabled === false) problems.push(`account ${config.accountId} is disabled`);
    const allow = Array.isArray(account.allowFrom) ? account.allowFrom.map(String) : [];
    if (allow.length === 0) problems.push(`account ${config.accountId} has no allowFrom`);
    if (allow.some(isWildcard)) problems.push(`account ${config.accountId} allowFrom contains a wildcard`);
    if (Array.isArray(config.senderIds) && config.senderIds.some((id) => !allow.includes(String(id)))) {
      problems.push("config.senderIds is not a subset of the account allowFrom");
    }
  }

  const agents = isPlainObject(cfg?.agents?.entries) ? cfg.agents.entries : {};
  const agent = agents[config.agentId];
  if (!isPlainObject(agent)) problems.push(`agent ${config.agentId} does not exist`);
  else if (normalizePath(agent.workspace) !== normalizePath(config.agentWorkspace)) {
    problems.push(`agent ${config.agentId} workspace disagrees with config.agentWorkspace`);
  }

  const bindings = Array.isArray(cfg?.bindings) ? cfg.bindings : [];
  const direct = bindings.filter((one) => isPlainObject(one) && one.agentId === config.agentId
    && isPlainObject(one.match) && one.match.channel === "telegram" && isDirectPeer(one.match));
  if (!direct.some((one) => peerId(one.match) === String(config.conversationId))) {
    problems.push(`config.conversationId is not a direct telegram binding for ${config.agentId}`);
  }

  if (!existsSync(normalizePath(config.councilAskPath))) problems.push("config.councilAskPath does not exist");
  const runtime = activeRuntime(config, prefix);
  if (!runtime.ok) problems.push(runtime.detail);

  return { ok: problems.length === 0, problems, releasePath: runtime.releasePath };
}
