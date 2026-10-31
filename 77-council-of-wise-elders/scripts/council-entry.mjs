#!/usr/bin/env node
// Council of Wise Elders: the supported front door (CTR-102).
//
// One documented entry command for every council call, so the agent never
// has to improvise a sequence:
//
//   council-ask ask --brief FILE [--mode light|medium|heavy] [--route R]
//                   [--model M] [--fresh-facts FILE] [--json]
//   council-ask session <session-id> [--json]
//   council-ask sessions [--json]
//   council-ask authority [--json]
//
// Why this exists, as recorded on the operator box (2026-10-28):
//   1. An explicit "ask the council" was answered with a COMPLETED verdict
//      from four days earlier instead of a new sitting. `ask` always opens a
//      new session; a same-question prior sitting is reported as context and
//      never satisfies the ask.
//   2. The service was down (LaunchAgent written, never bootstrapped), so the
//      agent improvised. `ask` proves the service authority first and refuses
//      with COUNCIL_SERVICE_DOWN instead.
//   3. Recovery used `blackceo-council status`, which reads the CLI's LOCAL
//      store and reported COUNCIL_SESSION_NOT_FOUND while the service held the
//      session. `session` and `sessions` read the SERVICE, never that store.
//   4. The chamber link and the desktop pop were a second, optional agent
//      step, so both were skipped. Every `ask` and every `session` read emits
//      the `Chamber link:` line and fires the pop here.
//
// ponytail: convening delegates to `blackceo-council convene --json` (the
// existing service client: route/model negotiation, public-origin probe,
// service.json persistence) and the link/pop delegate to
// scripts/chamber-visual.sh (the existing resolver). Nothing is reimplemented.
// Add a direct POST only if the CLI shim stops shipping.
//
// Usage: node scripts/council-entry.mjs <ask|session|sessions|authority> ...
//        env: WISE_ELDERS_SERVICE_ORIGIN, WISE_ELDERS_SERVICE_JSON,
//             OPENCLAW_ROOT, COUNCIL_CLI, COUNCIL_SERVICE_LABEL,
//             COUNCIL_ENTRY_NO_REPAIR=1 (never bootstrap the service)
// Exit: 0 ok, 2 usage, 3 not-ready (typed refusal, nothing fabricated)

import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, realpathSync } from "node:fs";
import { homedir, userInfo } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_ORIGIN = "http://127.0.0.1:8787";
const DEFAULT_LABEL = "ai.blackceo.council-service";
const PROBE_MS = 2_500;
const REPAIR_WAIT_MS = 20_000;
const SKILL_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
// The file actually executing. In an installed box this is the durable copy
// under $OPENCLAW_ROOT/council-runtime/frontdoor/<release-id>/scripts/, never
// the skill checkout that installed it.
const FRONT_DOOR = fileURLToPath(import.meta.url);

class Refusal extends Error {
  constructor(code, message, action, { exitCode = 3, detail } = {}) {
    super(message);
    this.code = code; this.action = action; this.exitCode = exitCode; this.detail = detail;
  }
}

export function envOrFile(env = process.env) {
  const explicit = env.WISE_ELDERS_SERVICE_JSON;
  if (explicit) return explicit;
  const oc = env.OPENCLAW_ROOT || env.WISE_ELDERS_OPENCLAW_ROOT
    || (existsSync("/data/.openclaw") ? "/data/.openclaw" : null);
  if (oc) return join(oc, "council-runtime", "service.json");
  const home = env.HOME || homedir();
  return join(home, ".openclaw", "council-runtime", "service.json");
}

export function readServiceJson(path) {
  try { return JSON.parse(readFileSync(path, "utf8")); } catch { return null; }
}

export function resolveOrigin({ env = process.env, serviceJson } = {}) {
  const raw = env.WISE_ELDERS_SERVICE_ORIGIN
    || (typeof serviceJson?.origin === "string" ? serviceJson.origin : "")
    || DEFAULT_ORIGIN;
  try { return new URL(raw).origin; } catch { return DEFAULT_ORIGIN; }
}

