// Environment hygiene for render children (Directive MG-029).
//
// Render children execute generated scene code, so they are treated as
// untrusted: they receive an ALLOWLISTED environment, never the host
// process environment with a few names deleted. Three independent rules
// apply, in order:
//   1. Only names on ENV_ALLOWLIST are inherited at all.
//   2. Any name that looks secret-shaped is refused even if a future
//      allowlist edit adds it (SECRET_NAME_PATTERN).
//   3. Code-injection and egress vectors are refused by name even though
//      they are not secrets: NODE_OPTIONS and LD_PRELOAD can execute
//      arbitrary code inside the child, and the *_PROXY variables hand
//      the child a ready-made network egress path. Render children make
//      no network calls by design (network.ts enforces that at the OS
//      level when a policy is requested); they do not need a proxy.
//
// The builder returns the NAMES it removed (never values) so evidence
// can prove what was withheld. redactSecrets handles the complementary
// direction: anything a child prints is scrubbed of the host's secret
// values and of secret-shaped strings before it is stored as a log.

import { randomUUID } from "node:crypto";

/** Names a render child may inherit from the host environment. Kept to
 * what the pinned engines and their browsers need to run locally: path
 * and locale plumbing, XDG locations, and the runtime's own MOTION_*
 * configuration surface. Provider credentials are never on this list. */
export const ENV_ALLOWLIST: ReadonlySet<string> = new Set([
  "PATH",
  "HOME",
  "TMPDIR",
  "TEMP",
  "TMP",
  "LANG",
  "LC_ALL",
  "LC_CTYPE",
  "TZ",
  "USER",
  "LOGNAME",
  "SHELL",
  "TERM",
  "COLORTERM",
  "NO_COLOR",
  "FORCE_COLOR",
  "NODE_ENV",
  "XDG_CACHE_HOME",
  "XDG_CONFIG_HOME",
  "XDG_DATA_HOME",
  "XDG_RUNTIME_DIR",
  "MOTION_RUNTIME_DIR",
  "MOTION_SHARED_RUNTIME_DIR",
  "MOTION_CAPABILITIES_PATH",
  "MOTION_CONTRACTS_SCHEMA",
  "MOTION_TYPOGRAPHY_TOKENS",
  "MOTION_FIXTURES_ROOT",
  "MOTION_PROCESS_REGISTRY_DIR",
  "MOTION_JOB_WORK_ROOT",
  "MOTION_RENDER_NETWORK",
]);

/** A variable name is secret-shaped when it names a credential: an API
 * key, token, password, or private key material. This catches the
 * provider names this pipeline uses (KIE_API_KEY, FISH_AUDIO_API_KEY,
 * GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY) without enumerating
 * vendors, and any future provider added the same way. */
export const SECRET_NAME_PATTERN =
  /(API_?KEY|ACCESS_?KEY|SECRET|TOKEN|PASSWORD|PASSWD|PASSPHRASE|PRIVATE_?KEY|CREDENTIAL|AUTH)/i;

export function isSecretName(name: string): boolean {
  return SECRET_NAME_PATTERN.test(name);
}

/** Names refused for render children even though they are not secrets:
 * dynamic-loader and Node option injection, plus proxy configuration
 * (an egress path a scene could use to reach the network in modes
 * where the OS namespace is not requested). */
export const FORBIDDEN_CHILD_ENV: ReadonlySet<string> = new Set([
  "NODE_OPTIONS",
  "LD_PRELOAD",
  "LD_LIBRARY_PATH",
  "DYLD_INSERT_LIBRARIES",
  "DYLD_LIBRARY_PATH",
  "HTTP_PROXY",
  "HTTPS_PROXY",
  "ALL_PROXY",
  "http_proxy",
  "https_proxy",
  "all_proxy",
  "NODE_USE_ENV_PROXY",
]);

export interface RenderEnvOptions {
  /** Job the child belongs to; recorded as MOTION_JOB_ID. */
  jobId?: string;
  /** Ownership token for this job; recorded as MOTION_JOB_TOKEN and
   * inherited by every descendant, which is what lets the process
   * registry and the sweep prove a process belongs to a job by reading
   * /proc/<pid>/environ. Generated when a jobId is given and no token
   * is supplied. */
  jobToken?: string;
  /** Job-specific scratch directory; becomes the child's TMPDIR. */
  tmpDir?: string;
  /** Job-specific home directory; becomes the child's HOME. */
  homeDir?: string;
  /** Caller-controlled additions applied AFTER scrubbing (engine
   * control flags such as HYPERFRAMES_SKIP_SKILLS). A secret-shaped or
   * forbidden name here is a programming error and throws. */
  extra?: Record<string, string>;
}

export interface RenderEnvResult {
  env: NodeJS.ProcessEnv;
  /** Every host variable name that was withheld, sorted. Names only:
   * values are never recorded anywhere in this layer. */
  removedNames: string[];
  /** The ownership token placed in the child environment, if any. */
  jobToken: string | null;
}

