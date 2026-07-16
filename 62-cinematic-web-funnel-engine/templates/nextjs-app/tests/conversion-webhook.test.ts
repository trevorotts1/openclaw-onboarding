import { afterEach, describe, expect, it, vi } from "vitest";
import { relayToGhlWebhook } from "@/lib/conversion-webhook";

/**
 * conversion-webhook.test.ts — build unit U16 (P12-CRM). Per directive:
 * "Test against MOCKED GHL fixtures — NO live GHL call." Every test below
 * either exercises a fail-closed path with no network call at all, or
 * stubs `global.fetch` with a synthetic, in-process mocked response —
 * nothing here ever reaches a real host.
 */

const ENV_VAR = "TEST_GHL_WEBHOOK_URL";
const ALLOWED_HOSTS_VAR = "GHL_WEBHOOK_ALLOWED_HOSTS";

afterEach(() => {
  delete process.env[ENV_VAR];
  delete process.env[ALLOWED_HOSTS_VAR];
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("relayToGhlWebhook", () => {
  it("fails closed when the env var is unset — never falls back to a default URL", async () => {
    const result = await relayToGhlWebhook(ENV_VAR, { a: 1 });
    expect(result).toEqual({ ok: false, error: `env var "${ENV_VAR}" is not set` });
  });

  it("fails closed when the env var is set but blank", async () => {
    process.env[ENV_VAR] = "   ";
    const result = await relayToGhlWebhook(ENV_VAR, { a: 1 });
    expect(result.ok).toBe(false);
  });

  it("fails closed when the env var is not a valid URL", async () => {
    process.env[ENV_VAR] = "not-a-url";
    const result = await relayToGhlWebhook(ENV_VAR, { a: 1 });
    expect(result.ok).toBe(false);
    expect(result.error).toContain("not a valid URL");
  });

  it("fails closed when the env var resolves to a non-https URL", async () => {
    process.env[ENV_VAR] = "http://example.com/webhook";
    const result = await relayToGhlWebhook(ENV_VAR, { a: 1 });
    expect(result.ok).toBe(false);
    expect(result.error).toContain("https://");
  });

  it("fails closed when the env var resolves to a host outside the outbound provider allowlist", async () => {
    // Default allowlist only covers GHL's own hosts — an https URL on any
    // other host (mis-set or tampered env var) must never be POSTed to.
    process.env[ENV_VAR] = "https://attacker.example.com/hooks/exfil";
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const result = await relayToGhlWebhook(ENV_VAR, { a: 1 });

    expect(result.ok).toBe(false);
    expect(result.error).toContain("allowlist");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("allows a subdomain of a default-allowlisted GHL host with no extra config", async () => {
    process.env[ENV_VAR] = "https://services.leadconnectorhq.com/hooks/inbound";
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await relayToGhlWebhook(ENV_VAR, { a: 1 });

    expect(result).toEqual({ ok: true, status: 200 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("relays to a MOCKED GHL fixture endpoint and reports success — no live GHL call", async () => {
    // The fixture host is not a real GHL domain, so it must be explicitly
    // added via the additive allowlist extension var — the same mechanism
    // an operator would use for a client-specific relay domain.
    process.env[ALLOWED_HOSTS_VAR] = "ghl.example.invalid";
    process.env[ENV_VAR] = "https://ghl.example.invalid/hooks/mocked-fixture";
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await relayToGhlWebhook(ENV_VAR, { ctaId: "book-a-call" });

    expect(result).toEqual({ ok: true, status: 200 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [calledUrl, calledInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(calledUrl).toBe("https://ghl.example.invalid/hooks/mocked-fixture");
    expect(calledInit.method).toBe("POST");
    expect(JSON.parse(calledInit.body as string)).toEqual({ ctaId: "book-a-call" });
  });

  it("reports failure (never throws) when the mocked endpoint responds non-2xx", async () => {
    process.env[ALLOWED_HOSTS_VAR] = "ghl.example.invalid";
    process.env[ENV_VAR] = "https://ghl.example.invalid/hooks/mocked-fixture";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 500 })));

    const result = await relayToGhlWebhook(ENV_VAR, { a: 1 });

    expect(result).toEqual({ ok: false, status: 500 });
  });

  it("reports a timeout as a failure, never throws or hangs", async () => {
    process.env[ALLOWED_HOSTS_VAR] = "ghl.example.invalid";
    process.env[ENV_VAR] = "https://ghl.example.invalid/hooks/mocked-fixture";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            const err = new Error("aborted");
            err.name = "AbortError";
            reject(err);
          });
        });
      }),
    );

    const result = await relayToGhlWebhook(ENV_VAR, { a: 1 }, { timeoutMs: 10 });

    expect(result).toEqual({ ok: false, error: "timeout" });
  });

  it("reports a network error as a failure, never throws", async () => {
    process.env[ALLOWED_HOSTS_VAR] = "ghl.example.invalid";
    process.env[ENV_VAR] = "https://ghl.example.invalid/hooks/mocked-fixture";
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")));

    const result = await relayToGhlWebhook(ENV_VAR, { a: 1 });

    expect(result).toEqual({ ok: false, error: "network error" });
  });
});