async function probe(origin, fetchImpl) {
  try {
    const res = await fetchImpl(`${origin}/healthz`, {
      method: "GET", signal: AbortSignal.timeout(PROBE_MS),
    });
    return res.ok;
  } catch { return false; }
}

function launchAgentPlists(home, label) {
  return [
    join(home, "Library", "LaunchAgents", `${label}.plist`),
    join(home, "Library", "LaunchAgents", "ai.blackceo.wise-elders.service.plist"),
  ].filter((p) => existsSync(p));
}

// Bootstrap the LaunchAgent that owns this box's service. Read-only until the
// service is genuinely absent, so a healthy box is never disturbed.
export function repairService({ serviceJson, env = process.env, run = spawnSync } = {}) {
  if (env.COUNCIL_ENTRY_NO_REPAIR === "1") return { repaired: false, why: "repair disabled" };
  if (process.platform !== "darwin") return { repaired: false, why: "not macOS (VPS uses pm2)" };
  const home = env.HOME || homedir();
  const label = env.COUNCIL_SERVICE_LABEL
    || (typeof serviceJson?.name === "string" && serviceJson.name !== "external" ? serviceJson.name : DEFAULT_LABEL);
  const uid = typeof process.getuid === "function" ? process.getuid() : userInfo().uid;
  const domain = `gui/${uid}`;
  const plists = launchAgentPlists(home, label);
  const tried = [];
  for (const plist of plists) {
    const r = run("launchctl", ["bootstrap", domain, plist], { encoding: "utf8", timeout: 20_000 });
    tried.push(`${plist}: ${r.status === 0 ? "bootstrapped" : (r.stderr || `exit ${r.status}`).trim().split("\n")[0]}`);
  }
  return { repaired: plists.length > 0, why: tried.join("; ") || "no LaunchAgent plist found", plists };
}

async function waitHealthy(origin, fetchImpl, ms) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    if (await probe(origin, fetchImpl)) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

// The authority preflight: prove a service answers before anything else runs.
export async function ensureAuthority({
  env = process.env, fetchImpl = fetch, run = spawnSync, serviceJson = readServiceJson(envOrFile(env)),
} = {}) {
  const origin = resolveOrigin({ env, serviceJson });
  if (await probe(origin, fetchImpl)) {
    return { origin, serviceJson, state: "up", repaired: null };
  }
  const repair = repairService({ serviceJson, env, run });
  const back = repair.repaired && await waitHealthy(origin, fetchImpl, REPAIR_WAIT_MS);
  if (!back) {
    throw new Refusal(
      "COUNCIL_SERVICE_DOWN",
      `The council service did not answer at ${origin} and could not be brought back (${repair.why}).`,
      "Run the box's wire.sh, or start the LaunchAgent named in service.json, then retry. Do not convene or read a session until the service answers /healthz.",
      { detail: { origin, repair } },
    );
  }
  return { origin, serviceJson, state: "up", repaired: repair };
}

function resolveCli({ env = process.env, home = env.HOME || homedir() } = {}) {
  const oc = env.OPENCLAW_ROOT || env.WISE_ELDERS_OPENCLAW_ROOT || join(home, ".openclaw");
  const candidates = [
    env.COUNCIL_CLI,
    join(oc, "council-runtime", "bin", "blackceo-council"),
    join(home, ".local", "bin", "blackceo-council"),
    "blackceo-council",
  ].filter(Boolean);
  for (const c of candidates) {
    if (c.includes("/")) { if (existsSync(c)) return c; continue; }
    // Quoted: COUNCIL_CLI is env-provided, so it is passed as a positional
    // argument rather than interpolated into the shell command.
    const which = spawnSync("sh", ["-c", 'command -v "$1"', "sh", c], { encoding: "utf8" });
    if (which.status === 0 && which.stdout.trim()) return which.stdout.trim();
  }
  return null;
}

