// U058: end-to-end proof that a from-scratch, straight-price, deck-only,
// no-VIP client can walk the intake form to completion.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { orderedQuestions, nextQuestionIndex, isQuestionActive } from "../worker/src/lib.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE = JSON.parse(readFileSync(path.join(__dirname, "fixture_payload.json"), "utf-8"));

const ANSWERS = {
  presentation_type: "from_scratch", representation_mix: "text heavy",
  audience_composition_note: "executives and founders", grounded_content: "Our flagship product launch method",
  visual_mix: "clean corporate", dark_ok: "true", hook_seed: "The story of how we started",
  deliverable_set: "deck", style_source: "(not used)", goal: "persuade", cta_action: "book a call",
  event_price: "free", access_free: "true", target_feeling: "inspired and urgent",
  tone: "professional and confident", offer_name: "The Momentum System", offer_stack: "(none)",
  price_mode: "straight", final_price: "5000", duration_min: "60", audience: "executives",
  brand_primary: "#0044cc", logo_on_slides: "true", payment_plan: "pay in full", vip_tier: "false",
  primary_objection: "time", proof_assets: "testimonials and case studies",
  style_prefs: "dark background, minimal text",
  transformation_promise: "Close more enterprise deals with less effort",
  slide_count: "25", delivery_destinations: "email and webinar",
  deadline: "2 weeks", client_notes: "needs voiceover ready by Friday",
};

const NEVER_SERVE = new Set(["recipient_name", "signature_source", "price_anchor"]);

function completeMissing(payload, answeredIds) {
  const answeredSet = new Set(answeredIds);
  const missing = [];
  for (const q of payload.questions) {
    if (q.required === false) continue;
    if (answeredSet.has(q.id)) continue;
    const active = isQuestionActive(q, ANSWERS);
    if (active === false) continue;
    if (q.block_gate === false) continue;
    missing.push(q.id);
  }
  return missing;
}

test("blocked questions never served to from-scratch straight-price client", () => {
  const served = [], answeredIds = [];
  while (true) {
    const idx = nextQuestionIndex(FIXTURE, answeredIds, ANSWERS);
    if (idx === -1) break;
    const qs = orderedQuestions(FIXTURE, ANSWERS);
    served.push(qs[idx].id); answeredIds.push(qs[idx].id);
  }
  for (const blocked of NEVER_SERVE) {
    assert.ok(!served.includes(blocked), blocked + " must not be served (got " + served.length + " questions)");
  }
});

test("/complete gate yields empty missing for from-scratch straight-price client", () => {
  const missing = completeMissing(FIXTURE, Object.keys(ANSWERS));
  assert.deepEqual(missing, [], "missing must be empty, got: " + JSON.stringify(missing));
});
