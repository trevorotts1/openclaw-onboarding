// =============================================================================
// PRES-006 — THE ONE CANONICAL INTAKE FIELD-PATH CONTRACT.
// =============================================================================
//
// SINGLE SOURCE OF TRUTH for where every Presentation-intake answer lives in
// the dept-format intake record, what "required" means for it, and how legacy
// (pre-contract) records migrate forward. Everything downstream derives from
// THIS file and nothing else:
//
//   * the hosted UI question sets (pages/index.html, deployed-r2/public/
//     index.html QUESTIONS arrays + pages/questions.json) are GENERATED from
//     it by tools/gen_ui_questions.mjs — the UI never restates a field path;
//   * both Worker copies (worker/src/index.js, deployed-r2/src/index.js)
//     import schema/intake_contract.js — which reads THIS file — for their
//     completeness gate. The independent REQUIRED_BRIEF_FIELDS arrays that
//     used to be duplicated (and to drift) in each worker are GONE;
//   * box-side intake_writer.py mirrors the migration rules and the test
//     suite pins that mirror to this file (schema/intake_fields.json is the
//     generated JSON projection the Python tests read);
//   * the engine's upsell consumers (presentation_job/defers.py,
//     resolve_intake.py, sales_checkout_builder.py, vsl_builder.py) already
//     read the canonical paths below — tests pin them to this contract.
//
// CANONICAL STORAGE, chosen by engine-consumer need (not form convenience):
// the upsell flags WANT_SALES_CHECKOUT / WANT_VSL_PAGE (and their verbatim
// declined-reason waivers) live under pre_presentation_capture.* — the
// documented storeTarget home upsell-questions.json declares and every engine
// consumer reads. The 2026-09 defect: the hosted form stored them there but
// both Workers' hand-copied REQUIRED_BRIEF_FIELDS arrays required them inside
// deck_brief, so every complete form payload was rejected 422 by its own
// backend. Version 2 makes the canonical location explicit and migrates
// legacy records (see intake_contract.js migrateIntake).
//
// Version history:
//   1 — pre-contract records: no schema_version key; upsell flags found in
//       inconsistent locations (deck_brief.*, flat top-level, or the canonical
//       pre_presentation_capture.*). Migrated forward, contradictions refused.
//   2 — this contract: canonical paths below, schema_version stamped on every
//       record the writer produces.