// --- Caller route propagation (CTR-123) -----------------------------------
//
// The OpenClaw caller's own configured provider/model is metadata that exists
// at this boundary: the agent runs `council-ask` from its own workspace, and
// OpenClaw documents the workspace as the agent's home and default cwd. The
// route id convention is the runtime's own (`<provider>-configured`; see
// runtime/src/cli/route-discovery.ts). Nothing here guesses a harness, a
// provider, or a fallback: an unresolved or ambiguous caller yields null and
// the service's typed refusal stands. The global main/default model is never
// substituted for the calling agent's own configured model.

const PROVIDER_ID = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

function expandHome(value, home) {
  if (typeof value !== "string" || value.length === 0) return null;
  if (value === "~") return home;
  return value.startsWith("~/") ? join(home, value.slice(2)) : value;
}

function realOrResolve(path) {
  try { return realpathSync(path); } catch { return resolve(path); }
}

function insideDir(parent, child) {
  const base = parent.endsWith("/") ? parent : `${parent}/`;
  return child === parent || child.startsWith(base);
}

function openclawStateDir(env) {
  const home = env.HOME || homedir();
  const raw = env.OPENCLAW_STATE_DIR || env.OPENCLAW_ROOT || env.WISE_ELDERS_OPENCLAW_ROOT || null;
  return expandHome(raw, home) || join(home, ".openclaw");
}

/**
 * Resolve the calling OpenClaw agent's configured provider/model from its
 * own configuration and workspace. Returns
 * { agent_id, provider, model, route_id } or null.
 *
 * Null is the whole answer whenever the caller is not unambiguous: no
 * matching workspace, a shared workspace, several entries at the same
 * depth, or an entry with no model of its own. It never falls back to
 * agents.defaults.model, so an inherited global default is not mistaken for
 * the calling agent's choice.
 */
export function resolveOpenClawCaller({ env = process.env, cwd = process.cwd() } = {}) {
  const home = env.HOME || homedir();
  // A workspace override names no single agent.
  if (typeof env.OPENCLAW_WORKSPACE_DIR === "string" && env.OPENCLAW_WORKSPACE_DIR.trim().length > 0) return null;
  const stateDir = realOrResolve(openclawStateDir(env));
  let config;
  try { config = JSON.parse(readFileSync(join(stateDir, "openclaw.json"), "utf8")); } catch { return null; }
  const entries = config?.agents?.entries;
  if (!entries || typeof entries !== "object") return null;
  const sharedRoot = expandHome(config?.agents?.defaults?.workspace, home);
  const cwdReal = realOrResolve(cwd);
  const matches = [];
  for (const [agentId, entry] of Object.entries(entries)) {
    if (!entry || typeof entry !== "object") continue;
    const declared = entry.workspace;
    // A declared workspace must be absolute (or ~-rooted) to be verifiable.
    if (typeof declared === "string" && declared.length > 0 && !declared.startsWith("/") && !declared.startsWith("~")) continue;
    const workspace = expandHome(declared, home) || (sharedRoot ? join(sharedRoot, agentId) : join(stateDir, `workspace-${agentId}`));
    const ws = realOrResolve(workspace);
    if (insideDir(ws, cwdReal)) matches.push({ agentId, entry, ws });
  }
  if (matches.length === 0) return null;
  matches.sort((a, b) => b.ws.length - a.ws.length);
  const best = matches[0];
  if (matches[1] && matches[1].ws.length === best.ws.length) return null;
  const primary = typeof best.entry.model === "string"
    ? best.entry.model
    : (typeof best.entry.model?.primary === "string" ? best.entry.model.primary : null);
  if (!primary) return null;
  const slash = primary.indexOf("/");
  if (slash <= 0 || slash === primary.length - 1) return null;
  const provider = primary.slice(0, slash);
  const model = primary.slice(slash + 1);
  if (!PROVIDER_ID.test(provider)) return null;
  if (model.startsWith("--") || /[\r\n]/.test(model)) return null;
  return { agent_id: best.agentId, provider, model, route_id: `${provider}-configured` };
}

