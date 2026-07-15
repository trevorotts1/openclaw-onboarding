import { afterEach, describe, expect, it, vi } from "vitest";
import { resolveGhlFormEmbeds } from "@/lib/resolve-ghl-embeds";

/**
 * resolve-ghl-embeds.test.ts — build unit U16 QC fix (P12-CRM). Covers the
 * server-only resolution path that used to live inside `GhlFormEmbed.tsx`
 * (a component that turned out to render client-side despite having no
 * `"use client"` of its own, per RSC ownership rules — see
 * `lib/resolve-ghl-embeds.ts` for the full explanation). This is the path
 * that was previously never exercised: the U15 integration fixture's
 * `cta_map` entries have no `kind`, so no existing suite drove a real
 * `"ghl-form-embed"` action through resolution before this fix.
 *
 * Per directive: "Test against MOCKED GHL fixtures — NO live GHL call."
 * `resolveGhlFormEmbeds` never performs network I/O — it only reads
 * `process.env` and validates URL shape — so every assertion below is a
 * pure in-process check.
 */

const ENV_VAR = "TEST_GHL_FORM_EMBED_URL";

afterEach(() => {
  delete process.env[ENV_VAR];
  vi.restoreAllMocks();
});

describe("resolveGhlFormEmbeds", () => {
  it("resolves a valid ghl-form-embed entry to its env-var URL", () => {
    process.env[ENV_VAR] = "https://ghl.example.invalid/widget/mocked-fixture";

    const resolved = resolveGhlFormEmbeds({
      "hero-cta": {
        kind: "ghl-form-embed",
        label: "Get the guide",
        embedUrlEnvVar: ENV_VAR,
        requiredFields: [],
      },
    });

    expect(resolved["hero-cta"]).toEqual({
      ok: true,
      label: "Get the guide",
      url: "https://ghl.example.invalid/widget/mocked-fixture",
    });
  });

  it("fails closed (never returns a guessed/fallback URL) when the env var is unset", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const resolved = resolveGhlFormEmbeds({
      "hero-cta": {
        kind: "ghl-form-embed",
        label: "Get the guide",
        embedUrlEnvVar: ENV_VAR,
        requiredFields: [],
      },
    });

    expect(resolved["hero-cta"]).toEqual({ ok: false, label: "Get the guide" });
    // Logs the env VAR NAME only — never a value (spec Section 20).
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining(ENV_VAR));
    expect(errorSpy).toHaveBeenCalledWith(expect.not.stringContaining("undefined://"));
  });

  it("fails closed when the env var is set but blank", () => {
    process.env[ENV_VAR] = "   ";

    const resolved = resolveGhlFormEmbeds({
      "hero-cta": {
        kind: "ghl-form-embed",
        label: "Get the guide",
        embedUrlEnvVar: ENV_VAR,
        requiredFields: [],
      },
    });

    expect(resolved["hero-cta"]).toEqual({ ok: false, label: "Get the guide" });
  });

  it("fails closed when the env var resolves to a malformed URL", () => {
    process.env[ENV_VAR] = "not-a-url";

    const resolved = resolveGhlFormEmbeds({
      "hero-cta": {
        kind: "ghl-form-embed",
        label: "Get the guide",
        embedUrlEnvVar: ENV_VAR,
        requiredFields: [],
      },
    });

    expect(resolved["hero-cta"]).toEqual({ ok: false, label: "Get the guide" });
  });

  it("never logs the resolved (secret-shaped) URL value on any path", () => {
    process.env[ENV_VAR] = "https://ghl.example.invalid/widget/mocked-fixture?token=super-secret";
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    resolveGhlFormEmbeds({
      "hero-cta": {
        kind: "ghl-form-embed",
        label: "Get the guide",
        embedUrlEnvVar: ENV_VAR,
        requiredFields: [],
      },
    });

    for (const call of errorSpy.mock.calls) {
      expect(String(call[0])).not.toContain("super-secret");
    }
  });

  it("ignores non-ghl-form-embed and malformed ctaMap entries entirely", () => {
    const resolved = resolveGhlFormEmbeds({
      "book-a-call": {
        kind: "ghl-webhook",
        label: "Book a call",
        webhookEnvVar: "SOME_WEBHOOK_VAR",
        requiredFields: [],
      },
      faq: { kind: "external-link", label: "FAQ", href: "/faq", requiredFields: [] },
      broken: { kind: "not-a-real-kind" },
    });

    expect(resolved).toEqual({});
  });

  it("resolves multiple ghl-form-embed entries independently — one failure doesn't affect another", () => {
    const OK_VAR = "TEST_GHL_FORM_EMBED_URL_OK";
    process.env[OK_VAR] = "https://ghl.example.invalid/widget/second-fixture";
    vi.spyOn(console, "error").mockImplementation(() => {});

    const resolved = resolveGhlFormEmbeds({
      broken: {
        kind: "ghl-form-embed",
        label: "Broken widget",
        embedUrlEnvVar: ENV_VAR, // intentionally unset
        requiredFields: [],
      },
      working: {
        kind: "ghl-form-embed",
        label: "Working widget",
        embedUrlEnvVar: OK_VAR,
        requiredFields: [],
      },
    });

    expect(resolved.broken).toEqual({ ok: false, label: "Broken widget" });
    expect(resolved.working).toEqual({
      ok: true,
      label: "Working widget",
      url: "https://ghl.example.invalid/widget/second-fixture",
    });

    delete process.env[OK_VAR];
  });
});
