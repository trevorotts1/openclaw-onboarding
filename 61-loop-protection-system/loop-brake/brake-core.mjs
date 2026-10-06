// loop-brake core (Skill 61, Fix 9). Pure logic: no SDK import, no model call, no disk write.
//
// before_tool_call [sessions_send]: hash the NORMALIZED message per (source session, target);
//   the THIRD identical hash inside the D7 window is blocked (block only, never an approval gate).
// after_tool_call [all tools]: count failed results that carry an auth-refusal marker per
//   (run, tool) with the D6 two-layer test; report once at warn and once at P1.
//
// Every number and marker is read at runtime from config/thresholds.json and
// config/signatures.json. Nothing is copied here. State lives in memory only, and is only
// hashes and counters: no message body, tool argument or tool result is ever stored or logged.
// Any internal error passes the call through (fail-open): a false block is the risk, not a miss.

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const BLOCK_REASON =
  "Already delivered; do not resend. Use timeoutSeconds: 0 or wait for the late reply.";
export const FAIL_CLOSED_REASON = "Fail-closed dependency: stop and report once (N40)";
export const DEFAULT_CONFIG_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "config");

// Same whitespace set as Python's str.isspace() / re `\s`, so the hash matches
// scripts/loop_common.py cross_run_payload_hash byte for byte (JS `\s` differs at the edges).
const WS = "\\t\\n\\v\\f\\r \\x1c-\\x1f\\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
const PREAMBLE_RE = new RegExp(`^[${WS}]*\\[[^\\]\\n]{0,200}\\][${WS}]*\\n?`);
const WS_RUN_RE = new RegExp(`[${WS}]+`, "g");

export function normalize(text) {
  const s = typeof text === "string" ? text : "";
  return s.replace(PREAMBLE_RE, "").replace(WS_RUN_RE, " ").replace(/^ | $/g, "");
}

export function payloadHash(source, target, text) {
  const body = JSON.stringify({ payload: normalize(text), source: String(source ?? ""), target: String(target ?? "") });
  return createHash("sha256").update(body, "utf8").digest("hex").slice(0, 16);
}

// The existing rollout gate, same precedence as scripts/activate-loop-protection.sh:
// env override (non-empty) > rollout.json fleet_rollout_enabled === true > held.
export function rolloutEnabled(configDir, env = process.env) {
  const e = env.OPENCLAW_LOOP_PROTECTION_ROLLOUT;
  if (e) return ["1", "true", "yes", "on", "enabled"].includes(String(e).toLowerCase());
  try {
    return JSON.parse(readFileSync(join(configDir, "rollout.json"), "utf8")).fleet_rollout_enabled === true;
  } catch {
    return false;
  }
}

function positive(n, what) {
  if (!Number.isFinite(n) || n <= 0) throw new Error(`bad ${what}`);
  return n;
}

export function loadConfig(configDir) {
  const t = JSON.parse(readFileSync(join(configDir, "thresholds.json"), "utf8"));
  const s = JSON.parse(readFileSync(join(configDir, "signatures.json"), "utf8"));
  const d7 = t.d7_cross_run_resend;
  const d6 = t.d6_futile_retry_burst;
  const f = s.fail_closed_markers;
  const shapes = [];
  for (const p of f.error_shape_patterns ?? []) {
    try { shapes.push(new RegExp(p, "im")); } catch { /* a bad pattern is skipped, like the Python side */ }
  }
  return {
    windowMs: positive(d7.window_seconds, "window_seconds") * 1000,
    sendWarnAt: positive(d7.warn_repeat, "warn_repeat"),
    sendBlockAt: positive(d7.p1_repeat, "p1_repeat"),
    maxAttempts: positive(d6.doctrine_max_attempts, "doctrine_max_attempts"),
    fcWarnAt: positive(d6.warn_failclosed_calls, "warn_failclosed_calls"),
    fcP1At: positive(d6.p1_failclosed_calls, "p1_failclosed_calls"),
    markers: (f.markers ?? []).map((m) => String(m).toLowerCase()),
    exempt: new Set((f.result_scan_exempt_tools ?? []).map(String)),
    shapes,
  };
}

const FAILED_STATUS = new Set(["error", "failed", "blocked", "denied"]);
const TEXT_CAP = 65536; // ponytail: scan ceiling per result; raise only if a real refusal ever sits past 64 KiB
const MAX_ENTRIES = 2000; // ponytail: memory ceiling per map (oldest evicted); a longer-lived counter store needs a TTL

function resultText(r) {
  if (r == null) return "";
  if (typeof r === "string") return r.slice(0, TEXT_CAP);
  const parts = [];
  const take = (v) => { if (typeof v === "string") parts.push(v); };
  const c = r.content;
  if (typeof c === "string") take(c);
  else if (Array.isArray(c)) {
    for (const b of c) {
      if (typeof b === "string") take(b);
      else if (b && typeof b === "object") for (const k of ["text", "output", "content"]) take(b[k]);
    }
  } else if (c && typeof c === "object") { take(c.text); take(c.output); }
  if (!parts.length) { try { parts.push(JSON.stringify(r)); } catch { /* unscannable: counts as no marker */ } }
  return parts.join("\n").slice(0, TEXT_CAP);
}

