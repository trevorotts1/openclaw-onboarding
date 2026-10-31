// Council before_dispatch claim core (CTR-127).
//
// This module is the testable half of the plugin. The OpenClaw wiring lives in
// ../index.ts. Nothing here imports the OpenClaw SDK, so the regression case
// can run with plain Node without loading the Gateway.
//
// Contract, in order:
//   1. Trust: Telegram account + chat/channel + sender + target agent/session
//      must match operator config exactly. Anything absent or different is
//      UNHANDLED, so the normal model path (and its sender authorization)
//      stays in charge.
//   2. Message shape: only the explicit Council phrases in the installed
//      SKILL.md are recognised, anchored at the start of the message and
//      tolerant of repeated whitespace ("ASK THE  COUNCIL"). A recognised ask
//      that cannot be used is answered with a typed refusal, never dropped to
//      the model turn. The original remainder is DATA (never a shell string,
//      never a route).
//   3. Durable claim: one message id gets one sitting. The claim is written
//      before any brief or front-door work; the result is written atomically.
//   4. Brief: the installed permitted-context builder collects authorised
//      context. The DecisionBrief carries the ORIGINAL question, explicit
//      unknowns, and evidence-bound facts. No model inference, no invented
//      options, no invented catalog, no invented weights.
//   5. Front door: spawn the supported `council-ask` shim with argv (never a
//      shell) from the calling agent's workspace, so the accepted CTR-123
//      caller-route patch resolves that agent's own configured route. The
//      hook returns the front door's actual text or a typed failure. It never
//      emits approval/GO text.
//
//   6. Runtime closure: the brief builder is the Council runtime's own dist/.
//      It is loaded only from a DEPENDENCY-COMPLETE root: config runtimeRoot
//      when explicitly supplied, otherwise the release named by
//      <prefix>/active.json (derived from councilAskPath). "Complete" means the
//      advertised package entry (dist/index.js), dist/brief/permitted-brief.js,
//      the contracts barrel, and a zod package that satisfies the runtime's own
//      exact pin, checked statically before any import. zod is installed by the
//      installer's npm ci from the lock's integrity-pinned fetch; neither the
//      .skill archive nor the plugin tarball vendors it. An incomplete root is
//      a typed COUNCIL_RUNTIME_UNRESOLVED refusal, never a silent fallback to
//      another tree: capture copies only what resolves, so loading a
//      dependency-less root is exactly how the live zod crash happened.
//
// ponytail: the plugin does not re-implement route resolution, service
// authority, session reads, or the chamber link. Those stay in council-ask.

import { spawn as spawnProcess } from "node:child_process";
import { createHash } from "node:crypto";
import {
  closeSync,
  existsSync,
  mkdirSync,
  openSync,
  readFileSync,
  realpathSync,
  renameSync,
  statSync,
  writeFileSync,
  writeSync,
} from "node:fs";
import { builtinModules } from "node:module";
import { homedir } from "node:os";
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";

const MAX_CAPTURED_BYTES = 96 * 1024;
const MAX_RENDERED_CHARS = 4000;
const MAX_QUESTION_CHARS_DEFAULT = 1500;
const MAX_MESSAGE_CHARS_DEFAULT = 4000;

// Front-door worst case, read from the installed front door itself
// (council-runtime/frontdoor/rel-5f50666e2356/scripts/council-entry.mjs):
//   PROBE_MS                      2_500   ensureAuthority probe
//   launchctl 20_000 x <=2        40_000  repairService, one per plist
//   REPAIR_WAIT_MS 20_000 + 2_500 22_500  waitHealthy deadline + one probe
//   convene timeout          180_000
//   chamber-visual.sh         30_000
//   = 275_000 ms
// The hook must never SIGTERM a sitting that is still inside the front door's
// own budget and then report a false "did not convene". 300_000 keeps 25 s of
// headroom. A value below the floor is refused BEFORE any claim or spawn; it
// is never implemented by shortening a running sitting's timer.
export const FRONTDOOR_WORST_CASE_MS = 275000;
export const TIMEOUT_MIN_MS = 300000;
export const TIMEOUT_DEFAULT_MS = 300000;
export const TIMEOUT_MAX_MS = 600000;

// CTR-133: an unresolved exploration candidate is NOT a decision alternative.
// The observed placeholder ("option-explore") was scored 7.4 and exported as a
// GO_WITH_CONDITIONS verdict; the placeholder is named here only so preparation,
// validation, and the regression can recognise it. It is never synthesised.
export const EXPLORATION_OPTION_ID = "option-explore";
export const EXPLORATION_OPTION_LABEL =
  "Explore the question with the Council; no option has been chosen yet.";
export const BRIEF_STATE = Object.freeze({
  RECOMMENDATION: "recommendation",
  PREPARING: "preparing",
  INPUT_NEEDED: "input-needed",
});
export const PREPARATION_REQUIRED_CODE = "COUNCIL_PREPARATION_REQUIRED";
const OPTION_KINDS = new Set(["status_quo", "bounded_test", "change", "other"]);

// The public roster, not client data. The SKILL.md phrase list says any named
// seat works the same way as "ask the council".
const SEAT_PHRASES = [
  "simon sinek",
  "t. d. jakes",
  "td jakes",
  "oprah winfrey",
  "tiffany aliche",
  "russell brunson",
  "michelle obama",
  "brene brown",
  "brené brown",
  "dr. dennis kimbro",
  "dennis kimbro",
  "les brown",
];

const COUNCIL_PHRASES = [
  "ask my council of wise elders",
  "ask the council of wise elders",
  "ask the council",
  "take this decision to the council",
  "take this to the council",
  "review this plan with the council",
];

// Existing-session controls. A message that starts with one of these after the
// phrase is a read/control request, never a new sitting.
const CONTROL_PREFIXES = [
  "stop",
  "cancel",
  "pause",
  "resume",
  "read",
  "show",
  "list",
  "status",
  "verdict",
  "report",
  "explain",
  "what did",
  "what was",
  "what is the verdict",
  "continue",
];

export function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

export function expandHome(value) {
  if (typeof value !== "string" || value.length === 0) return "";
  if (value === "~") return homedir();
  return value.startsWith("~/") ? join(homedir(), value.slice(2)) : value;
}

function integerInRange(value, min, max, fallback) {
  if (value === undefined) return fallback;
  if (!Number.isInteger(value) || value < min || value > max) return null;
  return value;
}

function absolutePath(value) {
  const expanded = expandHome(value);
  if (!expanded || !isAbsolute(expanded)) return "";
  return resolve(expanded);
}

/**
 * Validate the operator config. A missing or malformed field disables the
 * plugin entirely (fail closed): no handler, no spend, no interception.
 */
