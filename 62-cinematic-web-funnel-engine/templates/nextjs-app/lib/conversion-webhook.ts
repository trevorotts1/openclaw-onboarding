/**
 * conversion-webhook.ts — server-only relay from a validated conversion
 * submission to the client's own GHL inbound webhook (Convert and Flow
 * workflow trigger, Skill 44 — build unit U16, P12-CRM). This module is
 * never imported from a "use client" component; it exists so
 * `app/api/conversion-event/route.ts` stays a thin request/response
 * adapter around logic that can be unit-tested directly.
 *
 * Resolves the target URL by ENV VAR NAME only, at call time, and NEVER
 * logs the resolved value — only the env var's NAME and the resulting HTTP
 * status/error are ever recorded (spec Section 20: "record secret presence
 * by name only in receipts"; "never log secret values"; "allowlist outbound
 * provider hosts").
 */

export interface RelayResult {
  ok: boolean;
  status?: number;
  error?: string;
}

const RELAY_TIMEOUT_MS = 8000;

/**
 * Default allowlisted outbound webhook host suffixes (spec Section 20:
 * "allowlist outbound provider hosts"). A resolved webhook URL's hostname
 * must equal one of these, or be a subdomain of one of these, or this
 * module refuses to relay.
 */
const DEFAULT_ALLOWED_HOST_SUFFIXES = ["leadconnectorhq.com", "gohighlevel.com"];

/**
 * Additive-only extension point for the default allowlist: a
 * comma-separated list of extra host suffixes, read from
 * `GHL_WEBHOOK_ALLOWED_HOSTS`. This exists so an operator can allow a
 * client-specific relay domain or a mocked test-fixture host WITHOUT
 * weakening the built-in GHL allowlist above — it never replaces it.
 */
function isAllowedHost(hostname: string): boolean {
  const extra = (process.env.GHL_WEBHOOK_ALLOWED_HOSTS ?? "")
    .split(",")
    .map((entry) => entry.trim().toLowerCase())
    .filter((entry) => entry.length > 0);
  const suffixes = [...DEFAULT_ALLOWED_HOST_SUFFIXES, ...extra];
  const host = hostname.toLowerCase();
  return suffixes.some((suffix) => host === suffix || host.endsWith(`.${suffix}`));
}

export async function relayToGhlWebhook(
  webhookEnvVar: string,
  payload: Record<string, unknown>,
  options?: { timeoutMs?: number },
): Promise<RelayResult> {
  const webhookUrl = process.env[webhookEnvVar];
  if (!webhookUrl || webhookUrl.trim().length === 0) {
    return { ok: false, error: `env var "${webhookEnvVar}" is not set` };
  }

  let parsed: URL;
  try {
    parsed = new URL(webhookUrl);
  } catch {
    return { ok: false, error: `env var "${webhookEnvVar}" is not a valid URL` };
  }
  if (parsed.protocol !== "https:") {
    return { ok: false, error: `env var "${webhookEnvVar}" must resolve to an https:// URL` };
  }
  if (!isAllowedHost(parsed.hostname)) {
    return {
      ok: false,
      error: `env var "${webhookEnvVar}" resolves to a host not in the outbound provider allowlist`,
    };
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options?.timeoutMs ?? RELAY_TIMEOUT_MS);
  try {
    const response = await fetch(parsed.toString(), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    return { ok: response.ok, status: response.status };
  } catch (error) {
    const isAbort = error instanceof Error && error.name === "AbortError";
    return { ok: false, error: isAbort ? "timeout" : "network error" };
  } finally {
    clearTimeout(timeout);
  }
}