// The canonical chamber line + desktop pop, from the existing resolver.
export function chamberVisual({ sessionId, env = process.env, skillRoot = SKILL_ROOT, run = spawnSync } = {}) {
  const helper = join(skillRoot, "scripts", "chamber-visual.sh");
  if (!existsSync(helper)) return { line: null, local: false, why: "chamber-visual.sh missing" };
  const args = ["bash", helper];
  if (sessionId) args.push("--session", sessionId);
  const r = run(args[0], args.slice(1), { encoding: "utf8", timeout: 30_000, env });
  const stderrLines = String(r.stderr || "").split("\n").map((l) => l.trim());
  const popLine = stderrLines.find((l) => l.startsWith("pop: ")) ?? null;
  const pop = popLine ? popLine.slice(5).trim() : null;
  const line = String(r.stdout || "").split("\n").find((l) => l.startsWith("Chamber link:")) ?? null;
  if (line === null) return { line: null, local: false, clientSafe: false, pop, why: (r.stderr || "no Chamber link line").trim().split("\n")[0] };
  return { line, ...clientReach(line), pop };
}

// A link a client can actually open. Loopback works only on the box's own
// screen, and the reserved documentation TLDs (example.com, .example, .test,
// .invalid) are fixtures: sending either to a client is a dead link, which is
// exactly the kind of invented-looking address the skill forbids.
export function clientReach(line) {
  const raw = String(line ?? "").replace(/^Chamber link:\s*/, "").trim();
  let host = "";
  try { host = new URL(raw).hostname.toLowerCase(); } catch { return { local: false, clientSafe: false }; }
  const local = host === "127.0.0.1" || host === "::1" || host === "localhost" || host.endsWith(".localhost");
  const fixture = /\.(example\.(com|net|org)|example|test|invalid)$/.test(host)
    || host === "example.com" || host === "example.net" || host === "example.org";
  return { local, clientSafe: !local && !fixture };
}

async function listSessions(origin, fetchImpl) {
  let res;
  try {
    res = await fetchImpl(`${origin}/api/council/sessions`, { headers: { accept: "application/json" } });
  } catch (e) {
    throw new Refusal("SERVICE_UNREACHABLE", `The council service did not answer at ${origin}.`, "Start the council service, then retry.");
  }
  const body = await res.json().catch(() => null);
  if (res.status === 501) {
    throw new Refusal("SESSION_LIST_NOT_BOUND", "The service has no session reader that can list.", "Read the session by id instead: council-ask session <id>.");
  }
  if (!res.ok || !body) {
    throw new Refusal("SERVICE_BAD_RESPONSE", `The council service answered HTTP ${res.status} without a session list.`, "Check that the origin is the council service.");
  }
  return Array.isArray(body.sessions) ? body.sessions : [];
}

async function readSession(origin, sessionId, fetchImpl) {
  let res;
  try {
    res = await fetchImpl(`${origin}/council/${encodeURIComponent(sessionId)}`, { headers: { accept: "application/json" } });
  } catch {
    throw new Refusal("SERVICE_UNREACHABLE", `The council service did not answer at ${origin}.`, "Start the council service, then retry.");
  }
  const body = await res.json().catch(() => null);
  if (res.status === 404 || body?.code === "SERVICE_SESSION_NOT_FOUND") {
    throw new Refusal(
      "COUNCIL_SESSION_NOT_FOUND",
      `store=service: the council service at ${origin} has no session ${sessionId}.`,
      "List the sessions the service holds with `council-ask sessions`; the local `blackceo-council status` reads a different store and is not authority here.",
      { detail: { origin, store: "service", session_id: sessionId } },
    );
  }
  if (!res.ok || !body) {
    throw new Refusal("SERVICE_BAD_RESPONSE", `The council service answered HTTP ${res.status} for ${sessionId}.`, "Check that the origin is the council service.");
  }
  return body;
}