export function normalizeConfig(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return { ok: false, reason: "config must be an object" };
  }
  const text = (key) => (typeof raw[key] === "string" ? raw[key].trim() : "");
  const channel = text("channel");
  if (channel !== "telegram") return { ok: false, reason: "channel must be telegram" };
  const accountId = text("accountId");
  const conversationId = text("conversationId");
  const agentId = text("agentId");
  for (const [key, value] of [["accountId", accountId], ["conversationId", conversationId], ["agentId", agentId]]) {
    if (!value) return { ok: false, reason: `${key} is required` };
  }
  if (!Array.isArray(raw.senderIds) || raw.senderIds.length === 0) {
    return { ok: false, reason: "senderIds must be a non-empty array" };
  }
  const senderIds = [];
  for (const entry of raw.senderIds) {
    if (typeof entry !== "string" || entry.trim().length === 0) {
      return { ok: false, reason: "senderIds entries must be non-empty strings" };
    }
    const value = entry.trim();
    if (!senderIds.includes(value)) senderIds.push(value);
  }
  const agentWorkspace = absolutePath(raw.agentWorkspace);
  const councilAskPath = absolutePath(raw.councilAskPath);
  const stateDir = absolutePath(raw.stateDir);
  for (const [key, value] of [
    ["agentWorkspace", agentWorkspace],
    ["councilAskPath", councilAskPath],
    ["stateDir", stateDir],
  ]) {
    if (!value) return { ok: false, reason: `${key} must be an absolute path` };
  }
  // runtimeRoot is an OVERRIDE, not the primary binding. When it is omitted the
  // plugin follows <prefix>/active.json, which already records the activated
  // release (no second pointer to drift). A supplied value is used only if it
  // is itself dependency-complete; it is never a hint to fall back from.
  const requestedRuntimeRoot =
    typeof raw.runtimeRoot === "string" ? raw.runtimeRoot.trim() : raw.runtimeRoot;
  const runtimeRoot =
    requestedRuntimeRoot === undefined || requestedRuntimeRoot === ""
      ? ""
      : absolutePath(requestedRuntimeRoot);
  if (requestedRuntimeRoot !== undefined && requestedRuntimeRoot !== "" && !runtimeRoot) {
    return { ok: false, reason: "runtimeRoot must be an absolute path when provided" };
  }
  const mode = raw.mode === undefined ? "medium" : raw.mode;
  if (!["light", "medium", "heavy"].includes(mode)) {
    return { ok: false, reason: "mode must be light, medium, or heavy" };
  }
  const displayTimezone = raw.displayTimezone === undefined ? "UTC" : text("displayTimezone");
  if (!displayTimezone) return { ok: false, reason: "displayTimezone must be a non-empty string" };
  const maxQuestionChars = integerInRange(raw.maxQuestionChars, 1, 4000, MAX_QUESTION_CHARS_DEFAULT);
  const maxMessageChars = integerInRange(raw.maxMessageChars, 64, 20000, MAX_MESSAGE_CHARS_DEFAULT);
  // An out-of-range hook budget is a config fault, not something to clamp: a
  // too-short value would SIGTERM a sitting that already started and report a
  // false "did not convene". Keep the plugin registered and refuse typed,
  // before any claim or spawn (fail closed before spend). Clamping is never
  // used, so a running sitting is never truncated.
  const requestedTimeoutMs = raw.timeoutMs === undefined ? TIMEOUT_DEFAULT_MS : raw.timeoutMs;
  let timeoutMs = TIMEOUT_DEFAULT_MS;
  let timeoutBlocked = null;
  if (
    !Number.isInteger(requestedTimeoutMs) ||
    requestedTimeoutMs < TIMEOUT_MIN_MS ||
    requestedTimeoutMs > TIMEOUT_MAX_MS
  ) {
    timeoutBlocked = Object.freeze({
      code: "COUNCIL_TIMEOUT_CONFIG_INVALID",
      detail: `timeoutMs ${JSON.stringify(requestedTimeoutMs)} is outside ${TIMEOUT_MIN_MS}..${TIMEOUT_MAX_MS}; the front door's own worst case is ${FRONTDOOR_WORST_CASE_MS} ms.`,
      action: `Set timeoutMs to ${TIMEOUT_DEFAULT_MS} in the council-before-dispatch plugin config, then resend.`,
    });
  } else {
    timeoutMs = requestedTimeoutMs;
  }
  const staleClaimMs = integerInRange(raw.staleClaimMs, 60000, 86400000, 900000);
  if (maxQuestionChars === null) return { ok: false, reason: "maxQuestionChars out of range" };
  if (maxMessageChars === null) return { ok: false, reason: "maxMessageChars out of range" };
  if (maxQuestionChars > maxMessageChars) {
    return { ok: false, reason: "maxQuestionChars must not exceed maxMessageChars" };
  }
  if (staleClaimMs === null) return { ok: false, reason: "staleClaimMs out of range" };
  return {
    ok: true,
    config: Object.freeze({
      channel,
      accountId,
      conversationId,
      senderIds: Object.freeze(senderIds),
      agentId,
      agentWorkspace,
      councilAskPath,
      runtimeRoot,
      stateDir,
      mode,
      displayTimezone,
      maxQuestionChars,
      maxMessageChars,
      timeoutMs,
      timeoutBlocked,
      staleClaimMs,
    }),
  };
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Whitespace-tolerant, anchored phrase match. The literal observed Telegram ask
// used two spaces ("ASK THE  COUNCIL"), so a plain prefix compare never matched
// it. Matching is still anchored at the start of the original text, and the
// boundary is checked on the original string so "councils" is not an ask.
function phraseRegex(phrase) {
  const body = phrase.split(/\s+/).map(escapeRegex).join("\\s+");
  return new RegExp(`^${body}`, "i");
}

// Longest phrase first: "ask the council of wise elders" must win over
// "ask the council" so the remainder is not "of wise elders ...".
const PHRASE_PATTERNS = [
  ...COUNCIL_PHRASES,
  ...SEAT_PHRASES.map((seat) => `ask the ${seat} seat`),
]
  .sort((a, b) => b.length - a.length)
  .map((phrase) => ({ phrase, regex: phraseRegex(phrase) }));

function hasPhraseBoundary(raw, end) {
  const next = raw.slice(end, end + 1);
  return next === "" || !/[a-z0-9]/i.test(next);
}

function trimQuestion(value) {
  return value.replace(/^[\s:,\-–—]+/, "").trim();
}

function isControlRequest(question) {
  const lower = question.toLowerCase().replace(/\s+/g, " ").trim();
  return CONTROL_PREFIXES.some((prefix) => lower === prefix || lower.startsWith(`${prefix} `));
}

/**
 * Extract the ORIGINAL question as data.
 *
 * Returns one of:
 *   { matched: true, question }
 *   { matched: false, reason }                            not an ask / a control
 *   { matched: false, rejected: { code, detail, action } } an explicit ask that
 *       cannot be used as-is. It MUST be answered as a typed refusal, never
 *       dropped to the model turn, or the model invents a GO again.
 */
export function extractQuestion(text, config) {
  if (typeof text !== "string") return { matched: false, reason: "not text" };
  const raw = text.trim();
  if (!raw) return { matched: false, reason: "empty message" };
  if (raw.startsWith(">")) return { matched: false, reason: "quoted prompt" };
  if (/^forwarded\b/i.test(raw)) return { matched: false, reason: "forwarded prompt" };

  for (const { regex } of PHRASE_PATTERNS) {
    const match = regex.exec(raw);
    if (!match) continue;
    const end = match[0].length;
    if (!hasPhraseBoundary(raw, end)) continue;
    if (raw.length > config.maxMessageChars) {
      return {
        matched: false,
        rejected: {
          code: "COUNCIL_ASK_TOO_LONG",
          detail: `The message is ${raw.length} characters; the limit is ${config.maxMessageChars}.`,
          action: "Send a shorter explicit Council ask.",
        },
      };
    }
    const question = trimQuestion(raw.slice(end));
    if (!question) {
      return {
        matched: false,
        rejected: {
          code: "COUNCIL_ASK_EMPTY",
          detail: "The Council phrase was recognized but no question followed it.",
          action: "Send the phrase followed by the decision or question.",
        },
      };
    }
    if (question.length > config.maxQuestionChars) {
      return {
        matched: false,
        rejected: {
          code: "COUNCIL_ASK_TOO_LONG",
          detail: `The question is ${question.length} characters; the limit is ${config.maxQuestionChars}.`,
          action: "Send a shorter question; put supporting detail in permitted context.",
        },
      };
    }
    if (/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/.test(question)) {
      return {
        matched: false,
        rejected: {
          code: "COUNCIL_ASK_INVALID",
          detail: "The question contains control characters.",
          action: "Resend the ask as plain text.",
        },
      };
    }
    if (isControlRequest(question)) return { matched: false, reason: "session control request" };
    return { matched: true, question };
  }
  return { matched: false, reason: "not an explicit Council ask" };
}

/**
 * Trust boundary. The before_dispatch call site has no isAuthorizedSender
 * gate, so this function is the equivalent binding: exact account, channel,
 * sender, DM (not group), and target agent session. Missing trustworthy
 * context is unhandled, never assumed.
 */
export function classifyInbound({ event, ctx, config }) {
  if (!event || !ctx) return { matched: false, reason: "missing event or context" };
  // deriveInboundMessageHookContext sets channelId from the transport name
  // (OriginatingChannel / Surface / Provider), while conversationId is the
  // actual chat binding (OriginatingTo / To). Bind one to the configured
  // transport and the other to the configured conversation.
  if (event.channel !== config.channel) return { matched: false, reason: "channel mismatch" };
  if (ctx.channelId !== config.channel) return { matched: false, reason: "channelId mismatch" };
  if (typeof ctx.conversationId !== "string" || ctx.conversationId !== config.conversationId) {
    return { matched: false, reason: "conversationId mismatch" };
  }
  if (typeof ctx.accountId !== "string" || ctx.accountId !== config.accountId) {
    return { matched: false, reason: "account mismatch" };
  }
  if (typeof event.senderId !== "string" || typeof ctx.senderId !== "string") {
    return { matched: false, reason: "sender absent" };
  }
  if (event.senderId !== ctx.senderId) return { matched: false, reason: "sender mismatch" };
  if (!config.senderIds.includes(event.senderId)) return { matched: false, reason: "sender not allowed" };
  if (event.isGroup !== false) return { matched: false, reason: "not a direct message" };
  if (event.replyToIsQuote === true) return { matched: false, reason: "quoted historical prompt" };
  // NOTE: before_dispatch's event/ctx mapper sets no senderIsBot field, so the
  // sender allowlist above is the actual bot/external control. No bot check is
  // claimed here.
  if (typeof event.messageId !== "string" || typeof ctx.messageId !== "string") {
    return { matched: false, reason: "message id absent" };
  }
  if (event.messageId !== ctx.messageId) return { matched: false, reason: "message id mismatch" };
  if (typeof event.sessionKey !== "string" || typeof ctx.sessionKey !== "string") {
    return { matched: false, reason: "session key absent" };
  }
  if (event.sessionKey !== ctx.sessionKey) return { matched: false, reason: "session key mismatch" };
  const agentPrefix = `agent:${config.agentId}:`;
  if (!event.sessionKey.startsWith(agentPrefix)) {
    return { matched: false, reason: "session does not belong to the configured agent" };
  }
  const ask = extractQuestion(event.content, config);
  if (ask.matched) return { matched: true, question: ask.question };
  if (ask.rejected) return { matched: false, rejected: ask.rejected };
  return { matched: false, reason: ask.reason };
}