export function createBrake(cfg, { now = Date.now, say = () => {} } = {}) {
  const sends = new Map(); // payload hash -> { ts: number[], logged: boolean }
  const refusals = new Map(); // `${runId}\0${tool}` -> { n, warned, p1 }
  const touch = (map, k, v) => {
    map.delete(k);
    map.set(k, v);
    if (map.size > MAX_ENTRIES) map.delete(map.keys().next().value);
  };

  function beforeSend(event, ctx) {
    try {
      if (event?.toolName !== "sessions_send") return undefined;
      const p = event.params ?? {};
      const source = ctx?.sessionKey ?? ctx?.sessionId;
      const target = p.sessionKey ?? p.label ?? p.agentId;
      if (!source || !target || !normalize(p.message)) return undefined; // pair or body unknown: fail open
      const h = payloadHash(source, target, p.message);
      const t = now();
      const e = sends.get(h) ?? { ts: [], logged: false };
      e.ts = e.ts.filter((x) => t - x <= cfg.windowMs);
      if (!e.ts.length) e.logged = false;
      if (e.ts.length + 1 >= cfg.sendBlockAt) {
        touch(sends, h, e); // a blocked attempt is not recorded, so the window frees on its own
        if (!e.logged) {
          e.logged = true;
          say("warn", `blocked identical sessions_send (hash ${h}); already delivered ${e.ts.length}x in window`);
        }
        return { block: true, blockReason: BLOCK_REASON };
      }
      e.ts.push(t);
      touch(sends, h, e);
      if (e.ts.length >= cfg.sendWarnAt) say("warn", `repeat identical sessions_send ${e.ts.length}x in window (hash ${h})`);
    } catch {
      say("warn", "before_tool_call error; call passed through");
    }
    return undefined;
  }

  // Spec Fix 9 item 2: once a tool has refused doctrine_max_attempts (2) times in a run, the
  // NEXT call to that tool in that run is blocked. Per (run, tool); other tools and runs are untouched.
  // A blocked attempt still counts as an attempt, so the warn/P1 reports can fire while blocked.
  function beforeRefusal(event, ctx) {
    try {
      const tool = event?.toolName;
      const run = event?.runId ?? ctx?.runId;
      if (!tool || !run) return undefined;
      const k = `${run}\u0000${tool}`;
      const e = refusals.get(k);
      if (!e || e.n < cfg.maxAttempts) return undefined;
      noteAttempt(k, e, tool, run);
      return { block: true, blockReason: FAIL_CLOSED_REASON };
    } catch {
      say("warn", "before_tool_call error; call passed through");
      return undefined;
    }
  }

  function noteAttempt(k, e, tool, run) {
    e.n += 1;
    if (e.n >= cfg.fcP1At && !e.p1) {
      e.p1 = e.warned = true;
      say("error", `P1 fail-closed dependency: tool=${tool} run=${run} attempts=${e.n}; stop and report once (N40)`);
    } else if (e.n >= cfg.fcWarnAt && !e.warned) {
      e.warned = true;
      say("warn", `fail-closed dependency: tool=${tool} run=${run} attempts=${e.n}; stop and report once (N40)`);
    }
    touch(refusals, k, e);
  }

  // The existing D6 two-layer test: L1 tool is not result-exempt; L2 a marker is present AND the
  // result failed at the tool layer or is shaped like an error (prose alone never counts).
  function isRefusal(tool, ev) {
    if (cfg.exempt.has(tool)) return false;
    const r = ev.result;
    const failed =
      Boolean(ev.error) ||
      r?.isError === true ||
      FAILED_STATUS.has(String(r?.details?.status ?? "").toLowerCase());
    const text = resultText(r) + (typeof ev.error === "string" ? `\n${ev.error}` : "");
    const low = text.toLowerCase();
    if (!cfg.markers.some((m) => low.includes(m))) return false;
    return failed || cfg.shapes.some((re) => re.test(text));
  }

  function afterToolCall(event, ctx) {
    try {
      const tool = event?.toolName;
      const run = event?.runId ?? ctx?.runId;
      if (!tool || !run || !isRefusal(tool, event)) return;
      const k = `${run}\u0000${tool}`;
      noteAttempt(k, refusals.get(k) ?? { n: 0, warned: false, p1: false }, tool, run);
    } catch {
      say("warn", "after_tool_call error; ignored");
    }
  }

  // Counters and hashes only. Safe to serialize: it holds nothing from any message or result.
  function snapshot() {
    return {
      sends: Object.fromEntries([...sends].map(([h, e]) => [h, e.ts.length])),
      refusals: Object.fromEntries([...refusals].map(([k, e]) => [k.replace("\u0000", "|"), e.n])),
    };
  }

  return { beforeSend, beforeRefusal, afterToolCall, snapshot };
}

export function register(api, deps = {}) {
  const say = (level, msg) => {
    try { api.logger?.[level]?.(`loop-brake: ${msg}`); } catch { /* logging never breaks a call */ }
  };
  const configDir = deps.configDir ?? DEFAULT_CONFIG_DIR;
  if (!rolloutEnabled(configDir, deps.env ?? process.env)) {
    say("info", "held by the Skill 61 rollout gate; no hooks registered");
    return null;
  }
  let cfg;
  try {
    cfg = loadConfig(configDir);
  } catch (e) {
    say("warn", `config unreadable (${e?.code ?? e?.name}); brake inactive, calls pass through`);
    return null;
  }
  const brake = createBrake(cfg, { now: deps.now, say });
  api.on("before_tool_call", brake.beforeSend, { matcher: ["sessions_send"] });
  api.on("before_tool_call", brake.beforeRefusal); // all tools; blocks only after a counted refusal streak
  api.on("after_tool_call", brake.afterToolCall);
  return brake;
}
