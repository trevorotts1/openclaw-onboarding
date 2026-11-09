#!/usr/bin/env node
// Council of Wise Elders: agent-resolver evidence for the selected-tree gate.
//
// scripts/selected-tree-gate.mjs refuses a box with more than one Council copy
// (~/.agents, ~/.claude, ~/.codex, ~/.openclaw ...) until it is told which copy
// the intended OpenClaw agent actually reads (--agent-selected). A roll has no
// operator to export COUNCIL_AGENT_SKILL_DIR, so wire.sh asks the real
// resolver instead: `openclaw skills info council-of-wise-elders --agent <id>
// --json` answers with the folder (baseDir) that agent serves.
//
// This is evidence, not a verdict. The gate still verifies the named copy and
// still rejects evidence that contradicts the live install-record or names a
// tree outside every known agent root. No answer (no CLI, no agent id on a
// multi-agent box, an error, another skill, a relative path) means exit 1 with
// nothing on stdout, so the gate stays "unproven" and refuses, as before.
//
// Agent id order mirrors scripts/onboarding-state.sh obs_default_agent():
// OPENCLAW_AGENT_ID, agents.defaults.systemAgent.agentId, an agents.entries
// item flagged default, agents.list id "main", the first entry. None found:
// no --agent is passed (single-agent boxes need none).
//
// Usage: node scripts/agent-resolver-evidence.mjs [--cli PATH] [--config FILE]
//        env: COUNCIL_OPENCLAW (CLI path), OPENCLAW_AGENT_ID, OPENCLAW_ROOT
//        stdout: the resolved skill folder; exit 0 evidence, 1 none, 2 usage

import { spawnSync } from "node:child_process";
import { accessSync, constants, existsSync, readFileSync, realpathSync } from "node:fs";
import { homedir } from "node:os";
import { delimiter, dirname, isAbsolute, join } from "node:path";
import { pathToFileURL } from "node:url";

export const SKILL_NAME = "council-of-wise-elders";

export function defaultAgentId(config, env = process.env) {
  if (env.OPENCLAW_AGENT_ID) return env.OPENCLAW_AGENT_ID;
  const agents = config?.agents ?? {};
  const system = agents.defaults?.systemAgent?.agentId;
  if (system) return system;
  const entries = agents.entries && typeof agents.entries === "object" ? agents.entries : {};
  for (const [id, v] of Object.entries(entries)) if (v && typeof v === "object" && v.default) return id;
  const list = Array.isArray(agents.list) ? agents.list : [];
  if (list.some((a) => a && a.id === "main")) return "main";
  const ids = Object.keys(entries).sort();
  if (ids.length) return ids[0];
  return list.find((a) => a && a.id)?.id ?? "";
}

function findCli({ cli, env, home }) {
  const candidates = [
    cli,
    env.COUNCIL_OPENCLAW,
    ...(env.PATH ?? "").split(delimiter).filter(Boolean).map((d) => join(d, "openclaw")),
    join(home, ".local", "bin", "openclaw"),
    join(home, ".npm-global", "bin", "openclaw"),
    "/usr/local/bin/openclaw",
    "/opt/homebrew/bin/openclaw",
  ];
  for (const c of candidates) {
    if (!c) continue;
    try {
      accessSync(c, constants.X_OK);
      return c;
    } catch { /* next */ }
  }
  return null;
}

/**
 * The folder the OpenClaw skill resolver serves for this skill, or
 * {dir: null, reason}. `run` is injectable for tests.
 */
export function resolveAgentSkillDir({
  cli, config, env = process.env, home = homedir(),
  run = (file, args, opts) => spawnSync(file, args, opts),
} = {}) {
  const exe = findCli({ cli, env, home });
  if (!exe) return { dir: null, reason: "no openclaw CLI found (COUNCIL_OPENCLAW, PATH, known install locations)" };
  const agent = defaultAgentId(config, env);
  const args = ["skills", "info", SKILL_NAME, ...(agent ? ["--agent", agent] : []), "--json"];
  // The CLI is a node script: keep the node running this helper first on PATH.
  const childEnv = { ...env, PATH: [dirname(process.execPath), env.PATH ?? ""].filter(Boolean).join(delimiter) };
  const r = run(exe, args, { encoding: "utf8", timeout: 90_000, maxBuffer: 8 * 1024 * 1024, env: childEnv });
  if (r.error || r.status !== 0) {
    return { dir: null, reason: `openclaw ${args.join(" ")} did not answer (${r.error?.message ?? `exit ${r.status}`})` };
  }
  let info;
  try {
    const out = String(r.stdout);
    info = JSON.parse(out.slice(out.indexOf("{"), out.lastIndexOf("}") + 1));
  } catch {
    return { dir: null, reason: "the resolver answer is not JSON" };
  }
  if (info?.ok === false) return { dir: null, reason: `resolver error: ${info.error?.message ?? "unknown"}` };
  if (info?.name !== SKILL_NAME) return { dir: null, reason: `resolver answered for ${info?.name ?? "no skill"}, not ${SKILL_NAME}` };
  if (typeof info.baseDir !== "string" || !isAbsolute(info.baseDir)) {
    return { dir: null, reason: "the resolver names no absolute baseDir" };
  }
  return { dir: info.baseDir, agent, reason: null };
}

if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) {
  const argv = process.argv.slice(2);
  const opt = (name) => { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : undefined; };
  if (argv.some((a) => a.startsWith("--") && !["--cli", "--config"].includes(a))) {
    console.error("usage: node scripts/agent-resolver-evidence.mjs [--cli PATH] [--config FILE]");
    process.exit(2);
  }
  const root = process.env.OPENCLAW_ROOT || join(homedir(), ".openclaw");
  const file = opt("--config") ?? join(root, "openclaw.json");
  let config = null;
  try {
    if (existsSync(file)) config = JSON.parse(readFileSync(file, "utf8"));
  } catch { /* an unreadable config just means no agent id */ }
  const res = resolveAgentSkillDir({ cli: opt("--cli"), config });
  if (!res.dir) {
    console.error(`agent-resolver-evidence: none (${res.reason})`);
    process.exit(1);
  }
  console.log(res.dir);
}