/**
 * Runtime closure resolution.
 *
 * The installed permitted-context builder is the Council runtime's own dist.
 * It has exactly one external dependency (the zod version pinned by the
 * runtime's package.json), and OpenClaw's package capture copies only what
 * resolves from the ORIGINAL importer path. A dependency-less root therefore
 * captures an unloadable runtime while every digest stays green (the live
 * COUNCIL_PLUGIN_ERROR / ERR_MODULE_NOT_FOUND zod crash).
 *
 * Resolution order (no fallback): explicit runtimeRoot -> <prefix>/active.json
 * -> typed refusal. The active record is the durability surface the installer
 * already writes; no second pointer is invented here.
 */
export const RUNTIME_UNRESOLVED_CODE = "COUNCIL_RUNTIME_UNRESOLVED";
export const RUNTIME_ACTIVE_SCHEMA = "wise-elders.council-runtime-active/v1";

const REQUIRED_RUNTIME_FILES = [
  "dist/brief/permitted-brief.js",
  "dist/contracts/index.js",
  "dist/contracts/schemas.js",
  "dist/index.js",
];

/**
 * The graph roots this gate walks: the release's advertised package entry
 * (runtime/package.json `exports["."]` -> dist/index.js) plus the two modules
 * loadRuntime imports. dist/contracts/schemas.js is reached through the barrel.
 *
 * Scope is exactly these three roots and their reachable modules. It is not a
 * proof over every file in dist/: an emitted module that no root reaches is not
 * checked, and a clean walk is static file evidence, never Node resolution.
 */
export const RUNTIME_CLOSURE_ENTRIES = [
  "dist/brief/permitted-brief.js",
  "dist/contracts/index.js",
  "dist/index.js",
];

const CLOSURE_MAX_FILES = 512;
const CLOSURE_MAX_BYTES = 8 * 1024 * 1024;
const CLOSURE_EXTENSIONS = /\.(js|mjs|cjs|json)$/;
const BUILTINS = new Set(builtinModules);

const EXACT_VERSION = /^\d+\.\d+\.\d+$/;
const RUNTIME_ACTION =
  "Install or repair the Council runtime with 77-council-of-wise-elders/scripts/install-runtime.mjs (it writes active.json), or set runtimeRoot to a dependency-complete release, then send a NEW explicit Council ask.";

export class RuntimeUnresolvedError extends Error {
  constructor(result) {
    super(result.detail);
    this.name = "RuntimeUnresolvedError";
    this.code = RUNTIME_UNRESOLVED_CODE;
    this.detail = result.detail;
    this.action = result.action ?? RUNTIME_ACTION;
    this.root = result.root ?? null;
  }
}

function runtimeRefusal(detail, root = null) {
  return { ok: false, code: RUNTIME_UNRESOLVED_CODE, detail, action: RUNTIME_ACTION, root };
}

function isInsidePath(parent, child) {
  const rel = relative(parent, child);
  return rel === "" || (rel !== ".." && !rel.startsWith(`..${sep}`) && !isAbsolute(rel));
}

/**
 * Static ESM module-specifier extraction. Comments and template literals are
 * skipped, and a string counts only when it is the specifier of a statement
 * level `import`/`export ... from`, the bare `import "x"` form, or `from` inside
 * such a statement. Prose inside a string is never mistaken for an import.
 * Nothing is resolved or executed.
 *
 * ponytail: a literal dynamic `import("x")` that begins a statement is not an
 * edge. The runtime entries are static barrels; extend this when a release
 * starts using that form.
 */
export function moduleSpecifiers(source) {
  const tokens = [];
  const n = source.length;
  const isWord = (c) => c !== undefined && /[A-Za-z0-9_$]/.test(c);
  let i = 0;
  let line = 1;
  while (i < n) {
    const c = source[i];
    if (c === "\n") {
      line += 1;
      i += 1;
      continue;
    }
    if (c === "/" && source[i + 1] === "/") {
      while (i < n && source[i] !== "\n") i += 1;
      continue;
    }
    if (c === "/" && source[i + 1] === "*") {
      i += 2;
      while (i < n && !(source[i] === "*" && source[i + 1] === "/")) {
        if (source[i] === "\n") line += 1;
        i += 1;
      }
      i += 2;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") {
      const quote = c;
      const startLine = line;
      let value = "";
      let closed = false;
      i += 1;
      while (i < n) {
        const d = source[i];
        if (d === "\\") {
          value += source[i + 1] ?? "";
          i += 2;
          continue;
        }
        if (d === quote) {
          i += 1;
          closed = true;
          break;
        }
        if (d === "\n") {
          line += 1;
          if (quote !== "`") break;
        }
        value += d;
        i += 1;
      }
      if (closed) tokens.push({ type: quote === "`" ? "template" : "string", value, line: startLine });
      continue;
    }
    if (isWord(c)) {
      const start = i;
      while (i < n && isWord(source[i])) i += 1;
      tokens.push({ type: "word", value: source.slice(start, i), line });
      continue;
    }
    if (!/\s/.test(c)) tokens.push({ type: "punct", value: c, line });
    i += 1;
  }

  const found = [];
  let statement = null;
  let depth = 0;
  let afterFrom = false;
  let bareImport = false;
  let previous = null;
  for (const token of tokens) {
    if (statement === null) {
      if (
        token.type === "word" &&
        (token.value === "import" || token.value === "export") &&
        (previous === null || (previous.type === "punct" && (previous.value === ";" || previous.value === "}")))
      ) {
        statement = token.value;
        depth = 0;
        afterFrom = false;
        bareImport = token.value === "import";
      }
    } else if (token.type === "punct" && (token.value === "{" || token.value === "(" || token.value === "[")) {
      depth += 1;
    } else if (token.type === "punct" && (token.value === "}" || token.value === ")" || token.value === "]")) {
      depth -= 1;
    } else if (token.type === "punct" && token.value === ";" && depth <= 0) {
      statement = null;
      depth = 0;
      afterFrom = false;
      bareImport = false;
    } else if (token.type === "word" && token.value === "from" && depth <= 0) {
      afterFrom = true;
    } else if ((token.type === "string" || token.type === "template") && depth <= 0) {
      if (afterFrom) {
        found.push({ specifier: token.value, line: token.line });
        statement = null;
      } else if (bareImport && statement === "import") {
        found.push({ specifier: token.value, line: token.line });
        statement = null;
      }
      afterFrom = false;
      bareImport = false;
    }
    previous = token;
  }
  return found;
}

/**
 * Static relative-import closure of the modules this plugin imports.
 *
 * A release is only "dependency-complete" when its own emitted graph is
 * loadable: every relative specifier carries a file extension (Node ESM never
 * appends one), every relative target exists inside the release root, and every
 * bare specifier resolves to a package installed under that root. Text and
 * file existence only: nothing is imported, resolved by Node, or executed.
 */