export function buildRenderEnv(
  base: NodeJS.ProcessEnv,
  opts?: RenderEnvOptions
): RenderEnvResult {
  const env: NodeJS.ProcessEnv = {};
  const removed: string[] = [];
  for (const [name, value] of Object.entries(base)) {
    if (value === undefined) continue;
    if (FORBIDDEN_CHILD_ENV.has(name) || isSecretName(name) || !ENV_ALLOWLIST.has(name)) {
      removed.push(name);
      continue;
    }
    env[name] = value;
  }
  if (opts?.extra) {
    for (const [name, value] of Object.entries(opts.extra)) {
      if (FORBIDDEN_CHILD_ENV.has(name) || isSecretName(name)) {
        throw new Error(
          `buildRenderEnv: extra variable ${name} is forbidden in a render child environment`
        );
      }
      env[name] = value;
    }
  }
  let jobToken: string | null = null;
  if (opts?.jobId) {
    jobToken = opts.jobToken ?? randomUUID();
    env.MOTION_JOB_ID = opts.jobId;
    env.MOTION_JOB_TOKEN = jobToken;
  }
  if (opts?.tmpDir) env.TMPDIR = opts.tmpDir;
  if (opts?.homeDir) env.HOME = opts.homeDir;
  removed.sort();
  return { env, removedNames: removed, jobToken };
}

/** Values of the secret-shaped variables present in an environment.
 * Used ONLY as redaction input by the process that owns the secrets:
 * the values are matched against captured child output and replaced,
 * never written to any log, registry, or evidence file. Very short
 * values are skipped: redacting a 1-3 character string would mangle
 * ordinary output while protecting nothing. */
export function secretValuesOf(env: NodeJS.ProcessEnv): string[] {
  const values: string[] = [];
  for (const [name, value] of Object.entries(env)) {
    if (value && value.length >= 6 && isSecretName(name)) values.push(value);
  }
  return values;
}

const LABELED_SECRET_PATTERN =
  /((?:api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|password|passwd|secret)\s*["']?\s*[:=]\s*["']?)[^\s"',}\]]+/gi;
const BEARER_PATTERN = /(Authorization\s*:\s*Bearer\s+)[^\s"']+|(\bBearer\s+)[A-Za-z0-9._~+/=-]{8,}/gi;
const PROVIDER_KEY_SHAPES: RegExp[] = [
  /\bsk-[A-Za-z0-9_-]{10,}\b/g,
  /\bAIza[0-9A-Za-z_-]{12,}\b/g,
  /\bgh[pousr]_[A-Za-z0-9]{16,}\b/g,
  /\bxox[baprs]-[A-Za-z0-9-]{10,}\b/g,
  /\bAKIA[0-9A-Z]{16}\b/g,
];

/**
 * Scrub captured child output before it is stored as a log or evidence:
 * exact host secret values first, then labeled assignments, bearer
 * tokens, and well-known provider key shapes. Benign content is left
 * byte-identical: a bare sha256 hex digest, for example, matches none
 * of these patterns and survives, because redaction that mangles
 * ordinary logs would hide real diagnostics.
 */
export function redactSecrets(
  text: string,
  secretValues?: string[],
  opts?: { valuesOnly?: boolean }
): string {
  let out = text;
  for (const value of secretValues ?? []) {
    if (value.length >= 6) out = out.split(value).join("[redacted]");
  }
  // Pattern redaction rewrites labeled values it cannot prove are
  // secrets; on machine-readable output (JSON reports) that could
  // corrupt structure, so callers handling structured text pass
  // valuesOnly and still get exact-value protection.
  if (opts?.valuesOnly) return out;
  out = out.replace(LABELED_SECRET_PATTERN, "$1[redacted]");
  out = out.replace(BEARER_PATTERN, (_m, g1: string | undefined, g2: string | undefined) =>
    g1 ? `${g1}[redacted]` : `${g2 ?? "Bearer "}[redacted]`
  );
  for (const pattern of PROVIDER_KEY_SHAPES) out = out.replace(pattern, "[redacted]");
  return out;
}

/** Names of the secret shapes present in a text, for tests and audits:
 * returns "host-secret-value" when an exact host value appears, plus
 * one entry per pattern family that matched. Empty means clean. The
 * redaction placeholder is neutralized first (replaced with an empty
 * quoted string, which no value pattern accepts): a "[redacted]"
 * standing where a value was is the cure, not a leak, and without
 * this a labeled line followed by ordinary prose would score as a
 * labeled secret with the next line's first word as its "value". */
export function findSecretShapes(rawText: string, secretValues?: string[]): string[] {
  const text = rawText.split("[redacted]").join('""');
  const found: string[] = [];
  for (const value of secretValues ?? []) {
    if (value.length >= 6 && text.includes(value)) found.push("host-secret-value");
  }
  if (LABELED_SECRET_PATTERN.test(text)) found.push("labeled-secret");
  LABELED_SECRET_PATTERN.lastIndex = 0;
  if (BEARER_PATTERN.test(text)) found.push("bearer-token");
  BEARER_PATTERN.lastIndex = 0;
  for (const pattern of PROVIDER_KEY_SHAPES) {
    if (pattern.test(text)) found.push("provider-key-shape");
    pattern.lastIndex = 0;
  }
  return [...new Set(found)];
}
