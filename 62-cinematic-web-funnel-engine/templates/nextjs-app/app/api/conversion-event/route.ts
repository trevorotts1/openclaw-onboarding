import { NextResponse } from "next/server";
import { SITE_DATA } from "@/lib/site-data.generated";
import { parseConversionMap, validateSubmission } from "@/components/conversion-map";
import { relayToGhlWebhook } from "@/lib/conversion-webhook";

/**
 * app/api/conversion-event/route.ts — the server side of the "ghl-webhook"
 * conversion kind (build unit U16, P12-CRM). Same-origin only: the client
 * wiring in `components/ConversionCtaWiring.tsx` posts here instead of
 * calling GHL directly, so no webhook URL and no GHL credential is ever
 * shipped to the browser.
 *
 * Fail-closed at every step (directive: "Fail-closed if the conversion
 * wiring is missing required fields"):
 *   1. malformed JSON / missing `ctaId` -> 400, no relay attempted;
 *   2. `ctaId` not present in the SERVER's own independent re-parse of
 *      `SITE_DATA.ctaMap` -> 400 (never trusts the client's parse);
 *   3. resolved action is not kind "ghl-webhook" -> 400 (form-embed and
 *      external-link actions have no server submission path);
 *   4. any of `action.requiredFields` missing/empty in the submitted
 *      `fields` -> 400, independently re-checked here even though the
 *      client already checked;
 *   5. the configured `webhookEnvVar` is unset, invalid, or non-https, or
 *      the relay itself fails/times out -> 502, never a silent 200.
 */

export const runtime = "nodejs";

interface ConversionEventBody {
  ctaId?: unknown;
  fields?: unknown;
}

function badRequest(error: string): Response {
  return NextResponse.json({ ok: false, error }, { status: 400 });
}

export async function POST(request: Request): Promise<Response> {
  let body: ConversionEventBody;
  try {
    body = (await request.json()) as ConversionEventBody;
  } catch {
    return badRequest("request body must be valid JSON");
  }

  if (typeof body.ctaId !== "string" || body.ctaId.trim().length === 0) {
    return badRequest('"ctaId" is required');
  }
  const ctaId = body.ctaId;

  const fields =
    typeof body.fields === "object" && body.fields !== null && !Array.isArray(body.fields)
      ? (body.fields as Record<string, unknown>)
      : {};

  const { actions } = parseConversionMap(SITE_DATA.ctaMap);
  const action = actions[ctaId];
  if (!action) {
    return badRequest(`"${ctaId}" is not a configured conversion action`);
  }
  if (action.kind !== "ghl-webhook") {
    return badRequest(`"${ctaId}" is kind "${action.kind}", which does not accept server-side submissions`);
  }
  if (!action.webhookEnvVar) {
    return badRequest(`"${ctaId}" has no webhookEnvVar configured`);
  }

  const validation = validateSubmission(action, fields);
  if (!validation.ok) {
    return badRequest(`missing required field(s): ${validation.missing.join(", ")}`);
  }

  const result = await relayToGhlWebhook(action.webhookEnvVar, {
    ctaId,
    label: action.label,
    fields,
    submittedAt: new Date().toISOString(),
  });

  if (!result.ok) {
    // Operator diagnostic only; never logs the resolved webhook URL value.
    console.error(
      `[cwfe-conversion] webhook relay failed for "${ctaId}": ${result.error ?? `status ${result.status}`}`,
    );
    return NextResponse.json({ ok: false, error: "delivery failed" }, { status: 502 });
  }

  return NextResponse.json({ ok: true });
}