export function runtimeClosureProblems(root, entries = RUNTIME_CLOSURE_ENTRIES) {
  const problems = [];
  const queue = [...entries];
  const seen = new Set();
  while (queue.length > 0) {
    const relativePath = queue.pop();
    if (seen.has(relativePath)) continue;
    if (seen.size >= CLOSURE_MAX_FILES) {
      problems.push(`closure check stopped at ${CLOSURE_MAX_FILES} files; refusing an unbounded graph`);
      break;
    }
    seen.add(relativePath);
    const full = join(root, ...relativePath.split("/"));
    let size;
    try {
      const stat = statSync(full);
      if (!stat.isFile()) {
        problems.push(`${relativePath} is not a regular file`);
        continue;
      }
      size = stat.size;
    } catch {
      problems.push(`${relativePath} is missing`);
      continue;
    }
    if (size > CLOSURE_MAX_BYTES) {
      problems.push(`${relativePath} is larger than ${CLOSURE_MAX_BYTES} bytes; refusing to parse it`);
      continue;
    }
    let source;
    try {
      source = readFileSync(full, "utf8");
    } catch {
      problems.push(`${relativePath} is unreadable`);
      continue;
    }
    for (const { specifier, line } of moduleSpecifiers(source)) {
      if (specifier.startsWith("node:") || BUILTINS.has(specifier)) continue;
      if (specifier.startsWith(".") || specifier.startsWith("/")) {
        const target = resolve(dirname(full), specifier);
        if (!isInsidePath(root, target)) {
          problems.push(`${relativePath}:${line} imports ${specifier}, which leaves the release root`);
          continue;
        }
        if (!CLOSURE_EXTENSIONS.test(specifier)) {
          problems.push(
            `${relativePath}:${line} imports ${specifier} with no file extension; Node ESM never appends one`,
          );
          continue;
        }
        let present = false;
        try {
          present = statSync(target).isFile();
        } catch {
          present = false;
        }
        if (!present) {
          problems.push(`${relativePath}:${line} imports ${specifier}, which does not exist`);
          continue;
        }
        if (/\.(js|mjs)$/.test(specifier)) {
          queue.push(relative(root, target).split(sep).join("/"));
        }
      } else if (!specifier.startsWith("#")) {
        const name = specifier.startsWith("@")
          ? specifier.split("/").slice(0, 2).join("/")
          : specifier.split("/")[0];
        const packageJson = join(root, "node_modules", ...name.split("/"), "package.json");
        if (!existsSync(packageJson)) {
          problems.push(`${relativePath}:${line} imports ${specifier}, but ${name} is not installed under the release root`);
        }
      }
    }
  }
  return problems;
}

/**
 * Static preflight. Never imports: checks the advertised package entry, the
 * plugin's two import points, the contracts barrel, the runtime's own exact
 * zod pin, that the installed zod package exists with an ESM import target on
 * disk, and that the graph reachable from all three roots is loadable under
 * Node ESM.
 */