export const INTAKE_CONTRACT = {
  contract: "presentation-intake-field-paths",
  version: 2,
  description:
    "One canonical field-path schema for the Presentation Interview intake: " +
    "form (generated UI questions), Workers (schema-driven completeness gate " +
    "+ version-aware migration), intake_writer, resolver, page/VSL stage and " +
    "tests all derive from this object.",

  // --- sections of the dept-format intake record ---------------------------
  sections: {
    deck_brief: "deck_brief",
    pre_presentation_capture: "pre_presentation_capture",
    intake_root: "intake.json",
  },

  // --- the fields -----------------------------------------------------------
  // `question` blocks are the UI projection (consumed by gen_ui_questions.mjs
  // verbatim). `canonical_path` is the storage location engine consumers read.
  fields: [
    {
      id: "presentation_type",
      canonical_path: "pre_presentation_capture.PRESENTATION_TYPE",
      section: "pre_presentation_capture",
      kind: "enum",
      required: true,
      block_gate: true,
      // Legacy records (and assemble_intake()'s pre-contract field_for()
      // fallback) filed the answer under deck_brief.PRESENTATION_TYPE or a
      // flat top-level PRESENTATION_TYPE key; the engine also accepts the
      // intake.json root `presentation_type`. All three migrate forward.
      legacy_aliases: ["deck_brief.PRESENTATION_TYPE", "PRESENTATION_TYPE"],
      allowed_values: ["from_scratch", "content_personal", "content_general", "signature"],
      question: {
        id: "presentation_type",
        order: 0,
        kind: "enum",
        prompt: "What <span class=\"emph\">kind of presentation</span> do you need?",
        help: "This is the first thing we need to know — it decides how we build everything else in your brief, from structure to length.",
        label: "Presentation type",
        required: true,
        storeOn: "pre_presentation_capture.PRESENTATION_TYPE",
        allowed_values: ["from_scratch", "content_personal", "content_general", "signature"],
        value_labels: {
          "from_scratch": "From scratch — brainstorm and build a brand-new presentation",
          "content_personal": "From something I already have, for ONE specific person",
          "content_general": "From something I already have, for a room or wider audience",
          "signature": "The full Signature Presentation (100+ slides, multi-part keynote)"
        }
      }
    },
    {
      id: "offer_name",
      canonical_path: "deck_brief.OFFER_NAME",
      section: "deck_brief",
      kind: "text",
      required: true,
      block_gate: true,
      question: {
        id: "offer_name",
        order: 1,
        kind: "text",
        prompt: "What are you selling at the end — the exact name of your product or offer?",
        help: "The offer sold at the end of the presentation — never invented.",
        label: "Offer name",
        placeholder: "e.g. The Momentum Method",
        required: true,
        storeOn: "deck_brief.OFFER_NAME"
      }
    },
    {
      id: "named_methodology",
      canonical_path: "deck_brief.NAMED_METHODOLOGY",
      section: "deck_brief",
      kind: "text",
      required: true,
      block_gate: true,
      question: {
        id: "named_methodology",
        order: 1.5,
        kind: "text",
        prompt: "Do you have a named methodology, framework, or system you deliver this through — what is it called, in your own words?",
        help: "The branded method name — client-supplied only, never invented for you. If you don&rsquo;t have a named method, say so plainly (e.g. &lsquo;no formal name, we just do X&rsquo;) rather than inventing one — an honest &lsquo;no&rsquo; is still a real answer.",
        label: "Named methodology",
        placeholder: "e.g. The Three-Move Pipeline System, or 'no formal name'",
        required: true,
        storeOn: "deck_brief.NAMED_METHODOLOGY"
      }
    },
    {
      id: "transformation_promise",
      canonical_path: "deck_brief.TRANSFORMATION_PROMISE",
      section: "deck_brief",
      kind: "text",
      required: true,
      block_gate: true,
      question: {
        id: "transformation_promise",
        order: 2,
        kind: "text",
        prompt: "What&rsquo;s the before-and-after this offer delivers — who are they before, and who are they after?",
        help: "The transformation promise drives the whole arc.",
        label: "Transformation promise",
        placeholder: "e.g. stuck and overwhelmed → clear, confident, closing",
        required: true,
        storeOn: "deck_brief.TRANSFORMATION_PROMISE"
      }
    },
    {
      id: "time_to_result",
      canonical_path: "deck_brief.TIME_TO_RESULT",
      section: "deck_brief",
      kind: "text",
      required: true,
      block_gate: true,
      question: {
        id: "time_to_result",
        order: 2.5,
        kind: "text",
        prompt: "How long does it typically take a client to see this result once they start — the real, honest timeframe?",
        help: "State the true delivery timeframe in your own words (e.g. &lsquo;8 weeks&rsquo;, &lsquo;about 3 sessions&rsquo;, or &lsquo;it varies, typically N weeks&rsquo;) — never a faster number to sound more impressive.",
        label: "Time to result",
        placeholder: "e.g. 8 weeks to final, a shift in 2",
        required: true,
        storeOn: "deck_brief.TIME_TO_RESULT"
      }
    },
    {
      id: "audience",
      canonical_path: "deck_brief.AUDIENCE",
      section: "deck_brief",
      kind: "text",
      required: true,
      block_gate: true,
      question: {
        id: "audience",
        order: 3,
        kind: "text",
        prompt: "Who is this presentation for?",
        help: "Industry, income level, and the pain point that brought them here. This seeds the audience-engine.",
        label: "Audience",
        placeholder: "e.g. women entrepreneurs, 35-55, tired of inconsistent clients",
        required: true,
        storeOn: "deck_brief.AUDIENCE"
      }
    },
    {
      id: "cta_action",
      canonical_path: "deck_brief.CTA_ACTION",
      section: "deck_brief",
      kind: "text",
      required: true,
      block_gate: true,
      question: {
        id: "cta_action",
        order: 4,
        kind: "text",
        prompt: "What is the exact call-to-action — the verb and next step you want them to take?",
        help: "This drives the closing slide&rsquo;s action language.",
        label: "Call to action",
        placeholder: "e.g. book a call, buy the program, join the waitlist",
        required: true,
        storeOn: "deck_brief.CTA_ACTION"
      }
    },
    {
      id: "brand_primary",
      canonical_path: "deck_brief.BRAND_PRIMARY",
      section: "deck_brief",
      kind: "logo",
      required: false,
      block_gate: false,
      extra_paths: { logo_on_slides: "deck_brief.LOGO_ON_SLIDES" },
      question: {
        id: "brand_primary",
        order: 5,
        kind: "logo",
        prompt: "Do you have a <span class=\"emph\">logo</span> or brand colors for the slides?",
        help: "If no logo is on file, provide one here — or we build without one and stay on-brand to the presentation system.",
        label: "Logo",
        required: false,
        storeOn: "deck_brief.BRAND_PRIMARY",
        logo_on_slides: "deck_brief.LOGO_ON_SLIDES"
      }
    },
    {
      id: "image_links",
      canonical_path: "deck_brief.IMAGE_LINKS",
      section: "deck_brief",
      kind: "image_links",
      required: false,
      block_gate: false,
      question: {
        id: "image_links",
        order: 6,
        kind: "image_links",
        prompt: "Paste any <span class=\"emph\">image links</span> you want used in the deck.",
        help: "Product photos, headshots, brand imagery. Optional — add up to 5.",
        label: "Image links",
        required: false,
        storeOn: "deck_brief.IMAGE_LINKS"
      }
    },
    {
      id: "tone",
      canonical_path: "deck_brief.TONE",
      section: "deck_brief",
      kind: "text",
      required: true,
      block_gate: true,
      question: {
        id: "tone",
        order: 7,
        kind: "text",
        prompt: "Pick a <span class=\"emph\">tone</span> — Inspirational, Tough Love, Challenger, Teacher, Storyteller, High-Energy Hype, or Calm Premium.",
        help: "One of the seven named styles, or blend two.",
        label: "Tone",
        placeholder: "e.g. Inspirational + Teacher",
        required: true,
        storeOn: "deck_brief.TONE"
      }
    },
    {
      id: "final_price",
      canonical_path: "deck_brief.FINAL_PRICE",
      section: "deck_brief",
      kind: "text",
      required: true,
      block_gate: true,
      question: {
        id: "final_price",
        order: 8,
        kind: "text",
        prompt: "What is the <span class=\"emph\">final price</span> of the offer?",
        help: "The offer price only — what a buyer pays at the end. Set 0 if this is a free-only close.",
        label: "Final price",
        placeholder: "e.g. $497",
        required: true,
        storeOn: "deck_brief.FINAL_PRICE"
      }
    },
    {
      id: "speech_speed_preference",
      canonical_path: "intake.json.speech_speed_preference",
      section: "intake_root",
      kind: "enum",
      required: true,
      block_gate: false,
      allowed_values: ["default", "medium", "fast"],
      question: {
        id: "speech_speed_preference",
        order: 9,
        kind: "enum",
        prompt: "At what <span class=\"emph\">pace</span> should we record the audio narration?",
        help: "default = recommended setting, medium = slightly faster, fast = high energy.",
        label: "Speech speed",
        required: true,
        storeOn: "intake.json",
        key: "speech_speed_preference",
        allowed_values: ["default", "medium", "fast"],
        value_labels: { "default": "Default pace (recommended)", "medium": "Medium pace", "fast": "Fast pace" }
      }
    },
    {
      id: "want_sales_checkout",
      canonical_path: "pre_presentation_capture.WANT_SALES_CHECKOUT",
      section: "pre_presentation_capture",
      kind: "enum",
      required: true,
      block_gate: true,
      allowed_values: ["yes", "no"],
      legacy_aliases: ["deck_brief.WANT_SALES_CHECKOUT", "WANT_SALES_CHECKOUT"],
      question: {
        id: "want_sales_checkout",
        order: 10,
        kind: "enum",
        prompt: "Do you need a <span class=\"emph\">sales page and checkout page</span> along with the presentation?",
        help: "Default yes. A no records a client waiver — you keep the deck and optionally a VSL page.",
        label: "Sales page + checkout",
        required: true,
        storeOn: "pre_presentation_capture.WANT_SALES_CHECKOUT",
        allowed_values: ["yes", "no"],
        value_labels: { "yes": "Yes, build the sales page and checkout page", "no": "No thank you" }
      }
    },
    {
      id: "sales_checkout_declined_reason",
      canonical_path: "pre_presentation_capture.SALES_CHECKOUT_DECLINED_REASON",
      section: "pre_presentation_capture",
      kind: "text",
      required: true,
      block_gate: true,
      conditional_on: { id: "want_sales_checkout", equals: "no" },
      question: {
        id: "sales_checkout_declined_reason",
        order: 10.1,
        kind: "text",
        prompt: "Understood — no sales page or checkout page. In your own words, why don&rsquo;t you want it? (I record this verbatim so nobody later has to guess.)",
        help: "Asked only when you declined the sales + checkout pages. Stored word-for-word as your waiver — an empty answer cannot be accepted.",
        label: "Why no sales/checkout page",
        placeholder: "e.g. we only need the deck for this launch",
        required: true,
        storeOn: "pre_presentation_capture.SALES_CHECKOUT_DECLINED_REASON",
        conditional_on: { id: "want_sales_checkout", equals: "no" }
      }
    },
    {
      id: "want_vsl_page",
      canonical_path: "pre_presentation_capture.WANT_VSL_PAGE",
      section: "pre_presentation_capture",
      kind: "enum",
      required: true,
      block_gate: true,
      allowed_values: ["yes", "no"],
      legacy_aliases: ["deck_brief.WANT_VSL_PAGE", "WANT_VSL_PAGE"],
      question: {
        id: "want_vsl_page",
        order: 11,
        kind: "enum",
        prompt: "Would you like a <span class=\"emph\">VSL page</span> — a video sales letter — along with this?",
        help: "Default no — a VSL page needs the video to exist first.",
        label: "VSL page",
        required: true,
        storeOn: "pre_presentation_capture.WANT_VSL_PAGE",
        allowed_values: ["yes", "no"],
        value_labels: { "yes": "Yes, build the VSL page", "no": "No thank you" }
      }
    },
    {
      id: "vsl_page_declined_reason",
      canonical_path: "pre_presentation_capture.VSL_PAGE_DECLINED_REASON",
      section: "pre_presentation_capture",
      kind: "text",
      required: true,
      block_gate: true,
      conditional_on: { id: "want_vsl_page", equals: "no" },
      question: {
        id: "vsl_page_declined_reason",
        order: 11.1,
        kind: "text",
        prompt: "No VSL page, understood. In your own words, why not? (Recorded verbatim as your waiver.)",
        help: "Asked only when you declined the VSL page. Stored word-for-word — an empty answer cannot be accepted.",
        label: "Why no VSL page",
        placeholder: "e.g. we have no hosted video yet",
        required: true,
        storeOn: "pre_presentation_capture.VSL_PAGE_DECLINED_REASON",
        conditional_on: { id: "want_vsl_page", equals: "no" }
      }
    },
    {
      id: "run_mode",
      canonical_path: "pre_presentation_capture.RUN_MODE",
      section: "pre_presentation_capture",
      kind: "enum",
      required: false,
      block_gate: false,
      allowed_values: ["ultra", "standard", "economy"],
      legacy_aliases: ["deck_brief.RUN_MODE", "RUN_MODE", "run_mode"],
      question: {
        // FIX 11 — the client's RUN MODE. kind "enum" is load-bearing — it
        // renders a pick-one group, so the interview-depth words (quick /
        // in-depth) cannot be typed into this slot at all; intake_writer.py
        // refuses them server-side for the API path, naming BOTH axes.
        // required:false + default "" means Skip declares nothing, and nothing
        // resolves to standard downstream — never ultra by default. storeOn is
        // pre_presentation_capture, NOT deck_brief: a run mode is an execution
        // axis, not deck content.
        id: "run_mode",
        order: 11.5,
        kind: "enum",
        prompt: "How hard should we run the <span class=\"emph\">build</span> of this deck?",
        help: "This is about the BUILD, not this interview. Skip it and you get Standard — we never put a run on Ultra unless you asked for it.",
        label: "Run mode",
        required: false,
        storeOn: "pre_presentation_capture.RUN_MODE",
        default: "",
        allowed_values: ["ultra", "standard", "economy"],
        value_labels: {
          "ultra": "Ultra — highest concurrency and strongest model mix (fastest, most expensive)",
          "standard": "Standard — the department default",
          "economy": "Economy — leaner and cheaper"
        }
      }
    },
    {
      id: "client_notes",
      canonical_path: "deck_brief.CLIENT_NOTES",
      section: "deck_brief",
      kind: "text",
      required: false,
      block_gate: false,
      question: {
        id: "client_notes",
        order: 12,
        kind: "text",
        prompt: "Anything else important we should <span class=\"emph\">know</span> before we start?",
        help: "Extras: target slide count, deadline, proof assets, anything else. Optional.",
        label: "Notes",
        placeholder: "Anything else we should know?",
        required: false,
        storeOn: "deck_brief.CLIENT_NOTES"
      }
    }
  ],

  // --- completeness gate ----------------------------------------------------
  // The canonical REQUIRED set. This is what both Workers validate against
  // (generated — no independent REQUIRED_BRIEF_FIELDS copies exist anywhere).
  // "false"/"no" is a REAL answer and never counts as missing; only
  // undefined / null / blank-string is missing.
  required_fields: [
    "deck_brief.OFFER_NAME",
    "deck_brief.NAMED_METHODOLOGY",
    "deck_brief.TRANSFORMATION_PROMISE",
    "deck_brief.TIME_TO_RESULT",
    "deck_brief.AUDIENCE",
    "deck_brief.CTA_ACTION",
    "deck_brief.TONE",
    "deck_brief.FINAL_PRICE",
    "pre_presentation_capture.PRESENTATION_TYPE",
    "pre_presentation_capture.WANT_SALES_CHECKOUT",
    "pre_presentation_capture.WANT_VSL_PAGE"
  ],

  // --- version-aware legacy migration ---------------------------------------
  // Legacy (version 1) records stored the upsell flags in inconsistent places.
  // Migration moves the FIRST present alias (in declaration order) to the
  // canonical path and removes the legacy keys — unless the legacy value
  // CONTRADICTS a value already at the canonical path, in which case the
  // migration REFUSES (never arbitrarily chooses). keep_legacy copies without
  // removing (for keys that double as provenance).
  migration: {
    from_version: 1,
    to_version: 2,
    boolean_normalization: { "true": "yes", "false": "no" }
  }
};

export default INTAKE_CONTRACT;