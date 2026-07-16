import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * conversion-event-route.test.ts — build unit U16 (P12-CRM). Exercises the
 * real `POST` handler from `app/api/conversion-event/route.ts` end to end,
 * with `@/lib/site-data.generated` (the P11 build's per-project output,
 * not present until `scripts/build_site.py` materializes a real project)
 * and `@/lib/conversion-webhook` (the actual outbound network call)
 * replaced by MOCKED fixtures via `vi.mock` — per directive: "Test against
 * MOCKED GHL fixtures — NO live GHL call." `relayMock` never performs a
 * real fetch; it is a synthetic in-process stand-in for a GHL response.
 *
 * `vi.hoisted` is required here (not just `vi.mock`'s own hoisting) because
 * the mock factories below reference `mockedCtaMap`/`relayMock`, and
 * `vi.mock` calls are hoisted above ordinary `const` declarations by
 * Vitest's transform — without `vi.hoisted` this would throw a
 * temporal-dead-zone error at import time.
 */

const { mockedCtaMap, relayMock } = vi.hoisted(() => {
  return {
    mockedCtaMap: {
      "book-a-call": {
        kind: "ghl-webhook",
        label: "Book a call",
        webhookEnvVar: "GHL_WEBHOOK_URL_BOOK_CALL",
        requiredFields: ["email"],
      },
      "download-guide": {
        kind: "ghl-form-embed",
        label: "Download the guide",
        embedUrlEnvVar: "GHL_FORM_EMBED_URL_GUIDE",
        requiredFields: [],
      },
    },
    relayMock: vi.fn(),
  };
});

vi.mock("@/lib/site-data.generated", () => ({
  SITE_DATA: {
    meta: { projectId: "p", title: "t", description: "d", architecture: "hybrid" },
    scenes: [],
    sections: [],
    ctaMap: mockedCtaMap,
    embed: { allowedAncestors: [] },
  },
}));

vi.mock("@/lib/conversion-webhook", () => ({
  relayToGhlWebhook: relayMock,
}));

const { POST } = await import("@/app/api/conversion-event/route");

function makeRequest(body: unknown): Request {
  return new Request("https://example.test/api/conversion-event", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

beforeEach(() => {
  relayMock.mockReset();
});

describe("POST /api/conversion-event", () => {
  it("400s on invalid JSON, never attempts a relay", async () => {
    const request = new Request("https://example.test/api/conversion-event", {
      method: "POST",
      body: "not json",
    });
    const response = await POST(request);
    expect(response.status).toBe(400);
    expect(relayMock).not.toHaveBeenCalled();
  });

  it("400s when ctaId is missing", async () => {
    const response = await POST(makeRequest({}));
    expect(response.status).toBe(400);
  });

  it("400s for an unconfigured ctaId — fails closed rather than guessing", async () => {
    const response = await POST(makeRequest({ ctaId: "does-not-exist" }));
    expect(response.status).toBe(400);
    expect(relayMock).not.toHaveBeenCalled();
  });

  it("400s for a ghl-form-embed ctaId — that kind has no server submission path", async () => {
    const response = await POST(makeRequest({ ctaId: "download-guide", fields: {} }));
    expect(response.status).toBe(400);
    expect(relayMock).not.toHaveBeenCalled();
  });

  it("400s when a required field is missing, independent of any client-side check", async () => {
    const response = await POST(makeRequest({ ctaId: "book-a-call", fields: {} }));
    expect(response.status).toBe(400);
    const body = (await response.json()) as { ok: boolean; error: string };
    expect(body.ok).toBe(false);
    expect(body.error).toContain("email");
    expect(relayMock).not.toHaveBeenCalled();
  });

  it("relays to the MOCKED webhook and returns 200 on success — no live GHL call", async () => {
    relayMock.mockResolvedValue({ ok: true, status: 200 });

    const response = await POST(makeRequest({ ctaId: "book-a-call", fields: { email: "a@b.com" } }));

    expect(response.status).toBe(200);
    const body = (await response.json()) as { ok: boolean };
    expect(body).toEqual({ ok: true });
    expect(relayMock).toHaveBeenCalledWith(
      "GHL_WEBHOOK_URL_BOOK_CALL",
      expect.objectContaining({ ctaId: "book-a-call", fields: { email: "a@b.com" } }),
    );
  });

  it("502s when the mocked relay reports failure", async () => {
    relayMock.mockResolvedValue({ ok: false, error: "env var not set" });

    const response = await POST(makeRequest({ ctaId: "book-a-call", fields: { email: "a@b.com" } }));

    expect(response.status).toBe(502);
    const body = (await response.json()) as { ok: boolean };
    expect(body.ok).toBe(false);
  });

  it("ignores an unexpected non-object fields payload rather than throwing", async () => {
    const response = await POST(makeRequest({ ctaId: "book-a-call", fields: "not-an-object" }));
    expect(response.status).toBe(400); // falls back to {} fields, which fails the required-field check
    expect(relayMock).not.toHaveBeenCalled();
  });
});