export function runtimeRootProblems(root) {
  const problems = [];
  for (const file of REQUIRED_RUNTIME_FILES) {
    try {
      if (!statSync(join(root, file)).isFile()) problems.push(`${file} is not a regular file`);
    } catch {
      problems.push(`${file} is missing`);
    }
  }
  const runtimePackage = readJson(join(root, "package.json"));
  const pin = runtimePackage?.dependencies?.zod;
  if (typeof pin !== "string" || pin.length === 0) {
    problems.push("package.json does not declare a zod dependency");
  }
  const zodRoot = join(root, "node_modules", "zod");
  const zodPackage = readJson(join(zodRoot, "package.json"));
  if (!zodPackage) {
    problems.push("node_modules/zod/package.json is missing");
    return problems;
  }
  if (typeof pin === "string" && EXACT_VERSION.test(pin) && zodPackage.version !== pin) {
    problems.push(
      `node_modules/zod is ${String(zodPackage.version ?? "unversioned")}, the runtime declares ${pin}`,
    );
  }
  const importTarget = zodPackage.exports?.["."]?.import ?? zodPackage.module ?? zodPackage.main;
  if (typeof importTarget !== "string" || importTarget.length === 0) {
    problems.push("zod package declares no ESM import target");
  } else {
    const target = join(zodRoot, importTarget.replace(/^\.\//, ""));
    try {
      if (!statSync(target).isFile()) problems.push(`zod import target ${importTarget} is not a regular file`);
    } catch {
      problems.push(`zod import target ${importTarget} is missing`);
    }
  }
  // Presence is not loadability: the emitted graph must resolve under Node ESM.
  // Only entries that exist are walked, so a missing file keeps its own message.
  const presentEntries = RUNTIME_CLOSURE_ENTRIES.filter((entry) => {
    try {
      return statSync(join(root, ...entry.split("/"))).isFile();
    } catch {
      return false;
    }
  });
  problems.push(...runtimeClosureProblems(root, presentEntries));
  return problems;
}

/**
 * Resolve one dependency-complete runtime root. Returns
 *   { ok: true, root, source, releaseId }
 *   { ok: false, code: COUNCIL_RUNTIME_UNRESOLVED, detail, action, root }
 * An explicit override is validated too; it is never silently replaced by the
 * active release and the active release is never silently replaced by a
 * sibling directory.
 */
export function resolveRuntimeRoot({ runtimeRoot = "", councilAskPath = "" } = {}) {
  if (typeof runtimeRoot === "string" && runtimeRoot.length > 0) {
    let root;
    try {
      root = realpathSync(runtimeRoot);
    } catch {
      return runtimeRefusal(`runtimeRoot ${runtimeRoot} does not exist`, runtimeRoot);
    }
    const problems = runtimeRootProblems(root);
    if (problems.length > 0) {
      return runtimeRefusal(
        `runtimeRoot ${root} is not dependency-complete: ${problems.join("; ")}`,
        root,
      );
    }
    return { ok: true, root, source: "config", releaseId: null };
  }

  if (typeof councilAskPath !== "string" || councilAskPath.length === 0) {
    return runtimeRefusal(
      "no runtimeRoot is configured and councilAskPath is absent, so the activated release cannot be located",
    );
  }
  // install-runtime.mjs + wire.sh place council-ask at <prefix>/bin/council-ask
  // and active.json at <prefix>/active.json.
  const prefix = dirname(dirname(councilAskPath));
  let prefixReal;
  try {
    prefixReal = realpathSync(prefix);
  } catch {
    return runtimeRefusal(`the runtime prefix ${prefix} (derived from councilAskPath) does not exist`, prefix);
  }
  const activePath = join(prefixReal, "active.json");
  const active = readJson(activePath);
  if (!active) {
    return runtimeRefusal(
      `no readable runtime activation record at ${activePath}; the plugin will not guess a runtime tree`,
      activePath,
    );
  }
  if (active.schema !== RUNTIME_ACTIVE_SCHEMA) {
    return runtimeRefusal(`${activePath} has schema ${String(active.schema ?? "(none)")}, expected ${RUNTIME_ACTIVE_SCHEMA}`, activePath);
  }
  if (typeof active.releaseId !== "string" || active.releaseId.length === 0) {
    return runtimeRefusal(`${activePath} records no releaseId`, activePath);
  }
  if (typeof active.releasePath !== "string" || !isAbsolute(active.releasePath)) {
    return runtimeRefusal(`${activePath} records no absolute releasePath`, activePath);
  }
  let releasesReal;
  let root;
  try {
    releasesReal = realpathSync(join(prefixReal, "releases"));
  } catch {
    return runtimeRefusal(`the release root ${join(prefixReal, "releases")} does not exist`, activePath);
  }
  try {
    root = realpathSync(active.releasePath);
  } catch {
    return runtimeRefusal(`the activated release ${active.releasePath} does not exist`, active.releasePath);
  }
  if (!isInsidePath(releasesReal, root)) {
    return runtimeRefusal(
      `the activated release ${root} is outside ${releasesReal}; refusing an unscoped runtime root`,
      root,
    );
  }
  if (basename(root) !== active.releaseId) {
    return runtimeRefusal(
      `the activated release directory ${root} does not match releaseId ${active.releaseId}`,
      root,
    );
  }

  // The receipt is part of the same activation record. Verify its scope and
  // that it describes this release before trusting the tree.
  if (typeof active.receiptPath !== "string" || !isAbsolute(active.receiptPath)) {
    return runtimeRefusal(`${activePath} records no absolute receiptPath`, activePath);
  }
  let receiptsReal;
  let receiptReal;
  try {
    receiptsReal = realpathSync(join(prefixReal, "receipts"));
    receiptReal = realpathSync(active.receiptPath);
  } catch {
    return runtimeRefusal(`the activation receipt ${active.receiptPath} does not exist`, active.receiptPath);
  }
  if (!isInsidePath(receiptsReal, receiptReal)) {
    return runtimeRefusal(
      `the activation receipt ${receiptReal} is outside ${receiptsReal}; refusing`,
      receiptReal,
    );
  }
  const receipt = readJson(receiptReal);
  if (!receipt) {
    return runtimeRefusal(`the activation receipt ${receiptReal} is unreadable`, receiptReal);
  }
  if (receipt.releaseId !== active.releaseId) {
    return runtimeRefusal(
      `the activation receipt ${receiptReal} describes ${String(receipt.releaseId ?? "(none)")}, not ${active.releaseId}`,
      receiptReal,
    );
  }
  for (const field of ["artifactDigest", "sourceManifestDigest"]) {
    if (
      typeof active[field] === "string" &&
      typeof receipt[field] === "string" &&
      active[field] !== receipt[field]
    ) {
      return runtimeRefusal(
        `active.json and the activation receipt disagree on ${field}; refusing to load an uncatalogued build`,
        root,
      );
    }
  }

  const problems = runtimeRootProblems(root);
  if (problems.length > 0) {
    return runtimeRefusal(
      `the activated release ${root} is not dependency-complete: ${problems.join("; ")}`,
      root,
    );
  }
  return { ok: true, root, source: "active.json", releaseId: active.releaseId, activePath };
}

/**
 * Load the installed permitted-context builder and strict brief validator.
 * These are the Council runtime's own modules, not a second implementation.
 * A missing/incomplete root becomes one typed refusal BEFORE any import, so a
 * dependency-less tree can never be captured as if it were loadable.
 */
export async function loadRuntime({
  runtimeRoot,
  councilAskPath,
  importModule = (url) => import(url),
}) {
  const resolved = resolveRuntimeRoot({ runtimeRoot, councilAskPath });
  if (!resolved.ok) throw new RuntimeUnresolvedError(resolved);
  let permitted;
  let contracts;
  try {
    [permitted, contracts] = await Promise.all([
      importModule(pathToFileURL(join(resolved.root, "dist", "brief", "permitted-brief.js")).href),
      importModule(pathToFileURL(join(resolved.root, "dist", "contracts", "index.js")).href),
    ]);
  } catch (error) {
    throw new RuntimeUnresolvedError({
      detail: `the dependency-complete root ${resolved.root} still failed to load: ${String(error?.message ?? error)}`,
      action: RUNTIME_ACTION,
      root: resolved.root,
    });
  }
  if (typeof permitted.assembleBrief !== "function") {
    throw new RuntimeUnresolvedError({
      detail: `${resolved.root}/dist/brief/permitted-brief.js does not export assembleBrief`,
      action: RUNTIME_ACTION,
      root: resolved.root,
    });
  }
  if (typeof contracts.validateDecisionBrief !== "function") {
    throw new RuntimeUnresolvedError({
      detail: `${resolved.root}/dist/contracts/index.js does not export validateDecisionBrief`,
      action: RUNTIME_ACTION,
      root: resolved.root,
    });
  }
  // CTR-133 optional preparation/proposal stage. An older dependency-complete
  // release without this module still loads; buildBrief then reports
  // input-needed instead of inventing an option. The stage owns its own
  // ONE-request budget and receives the configured provider port from the
  // caller; this plugin never selects a provider.
  let prepareProposals = null;
  try {
    const stage = await importModule(
      pathToFileURL(join(resolved.root, "dist", "brief", "proposal-stage.js")).href,
    );
    if (typeof stage?.prepareProposals === "function") {
      prepareProposals = stage.prepareProposals;
    }
  } catch {
    prepareProposals = null;
  }
  return {
    assembleBrief: permitted.assembleBrief,
    validateDecisionBrief: contracts.validateDecisionBrief,
    prepareProposals,
  };
}

function safeRelative(value) {
  if (typeof value !== "string" || !value || isAbsolute(value)) return null;
  const normalized = value.split("\\").join("/");
  if (normalized.startsWith("..") || normalized.includes("/../")) return null;
  return normalized;
}

function idFromQuestion(question, now, salt) {
  return `${salt}-${sha256(`${question}\u0000${now}\u0000${salt}`).slice(0, 16)}`;
}

/**
 * A known unresolved exploration candidate, recognised by its exact id or its
 * exact/legacy label. Used in three places, never as an option factory:
 * buildBrief (never synthesise it), the proposal stage's filter, and the
 * runtime verdict gate (never publish it as a scored recommendation).
 */
export function isUnresolvedExplorationOption(option) {
  if (!option || typeof option !== "object") return false;
  if (option.id === EXPLORATION_OPTION_ID) return true;
  if (typeof option.label !== "string") return false;
  const label = option.label.trim().toLowerCase().replace(/\s+/g, " ");
  return (
    label === EXPLORATION_OPTION_LABEL.toLowerCase() ||
    (label.startsWith("explore the question with the council") &&
      label.includes("no option has been chosen"))
  );
}

function optionIsSubstantive(option) {
  return (
    option &&
    typeof option === "object" &&
    typeof option.label === "string" &&
    option.label.trim().length > 0 &&
    !isUnresolvedExplorationOption(option)
  );
}

/**
 * The honest no-options result. It is NOT a brief and NOT a failure of the
 * Council: the question is exploratory, so no scored decision exists yet.
 * `request_budget` is the number of provider requests this preparation may
 * use; it is 0 when no configured route is available, never an unbounded retry.
 */
function preparationRequired({ state, question, detail, action, missing = [], requestBudget = 0 }) {
  return {
    ok: false,
    code: PREPARATION_REQUIRED_CODE,
    state,
    detail,
    action,
    preparation: {
      state,
      question,
      request_budget: requestBudget,
      requires_new_inference: state === BRIEF_STATE.PREPARING,
      missing,
      policy:
        "No alternative is invented. Proposed alternatives are labelled as proposed strategies, never as client facts; no catalog, price, or business fact is assumed.",
    },
  };
}

/**
 * Compose an honest DecisionBrief. The permitted-context builder supplies
 * context; the original question is preserved verbatim. Facts are only
 * included when their source file can be hashed into the evidence manifest.
 * Constraints whose hardness is unknown and decision flags that were not
 * supplied are carried as explicit unknowns, never guessed.
 */
export async function buildBrief({
  question,
  workspace,
  displayTimezone,
  now,
  runtimeRoot,
  councilAskPath,
  loadRuntimeImpl = loadRuntime,
  readFile = readFileSync,
  prepareProposals = null,
  proposalInfer = null,
  maxFacts = 40,
}) {
  let runtime;
  try {
    runtime = await loadRuntimeImpl({ runtimeRoot, councilAskPath });
  } catch (error) {
    return {
      ok: false,
      code: error?.code === RUNTIME_UNRESOLVED_CODE ? RUNTIME_UNRESOLVED_CODE : "COUNCIL_BRIEF_BUILD_FAILED",
      detail: String(error?.detail ?? error?.message ?? error),
      action: error?.action ?? "Fix the Council runtime root, then send a new explicit Council ask.",
    };
  }
  const permitted = runtime.assembleBrief({
    door: "openclaw",
    rootDir: workspace,
    decision: question,
  });
  if (!permitted || typeof permitted !== "object") {
    return { ok: false, code: "COUNCIL_BRIEF_BUILD_FAILED", detail: "permitted builder returned no brief" };
  }

  // Real alternatives above must be substantive. A legacy/placeholder entry is
  // dropped here, never promoted to a scored option, and never renamed into a
  // plausible-looking strategy.
  const options = [];
  for (const [index, label] of (permitted.options ?? []).entries()) {
    if (typeof label !== "string" || !label.trim()) continue;
    const candidate = { id: `option-permitted-${index + 1}`, label: label.trim(), kind: "other" };
    if (!optionIsSubstantive(candidate)) continue;
    options.push(candidate);
    if (options.length >= 10) break;
  }

  const proposalUnknowns = [];
  let deferredPreparation = false;
  if (options.length === 0 && typeof proposalInfer !== "function") {
    // CTR-134: this hook has NO model call of its own (before_dispatch carries
    // no inference API), so the ONE configured preparation request belongs to
    // the Council service, which owns the caller's resolved route/model. The
    // plugin forwards the question and permitted context and lets the service
    // prepare real alternatives and run the sitting. No option is invented
    // here, and an input-needed-only answer is never shipped as advice.
    deferredPreparation = true;
  } else if (options.length === 0) {
    // No real alternatives. Scored modes cannot convene honestly yet. Use the
    // runtime's ONE-request preparation stage when this release exposes it;
    // otherwise report input-needed. Neither path invents an option.
    const proposalStage =
      typeof prepareProposals === "function"
        ? prepareProposals
        : typeof runtime.prepareProposals === "function"
          ? runtime.prepareProposals
          : null;
    if (!proposalStage) {
      return preparationRequired({
        state: BRIEF_STATE.INPUT_NEEDED,
        question,
        detail:
          "The permitted context states no real alternatives and this runtime exposes no preparation stage, so there is nothing honest to score.",
        action:
          "State two to five real alternatives in the ask, or configure the preparation stage, then resend. No decision was scored.",
        missing: ["two to five real alternatives"],
      });
    }
    let prepared;
    try {
      prepared = await proposalStage(
        {
          question,
          permitted_context: {
            sources_read: Array.isArray(permitted.meta?.sources_read)
              ? permitted.meta.sources_read
              : [],
            facts: (permitted.facts ?? [])
              .filter((fact) => fact && typeof fact.statement === "string")
              .slice(0, maxFacts)
              .map((fact) => ({ statement: fact.statement, source: fact.source ?? null })),
            constraints: (permitted.constraints ?? []).filter((c) => typeof c === "string"),
            unknowns: (permitted.unknowns ?? []).filter((u) => typeof u === "string"),
          },
          display_timezone: displayTimezone,
          max_options: 5,
          request_budget: 1,
        },
        { infer: proposalInfer, max_requests: 1 },
      );
    } catch (error) {
      return preparationRequired({
        state: BRIEF_STATE.INPUT_NEEDED,
        question,
        detail: `The preparation stage failed: ${String(error?.message ?? error)}`,
        action:
          "Read the preparation error, then resend. No decision was scored and no alternative was invented.",
        missing: ["a successful preparation pass"],
        requestBudget: 1,
      });
    }
    // A caller may delegate the single preparation request to a linked consult
    // instead of awaiting it inside before_dispatch. That is the ONLY meaning of
    // `preparing`: a new inference is in flight, no sitting has started, and no
    // option exists yet. The prior session is linked by the caller; it is never
    // mutated in place.
    if (prepared && prepared.state === BRIEF_STATE.PREPARING && prepared.pending === true) {
      return preparationRequired({
        state: BRIEF_STATE.PREPARING,
        question,
        detail:
          "A linked preparation consult is running to propose alternatives for this question.",
        action:
          "Read the linked preparation consult; once it returns proposed alternatives, resend the ask with those alternatives. No decision is scored until then.",
        requestBudget: Number.isInteger(prepared.request_budget) ? prepared.request_budget : 1,
      });
    }
    const proposed = Array.isArray(prepared?.options) ? prepared.options : [];
    for (const [index, option] of proposed.entries()) {
      if (!option || typeof option.label !== "string" || !option.label.trim()) continue;
      const kind = OPTION_KINDS.has(option.kind) ? option.kind : "other";
      const candidate = {
        id: typeof option.id === "string" && option.id ? option.id : `option-proposed-${index + 1}`,
        label: option.label.trim(),
        kind,
      };
      if (!optionIsSubstantive(candidate)) continue;
      options.push(candidate);
      if (options.length >= 5) break;
    }
    if (options.length === 0) {
      return preparationRequired({
        state: BRIEF_STATE.INPUT_NEEDED,
        question,
        detail:
          prepared?.detail ??
          "The preparation stage returned no substantive alternative, so there is nothing honest to score.",
        action: "State two to five real alternatives, then resend. No decision was scored.",
        missing: Array.isArray(prepared?.missing) && prepared.missing.length > 0
          ? prepared.missing
          : ["two to five real alternatives"],
        requestBudget: 1,
      });
    }
    proposalUnknowns.push(
      "The alternatives above are PROPOSED strategies generated from the question and permitted context by the configured provider; they are not client-chosen facts and must be confirmed before any irreversible action.",
    );
    for (const statement of prepared?.unknowns ?? []) {
      if (typeof statement === "string" && statement.trim()) {
        proposalUnknowns.push(statement.trim());
      }
    }
  }

  const evidenceManifest = [];
  const evidenceBySource = new Map();
  const facts = [];
  const unknowns = [];
  for (const [index, fact] of (permitted.facts ?? []).entries()) {
    if (facts.length >= maxFacts) break;
    if (!fact || typeof fact.statement !== "string" || !fact.statement.trim()) continue;
    const source = safeRelative(fact.source);
    if (!source) {
      unknowns.push("A permitted-context fact had an unsafe source path and was omitted.");
      continue;
    }
    let evidenceId = evidenceBySource.get(source);
    if (!evidenceId) {
      let digest;
      try {
        digest = sha256(readFile(join(workspace, source)));
      } catch {
        unknowns.push(`A permitted-context fact from ${source} could not be evidence-bound and was omitted.`);
        continue;
      }
      evidenceId = `ev-${evidenceBySource.size + 1}`;
      evidenceBySource.set(source, evidenceId);
      evidenceManifest.push({
        evidence_id: evidenceId,
        sha256: digest,
        source_kind: "client_document",
        locator: source,
      });
    }
    facts.push({
      id: `fact-${index + 1}`,
      statement: fact.statement.trim(),
      evidence_ids: [evidenceId],
    });
  }

  for (const [index, statement] of (permitted.constraints ?? []).entries()) {
    if (typeof statement !== "string" || !statement.trim()) continue;
    unknowns.push(`Constraint stated in permitted context, hardness not established (${index + 1}): ${statement.trim()}`);
    if (unknowns.length >= 40) break;
  }
  for (const statement of permitted.unknowns ?? []) {
    if (typeof statement === "string" && statement.trim()) unknowns.push(statement.trim());
    if (unknowns.length >= 60) break;
  }

  unknowns.unshift(
    "Decision flags were not supplied, so no critical-domain classification was performed.",
    "The Council must not assume a product catalog, price list, or business facts that were not supplied.",
  );
  if (facts.length === 0) {
    unknowns.push("No evidence-bound facts were supplied with this ask.");
  }
  for (const statement of proposalUnknowns) unknowns.push(statement);

  const seenUnknowns = new Set();
  const unknownFacts = [];
  for (const statement of unknowns) {
    if (typeof statement !== "string") continue;
    const trimmed = statement.trim();
    if (!trimmed || seenUnknowns.has(trimmed)) continue;
    seenUnknowns.add(trimmed);
    unknownFacts.push({
      id: `unknown-${sha256(trimmed).slice(0, 12)}`,
      statement: trimmed,
      evidence_ids: [],
    });
    if (unknownFacts.length >= 80) break;
  }

  const brief = {
    schema_version: "wise-elders.brief/v1",
    brief_id: idFromQuestion(question, now, "brief"),
    session_id: idFromQuestion(question, now, "session"),
    revision: 1,
    question,
    facts,
    assumptions: [],
    unknowns: unknownFacts,
    constraints: [],
    options,
    relevance_weights: {},
    critical_domains: [],
    evidence_manifest: evidenceManifest,
    private_preference_ref:
      typeof permitted.private_preference_ref === "string" ? permitted.private_preference_ref : null,
    created_at: now,
    display_timezone: displayTimezone,
  };

  // CTR-134: an exploratory question with no real alternatives is forwarded as
  // a preparation request, not scored and not answered with input-needed only.
  // `options: []` is the explicit enqueue token: the service prepares the
  // alternatives with ONE request on the caller's own route, then validates
  // the resulting brief (the DecisionBrief contract keeps its min(1) option
  // rule; nothing is relaxed here and this token is never persisted as one).
  if (deferredPreparation && options.length === 0) {
    return {
      ok: true,
      brief,
      state: BRIEF_STATE.PREPARING,
      preparation: {
        state: BRIEF_STATE.PREPARING,
        request_budget: 1,
        requires_new_inference: true,
        missing: [],
      },
    };
  }

  const check = runtime.validateDecisionBrief(brief);
  if (!check || check.ok !== true) {
    const issues = Array.isArray(check?.issues)
      ? check.issues.slice(0, 8).map((issue) => `${issue.path || "brief"}: ${issue.message}`)
      : [];
    return {
      ok: false,
      code: "COUNCIL_BRIEF_INVALID",
      detail: issues.length > 0 ? issues.join("; ") : "the composed brief failed contract validation",
    };
  }
  return { ok: true, brief, state: BRIEF_STATE.RECOMMENDATION };
}

export function writeBriefFile({ stateDir, key, brief }) {
  const dir = join(stateDir, "briefs");
  mkdirSync(dir, { recursive: true, mode: 0o700 });
  const path = join(dir, `${key}.json`);
  const tmp = `${path}.tmp.${process.pid}`;
  writeFileSync(tmp, `${JSON.stringify(brief)}\n`, { mode: 0o600 });
  renameSync(tmp, path);
  return path;
}

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return null;
  }
}