const norm = (s) => String(s ?? "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

// A completed sitting on the same question is CONTEXT, never the answer.
export function priorSittings(sessions, question) {
  const q = norm(question);
  if (!q) return [];
  return (sessions || []).filter((s) => s && typeof s === "object"
    && norm(s.question) === q && String(s.state || "").toUpperCase() === "COMPLETED");
}

export async function runAsk(opts) {
  const { flags, env, fetchImpl = fetch, run = spawnSync, skillRoot = SKILL_ROOT, io } = opts;
  const wantJson = flags.get("json") === true;
  const briefPath = flags.get("brief");
  if (!briefPath) throw new Refusal("USAGE", "ask needs --brief FILE.", "Pass the prepared brief: council-ask ask --brief FILE [--mode light|medium|heavy].", { exitCode: 2 });
  let brief;
  try { brief = JSON.parse(readFileSync(briefPath, "utf8")); } catch (e) {
    throw new Refusal("BRIEF_UNREADABLE", `Could not read --brief ${briefPath}: ${e.message}`, "Fix the brief file and retry.", { exitCode: 2 });
  }
  const authority = await ensureAuthority({ env, fetchImpl, run });

  const prior = priorSittings(await listSessions(authority.origin, fetchImpl).catch(() => []), brief?.question);

  const cli = resolveCli({ env });
  if (!cli) {
    throw new Refusal(
      "COUNCIL_CLI_MISSING",
      "The council CLI shim is not installed on this box.",
      "Run the box's wire.sh (it installs $OPENCLAW_ROOT/council-runtime/bin/blackceo-council), then retry.",
    );
  }
  // An explicit choice from the caller always wins; only an otherwise
  // unknown harness reaches the caller-metadata resolution below.
  const explicitChoice = flags.has("route") || flags.has("model") || flags.has("harness");
  const caller = explicitChoice ? null : resolveOpenClawCaller({ env });
  // The shim is an executable node script; run it directly, not through node.
  const cliArgs = ["convene", "--brief", briefPath, "--json"];
  for (const k of ["mode", "route", "model", "fresh-facts", "ollama-plan", "fallback-model", "harness", "seat-ids"]) {
    if (flags.has(k)) cliArgs.push(`--${k}`, String(flags.get(k)));
  }
  // Propagate the calling agent's own route+model as the runtime's explicit
  // selection. This is what stops ROUTE_CHOICE_REQUIRED for an OpenClaw
  // caller without guessing a Claude harness. No provider is invented: an
  // unresolved caller leaves the service's typed refusal exactly as it was.
  if (caller) cliArgs.push("--route", caller.route_id, "--model", caller.model);
  cliArgs.push("--origin", authority.origin);
  // Exactly ONE opener (CTR-103 + CTR-101 integrated flow). The runtime
  // `convene` opens the chamber itself on a desktop box (--no-open /
  // COUNCIL_CHAMBER_OPEN). Suppress that on the convene child only, and let
  // chamber-visual.sh below own the single pop. A legacy runtime ignores the
  // variable and never opens, so the total is one in both generations.
  const conveneEnv = { ...env, COUNCIL_CHAMBER_OPEN: "0" };
  const out = run(cli, cliArgs, { encoding: "utf8", timeout: 180_000, env: conveneEnv });
  const raw = (out.stdout || "").trim();
  if (out.status !== 0 || !raw) {
    let parsed = null;
    try { parsed = JSON.parse(raw.slice(raw.indexOf("{"), raw.lastIndexOf("}") + 1)); } catch { /* text refusal */ }
    const code = parsed?.error?.code || parsed?.code || "CONVENE_REFUSED";
    const msg = parsed?.error?.message || parsed?.detail?.summary || raw.split("\n")[0] || "convene refused";
    throw new Refusal(code, String(msg), parsed?.error?.action || "Read the refusal and retry once resolved.");
  }
  let res;
  try { res = JSON.parse(raw.slice(raw.indexOf("{"), raw.lastIndexOf("}") + 1)); } catch {
    throw new Refusal("SERVICE_BAD_RESPONSE", "The convene command did not return JSON.", "Re-run with --json and report the raw output.");
  }
  const sessionId = String(res.session_id ?? "");
  if (!sessionId) throw new Refusal("SERVICE_BAD_RESPONSE", "The convene answer carried no session id.", "Report the raw output; never invent a session id.");

  const chamber = chamberVisual({ sessionId, env, skillRoot, run });
  const payload = {
    ok: true, action: "ask", session_id: sessionId,
    route_id: res.route_id ?? null, model_label: res.model_label ?? null,
    selection_source: res.selection_source ?? null, mode: res.mode ?? flags.get("mode") ?? null,
    caller_agent: caller?.agent_id ?? null,
    caller_route_injected: caller ? { route_id: caller.route_id, model: caller.model } : null,
    service_origin: authority.origin,
    service_state: authority.state,
    service_repaired: authority.repaired?.repaired ?? false,
    chamber_link: chamber.line ? chamber.line.replace(/^Chamber link:\s*/, "") : null,
    chamber_link_local: chamber.local,
    chamber_link_client_safe: chamber.clientSafe,
    desktop_pop: chamber.pop ?? null,
    prior_completed_same_question: prior.map((s) => ({ session_id: s.session_id, created_at: s.created_at })),
    session_url: res.session_url ?? null, events_url: res.events_url ?? null,
    // CTR-134: present only when the service prepared the alternatives with
    // ONE request on the caller's own route before the sitting.
    preparation: res.preparation ?? null,
  };
  io.out(wantJson ? `${JSON.stringify(payload)}\n` : renderAsk(payload, chamber));
  return 0;
}

export function renderAsk(payload, chamber) {
  const lines = [
    `Council convened: ${payload.session_id}`,
    `  mode: ${payload.mode ?? "medium"}   route: ${payload.route_id ?? "?"}   model: ${payload.model_label ?? "?"} (${payload.selection_source ?? "?"})`,
    `  service: ${payload.service_origin} (${payload.service_state}${payload.service_repaired ? ", repaired now" : ""})`,
  ];
  if (payload.prior_completed_same_question.length > 0) {
    const ids = payload.prior_completed_same_question.map((s) => s.session_id).join(", ");
    lines.push(`  note: a COMPLETED sitting on this exact question already exists (${ids}); this ask still opened the NEW session ${payload.session_id}. Prior verdicts are context, never the answer.`);
  }
  if (chamber.line) lines.push(`  ${chamber.line}`);
  if (chamber.line && chamber.local) {
    lines.push("  this link is loopback: never send it to a client; say the Council is running and the private link follows with a later council.");
  }
  if (chamber.line && !chamber.local && chamber.clientSafe === false) {
    lines.push("  this link points at a documentation/fixture host (example.com, .test, .invalid): it is a dead link for a client. Report the Council as running and say the private link follows; fix public_origin before sending anything.");
  }
  if (!chamber.line) lines.push(`  Chamber link unavailable (${chamber.why}); do not invent one.`);
  if (chamber.line && chamber.pop && !/^opened/.test(chamber.pop)) {
    lines.push(`  desktop pop: ${chamber.pop} (the link above is still the answer; paste it into the reply).`);
  }
  if (chamber.line) {
    // A report link exists only after the sitting completes; the service
    // provides it on the session read, so nothing is guessed at convene time.
    lines.push(`  Report (PDF): the download link comes with the completed-session read (council-ask session ${payload.session_id}); nothing is available until the sitting completes.`);
  }
  return `${lines.join("\n")}\n`;
}

export async function runSession(opts) {
  const { flags, id, env, fetchImpl = fetch, run = spawnSync, skillRoot = SKILL_ROOT, io } = opts;
  const wantJson = flags.get("json") === true;
  if (!id) throw new Refusal("USAGE", "session needs a session id.", "council-ask session <session-id>.", { exitCode: 2 });
  const authority = await ensureAuthority({ env, fetchImpl, run });
  const body = await readSession(authority.origin, id, fetchImpl);
  const record = body.session ?? {};
  const verdict = record.verdict ?? record.verdict_json ?? null;
  const label = verdict?.label ?? verdict?.verdict?.label ?? null;
  const chamber = chamberVisual({ sessionId: id, env, skillRoot, run });
  const stateValue = record.state?.state ?? record.state ?? body.state ?? null;
  // The service names its own report address, and only for a completed
  // sitting with a verdict. Never built here, never invented.
  const reportRaw = typeof body.report_url === "string" ? body.report_url : null;
  const report = reportRaw
    ? { url: reportRaw, ...clientReach(reportRaw) }
    : { url: null, local: false, clientSafe: false };
  const lines = [
    `Session ${id} (store=service)`,
    `  state: ${stateValue ?? "?"}`,
    `  mode: ${record.spec?.mode ?? record.mode ?? "?"}`,
    `  question: ${record.spec?.question ?? record.question ?? "?"}`,
    `  verdict: ${label ?? "none yet"}`,
  ];
  if (chamber.line) lines.push(`  ${chamber.line}`);
  if (chamber.line && chamber.local) lines.push("  this link is loopback: never send it to a client.");
  if (chamber.line && !chamber.local && chamber.clientSafe === false) {
    lines.push("  this link points at a documentation/fixture host: dead for a client, do not send it.");
  }
  if (report.url) {
    lines.push(`  Report (PDF): ${report.url}`);
    if (report.local) lines.push("  this report link is loopback: never send it to a client.");
    if (!report.local && report.clientSafe === false) {
      lines.push("  this report link points at a documentation/fixture host: dead for a client, do not send it.");
    }
  } else if (stateValue === "COMPLETED") {
    lines.push("  Report (PDF): unavailable from the service (no report_url); do not invent one.");
  }
  if (wantJson) {
    io.out(`${JSON.stringify({
      ok: true, action: "session", store: "service", service_origin: authority.origin,
      session_id: id,
      state: record.state?.state ?? record.state ?? body.state ?? null,
      mode: record.spec?.mode ?? record.mode ?? null,
      question: record.spec?.question ?? record.question ?? null,
      verdict_label: label,
      chamber_link: chamber.line ? chamber.line.replace(/^Chamber link:\s*/, "") : null,
      chamber_link_local: chamber.local,
      chamber_link_client_safe: chamber.clientSafe,
      desktop_pop: chamber.pop ?? null,
      // Saved-session PDF report: the exact service-provided address, only
      // for a completed sitting with a verdict; null otherwise.
      report_url: report.url,
      report_url_local: report.local,
      report_url_client_safe: report.clientSafe,
    })}\n`);
    return 0;
  }
  io.out(`${lines.join("\n")}\n`);
  return 0;
}

export async function runSessions(opts) {
  const { flags = new Map(), env, fetchImpl = fetch, run = spawnSync, io } = opts;
  const wantJson = flags.get("json") === true;
  const authority = await ensureAuthority({ env, fetchImpl, run });
  const sessions = await listSessions(authority.origin, fetchImpl);
  if (wantJson) {
    io.out(`${JSON.stringify({ ok: true, action: "sessions", store: "service", service_origin: authority.origin, sessions })}\n`);
    return 0;
  }
  if (sessions.length === 0) { io.out(`No council sessions in the service store at ${authority.origin}.\n`); return 0; }
  const lines = sessions.map((s) => `  ${s.session_id}  ${String(s.state ?? "?").padEnd(10)} ${s.created_at ?? ""}  ${s.question ?? ""}`);
  io.out(`Sessions in the service store at ${authority.origin}:\n${lines.join("\n")}\n`);
  return 0;
}

export async function runAuthority(opts) {
  const { flags = new Map(), env = process.env, fetchImpl = fetch, run = spawnSync, io } = opts;
  const wantJson = flags.get("json") === true;
  const sjPath = envOrFile(env);
  const serviceJson = readServiceJson(sjPath);
  const origin = resolveOrigin({ env, serviceJson });
  const up = await probe(origin, fetchImpl);
  const cli = resolveCli({ env });
  const lines = [
    `service origin: ${origin}`,
    `service health: ${up ? "up" : "DOWN (COUNCIL_SERVICE_DOWN)"}`,
    `service json: ${existsSync(sjPath) ? sjPath : "(absent)"}`,
    `manager: ${serviceJson?.manager ?? "?"}  name: ${serviceJson?.name ?? "?"}  release: ${serviceJson?.release_id ?? "?"}`,
    `public_origin: ${serviceJson?.public_origin ?? "(unset)"}`,
    `cli: ${cli ?? "(not installed)"} (convene/routes only; status/verdict read its local store)`,
    `front door: ${FRONT_DOOR}`,
    `skill root: ${SKILL_ROOT}`,
  ];
  if (wantJson) {
    io.out(`${JSON.stringify({
      ok: up, action: "authority",
      service_origin: origin,
      service_up: up,
      service_json: existsSync(sjPath) ? sjPath : null,
      manager: serviceJson?.manager ?? null,
      name: serviceJson?.name ?? null,
      release_id: serviceJson?.release_id ?? null,
      public_origin: serviceJson?.public_origin ?? null,
      cli,
      front_door: FRONT_DOOR,
      skill_root: SKILL_ROOT,
    })}\n`);
    return up ? 0 : 3;
  }
  io.out(`${lines.join("\n")}\n`);
  return up ? 0 : 3;
}

const COMMANDS = new Set(["ask", "session", "sessions", "authority"]);

export function parseArgs(argv) {
  const [command, ...rest] = argv;
  const flags = new Map();
  const positional = [];
  for (let i = 0; i < rest.length; i += 1) {
    const a = rest[i];
    if (!a.startsWith("--")) { positional.push(a); continue; }
    const name = a.slice(2);
    if (name === "json") { flags.set("json", true); continue; }
    const v = rest[i + 1];
    if (v === undefined || v.startsWith("--")) throw new Refusal("USAGE", `--${name} needs a value.`, "Pass a value after the flag.", { exitCode: 2 });
    flags.set(name, v); i += 1;
  }
  return { command, flags, positional };
}

export async function main(
  argv = process.argv.slice(2),
  io = { out: (s) => process.stdout.write(s), err: (s) => process.stderr.write(s) },
  deps = {},
) {
  const env = deps.env ?? process.env;
  const fetchImpl = deps.fetchImpl ?? fetch;
  const run = deps.run ?? spawnSync;
  const skillRoot = deps.skillRoot ?? SKILL_ROOT;
  try {
    const { command, flags, positional } = parseArgs(argv);
    if (!COMMANDS.has(command)) {
      throw new Refusal("USAGE", `Unknown command: ${command ?? "(none)"}`, "council-ask ask|session|sessions|authority", { exitCode: 2 });
    }
    if (command === "ask") return await runAsk({ flags, env, fetchImpl, run, skillRoot, io });
    if (command === "session") return await runSession({ flags, id: positional[0], env, fetchImpl, run, skillRoot, io });
    if (command === "sessions") return await runSessions({ flags, env, fetchImpl, run, io });
    return await runAuthority({ flags, env, fetchImpl, run, io });
  } catch (e) {
    if (e instanceof Refusal) {
      io.err(`${JSON.stringify({ ok: false, error: { code: e.code, message: e.message, action: e.action, ...(e.detail ? { detail: e.detail } : {}) } })}\n`);
      return e.exitCode;
    }
    io.err(`${JSON.stringify({ ok: false, error: { code: "ENTRY_FAILED", message: String(e?.message ?? e) } })}\n`);
    return 3;
  }
}

if (process.argv[1] && realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url))) {
  main().then((code) => process.exit(code));
}
