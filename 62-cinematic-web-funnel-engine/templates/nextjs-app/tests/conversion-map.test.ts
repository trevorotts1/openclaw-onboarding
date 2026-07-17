import { describe, expect, it } from "vitest";
import { parseConversionAction, parseConversionMap, validateSubmission } from "@/components/conversion-map";

describe("parseConversionAction", () => {
  it("accepts a valid ghl-form-embed action", () => {
    const result = parseConversionAction({
      kind: "ghl-form-embed",
      label: "Get the guide",
      embedUrlEnvVar: "GHL_FORM_EMBED_URL_HERO",
      requiredFields: [],
    });
    expect("action" in result).toBe(true);
  });

  it("rejects ghl-form-embed missing embedUrlEnvVar", () => {
    const result = parseConversionAction({ kind: "ghl-form-embed", label: "x", requiredFields: [] });
    expect("error" in result).toBe(true);
    if ("error" in result) expect(result.error).toContain("embedUrlEnvVar");
  });

  it("accepts a valid ghl-webhook action", () => {
    const result = parseConversionAction({
      kind: "ghl-webhook",
      label: "Book a call",
      webhookEnvVar: "GHL_WEBHOOK_URL_BOOK_CALL",
      requiredFields: ["email"],
    });
    expect("action" in result).toBe(true);
  });

  it("rejects ghl-webhook missing webhookEnvVar", () => {
    const result = parseConversionAction({ kind: "ghl-webhook", label: "x", requiredFields: [] });
    expect("error" in result).toBe(true);
    if ("error" in result) expect(result.error).toContain("webhookEnvVar");
  });

  it("accepts a valid external-link action", () => {
    const result = parseConversionAction({ kind: "external-link", label: "FAQ", href: "/faq", requiredFields: [] });
    expect("action" in result).toBe(true);
  });

  it("rejects external-link missing href", () => {
    const result = parseConversionAction({ kind: "external-link", label: "FAQ", requiredFields: [] });
    expect("error" in result).toBe(true);
  });

  it("rejects an unknown kind", () => {
    const result = parseConversionAction({ kind: "carrier-pigeon", label: "x" });
    expect("error" in result).toBe(true);
  });

  it("rejects non-object entries", () => {
    expect("error" in parseConversionAction("nope")).toBe(true);
    expect("error" in parseConversionAction(null)).toBe(true);
    expect("error" in parseConversionAction(["a"])).toBe(true);
    expect("error" in parseConversionAction(42)).toBe(true);
  });

  it("rejects a missing label", () => {
    const result = parseConversionAction({ kind: "external-link", href: "/x" });
    expect("error" in result).toBe(true);
  });

  it("rejects a blank label", () => {
    const result = parseConversionAction({ kind: "external-link", label: "   ", href: "/x" });
    expect("error" in result).toBe(true);
  });

  it("rejects a non-array requiredFields", () => {
    const result = parseConversionAction({
      kind: "external-link",
      label: "x",
      href: "/x",
      requiredFields: "email",
    });
    expect("error" in result).toBe(true);
  });

  it("rejects a requiredFields array with a non-string entry", () => {
    const result = parseConversionAction({
      kind: "external-link",
      label: "x",
      href: "/x",
      requiredFields: ["email", 42],
    });
    expect("error" in result).toBe(true);
  });

  it("defaults requiredFields to [] when absent", () => {
    const result = parseConversionAction({ kind: "external-link", label: "x", href: "/x" });
    expect("action" in result && result.action.requiredFields).toEqual([]);
  });
});

describe("parseConversionMap", () => {
  it("splits valid and invalid entries, never mixing a bad entry into actions", () => {
    const raw = {
      "good-link": { kind: "external-link", label: "Learn more", href: "/learn", requiredFields: [] },
      "bad-webhook": { kind: "ghl-webhook", label: "Book" }, // missing webhookEnvVar
    };
    const { actions, errors } = parseConversionMap(raw);
    expect(Object.keys(actions)).toEqual(["good-link"]);
    expect(errors).toHaveLength(1);
    expect(errors[0].ctaId).toBe("bad-webhook");
    expect(errors[0].reason).toContain("webhookEnvVar");
  });

  it("returns empty results for an empty map", () => {
    const { actions, errors } = parseConversionMap({});
    expect(actions).toEqual({});
    expect(errors).toEqual([]);
  });

  it("never throws on a hostile/malformed raw map", () => {
    const raw = {
      a: null,
      b: undefined,
      c: "string",
      d: 42,
      e: ["array"],
      f: { kind: "ghl-form-embed" },
    } as unknown as Record<string, unknown>;
    const { actions, errors } = parseConversionMap(raw);
    expect(Object.keys(actions)).toEqual([]);
    expect(errors.length).toBeGreaterThan(0);
  });
});

describe("validateSubmission", () => {
  const action = {
    kind: "ghl-webhook" as const,
    label: "Book",
    webhookEnvVar: "X",
    requiredFields: ["email", "name"],
  };

  it("passes when every required field is present and non-empty", () => {
    expect(validateSubmission(action, { email: "a@b.com", name: "A" })).toEqual({ ok: true });
  });

  it("fails closed when a required field is missing entirely", () => {
    expect(validateSubmission(action, { email: "a@b.com" })).toEqual({ ok: false, missing: ["name"] });
  });

  it("fails closed when a required field is present but blank", () => {
    expect(validateSubmission(action, { email: "a@b.com", name: "   " })).toEqual({
      ok: false,
      missing: ["name"],
    });
  });

  it("fails closed when a required field is present but not a string", () => {
    expect(validateSubmission(action, { email: "a@b.com", name: 42 as unknown as string })).toEqual({
      ok: false,
      missing: ["name"],
    });
  });

  it("fails closed when the action itself is undefined", () => {
    expect(validateSubmission(undefined, { email: "a@b.com", name: "A" })).toEqual({
      ok: false,
      missing: ["<action>"],
    });
  });

  it("passes trivially when requiredFields is empty", () => {
    expect(validateSubmission({ ...action, requiredFields: [] }, {})).toEqual({ ok: true });
  });
});