export function claimKey({ config, event }) {
  return sha256(`${config.accountId}\u0000${config.conversationId}\u0000${event.messageId}`).slice(0, 32);
}

/**
 * Durable duplicate-message claim. The claim file is created with O_EXCL
 * BEFORE any brief build or front-door call. A completed result is returned
 * verbatim to a replay, so one message can never spend twice.
 */
export function claimMessage({ config, key, nowMs }) {
  const dir = join(config.stateDir, "claims");
  try {
    mkdirSync(dir, { recursive: true, mode: 0o700 });
  } catch (error) {
    // State-dir faults are a typed refusal, never an escape to the caller: an
    // authorized explicit ask must not fall through to the model turn.
    return {
      ok: false,
      reason: "error",
      text: renderFailure(
        "COUNCIL_CLAIM_FAILED",
        String(error?.message ?? error),
        `Fix the plugin state directory (${config.stateDir}) permissions/ownership, then resend.`,
      ),
    };
  }
  const resultPath = join(dir, `${key}.result.json`);
  const claimPath = join(dir, `${key}.claim.json`);

  if (existsSync(resultPath)) {
    const result = readJson(resultPath);
    if (result && typeof result.text === "string") {
      return { ok: false, reason: "duplicate", text: result.text };
    }
  }

  const create = () => {
    const fd = openSync(claimPath, "wx", 0o600);
    try {
      writeSync(
        fd,
        `${JSON.stringify({ key, created_at: new Date(nowMs).toISOString(), pid: process.pid, status: "inflight" })}\n`,
      );
    } finally {
      closeSync(fd);
    }
  };

  try {
    create();
  } catch (error) {
    if (error?.code !== "EEXIST") {
      return { ok: false, reason: "error", text: renderFailure("COUNCIL_CLAIM_FAILED", String(error?.message ?? error)) };
    }
    const existing = readJson(claimPath);
    const created = Date.parse(existing?.created_at ?? "");
    if (!Number.isFinite(created) || nowMs - created > config.staleClaimMs) {
      try {
        renameSync(claimPath, `${claimPath}.stale.${nowMs}`);
        create();
      } catch (retryError) {
        return {
          ok: false,
          reason: "error",
          text: renderFailure("COUNCIL_CLAIM_FAILED", String(retryError?.message ?? retryError)),
        };
      }
    } else {
      return {
        ok: false,
        reason: "inflight",
        text: "A Council request for this message is already in progress. No second sitting was started.",
      };
    }
  }
  return { ok: true, claimPath, resultPath };
}

export function finishClaim({ claim, text, status, nowMs }) {
  if (!claim || !claim.claimPath) return;
  try {
    const payload = { status, text, at: new Date(nowMs).toISOString() };
    const tmp = `${claim.resultPath}.tmp.${process.pid}`;
    writeFileSync(tmp, `${JSON.stringify(payload)}\n`, { mode: 0o600 });
    renameSync(tmp, claim.resultPath);
    writeFileSync(claim.claimPath, `${JSON.stringify({ status, finished_at: payload.at })}\n`, { mode: 0o600 });
  } catch {
    // The claim is the safety property; a failed result write costs a replay
    // its cached text, never a second spend (the claim file still exists).
  }
}

export function redact(value, limit = 1200) {
  let text = String(value ?? "").replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, " ");
  text = text.replace(/\b(api[_-]?key|token|secret|password)\s*[=:]\s*\S+/gi, "$1=[redacted]");
  text = text.replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit)}...` : text;
}

export function renderFailure(code, detail, action) {
  const lines = [
    "Council did not convene.",
    `  error: ${redact(code, 120)}`,
  ];
  if (detail) lines.push(`  detail: ${redact(detail)}`);
  if (action) lines.push(`  next: ${redact(action)}`);
  return lines.join("\n");
}

/**
 * Preparation is a distinct state, not a failure and not a verdict. It carries
 * no GO/approval language, no score, and no invented option.
 */
export function renderPreparation(result) {
  const preparation = result?.preparation ?? {};
  const preparing = result?.state === BRIEF_STATE.PREPARING;
  const lines = [
    preparing
      ? "Council is preparing real alternatives. No decision has been scored yet."
      : "Council needs the real alternatives before it can score a decision.",
  ];
  if (result?.detail) lines.push(`  detail: ${redact(result.detail)}`);
  const missing = Array.isArray(preparation.missing) ? preparation.missing.filter(Boolean) : [];
  if (!preparing && missing.length > 0) {
    lines.push(`  missing: ${redact(missing.slice(0, 5).join("; "), 400)}`);
  }
  if (Number.isInteger(preparation.request_budget) && preparation.request_budget > 0) {
    lines.push(`  provider requests for preparation: ${preparation.request_budget}`);
  }
  if (result?.action) lines.push(`  next: ${redact(result.action)}`);
  return lines.join("\n");
}

export function renderSuccess(payload) {
  const lines = [`Council convened: ${redact(payload.session_id, 200)}`];
  if (payload.mode) lines.push(`  mode: ${redact(payload.mode, 40)}`);
  if (payload.route_id) lines.push(`  route: ${redact(payload.route_id, 120)}`);
  if (payload.model_label) lines.push(`  model: ${redact(payload.model_label, 120)}`);
  if (payload.service_origin) lines.push(`  service: ${redact(payload.service_origin, 200)}`);
  // CTR-134: the alternatives were prepared by the service's ONE request on
  // this same route before the sitting. They are proposals, not client facts,
  // and they are never presented as a catalog, price or result.
  if (payload.preparation && typeof payload.preparation === "object") {
    lines.push(
      "  alternatives: proposed by the configured model from the question and permitted context, then scored as PROPOSED options; they are not client-chosen facts, catalog items, prices or results.",
    );
    if (Number.isInteger(payload.preparation.request_count)) {
      lines.push(`  preparation provider requests: ${payload.preparation.request_count} of ${payload.preparation.request_budget ?? 1}`);
    }
  }
  // SKILL.md forbids sending a 127.0.0.1 link, and a fixture host is a dead
  // link for a client. The front door reports both facts; print the link only
  // when it is positively client-safe.
  const link = typeof payload.chamber_link === "string" ? payload.chamber_link.trim() : "";
  if (link && payload.chamber_link_client_safe === true) {
    lines.push(`  Chamber link: ${redact(link, 500)}`);
  } else if (link && payload.chamber_link_local === true) {
    lines.push(
      "  this link is loopback: never send it to a client; say the Council is running and the private link follows with a later council.",
    );
  } else if (link && payload.chamber_link_client_safe === false) {
    lines.push(
      "  this link points at a documentation/fixture host (example.com, .test, .invalid): it is a dead link for a client. Report the Council as running and say the private link follows; fix public_origin before sending anything.",
    );
  } else if (link) {
    lines.push("  Chamber link withheld: the front door did not report whether the link is client-safe.");
  } else {
    lines.push("  Chamber link unavailable; do not invent one.");
  }
  const prior = Array.isArray(payload.prior_completed_same_question) ? payload.prior_completed_same_question : [];
  if (prior.length > 0) {
    const ids = prior.slice(0, 5).map((item) => redact(item?.session_id ?? "", 80)).filter(Boolean);
    if (ids.length > 0) {
      lines.push(`  note: a prior COMPLETED sitting on this question exists (${ids.join(", ")}); this ask opened a NEW session.`);
    }
  }
  if (payload.desktop_pop && !/^opened/.test(String(payload.desktop_pop))) {
    lines.push(`  desktop pop: ${redact(payload.desktop_pop, 160)}`);
  }
  const text = lines.join("\n");
  return text.length > MAX_RENDERED_CHARS ? `${text.slice(0, MAX_RENDERED_CHARS)}...` : text;
}

function parseRefusal(text) {
  const raw = String(text ?? "");
  const start = raw.indexOf("{");
  const end = raw.lastIndexOf("}");
  if (start === -1 || end <= start) return null;
  try {
    const parsed = JSON.parse(raw.slice(start, end + 1));
    if (parsed?.ok === false) {
      return {
        code: parsed.error?.code ?? parsed.code ?? "COUNCIL_FRONTDOOR_REFUSED",
        message: parsed.error?.message ?? parsed.detail?.summary ?? parsed.detail ?? "the front door refused",
        action: parsed.error?.action ?? null,
      };
    }
  } catch {
    /* plain-text refusal stays a text refusal */
  }
  return null;
}

/**
 * Spawn the supported front door with argv only. No shell, bounded output,
 * hard timeout, and the calling agent's workspace as cwd so the accepted
 * CTR-123 caller-route patch sees that agent's own configured model.
 */
export function runFrontDoor({ config, briefPath, deps = {} }) {
  const spawnImpl = deps.spawn ?? spawnProcess;
  const env = deps.env ?? process.env;
  if (!env || typeof env.HOME !== "string" || env.HOME.length === 0) {
    return Promise.resolve({
      ok: false,
      code: "COUNCIL_ENV_UNTRUSTWORTHY",
      detail: "HOME is absent; the caller route cannot be resolved safely",
      action: "Run the Gateway with the operator account's HOME, then retry.",
    });
  }
  // The accepted caller-route patch deliberately treats a workspace override
  // as ambiguous and returns null. Refuse before spending instead of letting
  // it fall through to ROUTE_CHOICE_REQUIRED.
  if (typeof env.OPENCLAW_WORKSPACE_DIR === "string" && env.OPENCLAW_WORKSPACE_DIR.trim().length > 0) {
    return Promise.resolve({
      ok: false,
      code: "COUNCIL_ENV_UNTRUSTWORTHY",
      detail: "OPENCLAW_WORKSPACE_DIR is set, so the calling agent is ambiguous",
      action: "Remove the workspace override from the Gateway environment, then retry.",
    });
  }
  const args = ["ask", "--brief", briefPath, "--mode", config.mode, "--json"];
  return new Promise((resolvePromise) => {
    let child;
    try {
      child = spawnImpl(config.councilAskPath, args, {
        cwd: config.agentWorkspace,
        env,
        stdio: ["ignore", "pipe", "pipe"],
        shell: false,
      });
    } catch (error) {
      resolvePromise({
        ok: false,
        code: "COUNCIL_SPAWN_FAILED",
        detail: String(error?.message ?? error),
        action: "Check councilAskPath and its executable bit.",
      });
      return;
    }

    let stdout = "";
    let stderr = "";
    let tooLarge = false;
    let timedOut = false;
    let settled = false;
    let timer;
    let hardTimer;

    const finish = (value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      clearTimeout(hardTimer);
      resolvePromise(value);
    };
    const collect = (target, chunk) => {
      const text = Buffer.isBuffer(chunk) ? chunk.toString("utf8") : String(chunk);
      if (target.length + text.length > MAX_CAPTURED_BYTES) {
        tooLarge = true;
        try {
          child.kill("SIGTERM");
        } catch {
          /* already gone */
        }
        return target;
      }
      return target + text;
    };

    child.stdout?.on("data", (chunk) => {
      stdout = collect(stdout, chunk);
    });
    child.stderr?.on("data", (chunk) => {
      stderr = collect(stderr, chunk);
    });
    child.on("error", (error) => {
      finish({
        ok: false,
        code: "COUNCIL_SPAWN_FAILED",
        detail: String(error?.message ?? error),
        action: "Check councilAskPath and the Gateway process environment.",
      });
    });
    child.on("close", (code, signal) => {
      if (timedOut) {
        finish({
          ok: false,
          code: "COUNCIL_TIMEOUT",
          detail: `council-ask did not finish within ${config.timeoutMs} ms`,
          action: "Read `council-ask authority` on the box, then retry once the service is healthy.",
        });
        return;
      }
      if (tooLarge) {
        finish({
          ok: false,
          code: "COUNCIL_OUTPUT_TOO_LARGE",
          detail: `council-ask output exceeded ${MAX_CAPTURED_BYTES} bytes`,
          action: "Inspect the front door on the box; do not treat this as a verdict.",
        });
        return;
      }
      const refusal = parseRefusal(stderr) ?? parseRefusal(stdout);
      if (code !== 0) {
        finish({
          ok: false,
          code: refusal?.code ?? "COUNCIL_FRONTDOOR_FAILED",
          detail: refusal?.message ?? (stderr.trim() || stdout.trim() || `exit ${code}${signal ? ` (${signal})` : ""}`),
          action: refusal?.action ?? "Read the refusal above and retry once resolved.",
        });
        return;
      }
      let payload;
      try {
        payload = JSON.parse(stdout.trim());
      } catch {
        finish({
          ok: false,
          code: "COUNCIL_FRONTDOOR_BAD_OUTPUT",
          detail: "the front door did not return JSON",
          action: "Report the raw output; never invent a session id or verdict.",
        });
        return;
      }
      if (!payload || payload.ok !== true) {
        const detail =
          payload?.error?.message ?? payload?.detail?.summary ?? payload?.detail ?? "the front door refused";
        finish({
          ok: false,
          code: payload?.error?.code ?? payload?.code ?? "COUNCIL_FRONTDOOR_REFUSED",
          detail,
          action: payload?.error?.action ?? "Read the refusal and retry once resolved.",
        });
        return;
      }
      if (typeof payload.session_id !== "string" || payload.session_id.length === 0) {
        finish({
          ok: false,
          code: "COUNCIL_FRONTDOOR_BAD_OUTPUT",
          detail: "the front door returned success without a session id",
          action: "Report the raw output; never invent a session id.",
        });
        return;
      }
      finish({ ok: true, text: renderSuccess(payload), payload });
    });

    timer = setTimeout(() => {
      timedOut = true;
      try {
        child.kill("SIGTERM");
      } catch {
        /* already gone */
      }
    }, config.timeoutMs);
    hardTimer = setTimeout(() => {
      try {
        child.kill("SIGKILL");
      } catch {
        /* already gone */
      }
    }, config.timeoutMs + 5000);
  });
}

/**
 * The full handler. Returns undefined for every untrusted or unrelated
 * message, so normal dispatch is untouched. Returns a handled text only for
 * an authorized explicit ask, including its typed refusals.
 */
export async function handleInbound({ event, ctx, config, deps = {} }) {
  const classification = classifyInbound({ event, ctx, config });
  if (!classification.matched) {
    // A recognized explicit ask that cannot be used is still answered here, so
    // it can never fall through to a model that invents approval prose.
    if (classification.rejected) {
      return {
        handled: true,
        text: renderFailure(
          classification.rejected.code,
          classification.rejected.detail,
          classification.rejected.action,
        ),
      };
    }
    return undefined;
  }

  const nowMs = deps.now ? deps.now().getTime() : Date.now();
  const nowIso = new Date(nowMs).toISOString();
  // An out-of-range hook budget is refused here, before any state write or
  // spend. Refusing BEFORE the claim keeps the message retryable once the
  // operator fixes the config, and never truncates a running sitting.
  if (config.timeoutBlocked) {
    return {
      handled: true,
      text: renderFailure(
        config.timeoutBlocked.code,
        config.timeoutBlocked.detail,
        config.timeoutBlocked.action,
      ),
    };
  }
  const key = claimKey({ config, event });
  let claim;
  try {
    claim = claimMessage({ config, key, nowMs });
  } catch (error) {
    // Bounded refusal inside the handler: the ask is recognized and
    // authorized, so a state-dir fault must never become `undefined` (which
    // hands the message to a model that could invent a GO). No spawn happens.
    deps.logger?.error?.(`[council-before-dispatch] claim fault: ${String(error?.message ?? error)}`);
    return {
      handled: true,
      text: renderFailure(
        "COUNCIL_CLAIM_FAILED",
        String(error?.message ?? error),
        `Fix the plugin state directory (${config.stateDir}) permissions/ownership, then resend.`,
      ),
    };
  }
  if (!claim.ok) return { handled: true, text: claim.text };

  let text;
  let status = "error";
  try {
    const built = await buildBrief({
      question: classification.question,
      workspace: config.agentWorkspace,
      displayTimezone: config.displayTimezone,
      now: nowIso,
      runtimeRoot: config.runtimeRoot,
      councilAskPath: config.councilAskPath,
      loadRuntimeImpl: deps.loadRuntime,
      readFile: deps.readFile,
      prepareProposals: deps.prepareProposals,
      proposalInfer: deps.proposalInfer,
    });
    if (!built.ok) {
      if (built.state === BRIEF_STATE.PREPARING || built.state === BRIEF_STATE.INPUT_NEEDED) {
        // Distinct state: no sitting started, so the message must NOT be
        // reported as "Council did not convene" and must not carry a GO.
        text = renderPreparation(built);
        status = built.state;
      } else {
        text = renderFailure(
          built.code,
          built.detail,
          built.action ?? "Fix the brief input, then send a new explicit Council ask.",
        );
      }
    } else {
      const briefPath = writeBriefFile({ stateDir: config.stateDir, key, brief: built.brief });
      const run = await runFrontDoor({ config, briefPath, deps });
      if (run.ok) {
        text = run.text;
        status = "done";
      } else if (run.code === "COUNCIL_PREPARATION_REQUIRED") {
        // The service refused to score an exploratory question and could not
        // prepare alternatives (no configured adapter or no substantive
        // response). That is input-needed, never "did not convene" as if a
        // sitting had failed, and it carries no GO, score or approval.
        text = renderPreparation({
          state: "input-needed",
          detail: run.detail,
          action: run.action,
          preparation: { missing: [], request_budget: 0 },
        });
        status = "input-needed";
      } else {
        text = renderFailure(run.code, run.detail, run.action);
      }
    }
  } catch (error) {
    deps.logger?.error?.(`[council-before-dispatch] ${String(error?.message ?? error)}`);
    const code = error?.code === RUNTIME_UNRESOLVED_CODE ? RUNTIME_UNRESOLVED_CODE : "COUNCIL_PLUGIN_ERROR";
    text = renderFailure(
      code,
      String(error?.detail ?? error?.message ?? error),
      error?.action ?? "Read the Gateway log; no Council sitting was started.",
    );
  }

  finishClaim({ claim, text, status, nowMs });
  return { handled: true, text };
}
