# Prompt 03 — Per-Platform 'Superpower Strategy' Injection Block

- **Source workflow:** `02-content-generator` (02-Social Media in a Box Content Generator)
- **Model at export time:** n/a (prompt fragment assembler — consumed by Prompt 04's System message)
- **Purpose:** Code node that assembles the platform-specific strategy fragments (Facebook/Instagram/LinkedIn/YouTube/TikTok/Pinterest/Google Business) injected into the Reformatter agent's system message as {{ $json.strategyPrompt }}.
- **Anonymization:** verified clean — no client names or secrets in this prompt text. Client-identifying data in this workflow family lives ONLY in raw-export `pinData` (see ANALYSIS.md `client_name_locations`); it is excluded here.

## System (assembled fragment — full assembler code, strategy text inline)

_Source: node `Assemble Strategy1` → jsCode_

```
// ---------------------------------------------------------
// STRATEGY ASSEMBLER (V3 ROBUST)
// ---------------------------------------------------------
// Purpose: Build the 'Superpowers' string for the next agent.
// This injects the specific strategies we discussed.

const platforms = $('Split In Batches1').item.json.platforms || [];
let strategies = [];

// 1. FACEBOOK STRATEGY
if (platforms.some(p => p.platform === 'Facebook')) {
  strategies.push(`
  [FACEBOOK STRATEGY]
  - FEED POST: Use a Conversational Tone ("We", "You"). Structure: Hook -> Story -> Lesson. CRITICAL: You MUST end the post with a specific Question to trigger algorithm comments (e.g., "Has this happened to you?").
  - STORY: Urgent, Casual, "Behind the Scenes" vibe. Text must be under 15 words. CTA: "Tap to read".
  - REEL SCRIPT: 0-3s Visual Hook (Interrupt pattern). 15-60s body. Include [Visual Cues] for the creator.`);
}

// 2. INSTAGRAM STRATEGY
if (platforms.some(p => p.platform === 'Instagram')) {
  strategies.push(`
  [INSTAGRAM STRATEGY]
  - POST: Aesthetic Micro-Blog style. Headline in ALL CAPS or 🚨 Emojis. Use line breaks for readability. Place 15-20 Niche Hashtags at the very bottom.
  - STORY: Interactive focus. Prompt for Polls/Stickers. Focus on driving traffic to "Link in Bio".
  - REEL SCRIPT: High energy. Suggest a specific "Vibe" or Trending Audio style. Fast pacing (cuts every 3s).`);
}

// 3. LINKEDIN STRATEGY
if (platforms.some(p => p.platform === 'LinkedIn')) {
  strategies.push(`
  [LINKEDIN STRATEGY]
  - POST: "Bro-etry" Style. One sentence per line. Heavy use of white space. Tone: Professional but Personal. 
  - HOOK: Use a Contrarian Opinion or a Hard Business Lesson.
  - CRITICAL RULE: Do NOT put external links in the post body. Instead, generate a separate "followUpComment" string containing the link/resource.`);
}

// 4. YOUTUBE STRATEGY
if (platforms.some(p => p.platform === 'YouTube')) {
  strategies.push(`
  [YOUTUBE STRATEGY]
  - VIDEO (Long): Structured Script. 1. Hook (Promise) 2. Bumper 3. Value Points 4. CTA (Subscribe).
  - SHORTS: Loopable Script. The last sentence must flow syntactically back into the first sentence to encourage replays.`);
}

// 5. TIKTOK STRATEGY
if (platforms.some(p => p.platform === 'TikTok')) {
  strategies.push(`
  [TIKTOK STRATEGY]
  - SCRIPT: Raw, Unpolished, "UGC" feel. Visual Shock in first 3 seconds. Entertainment > Education.
  - SEO: The Caption must include 3-4 semantic keywords (TikTok is a Search Engine).`);
}

// 6. PINTEREST STRATEGY
if (platforms.some(p => p.platform === 'Pinterest')) {
  strategies.push(`
  [PINTEREST STRATEGY]
  - PIN DESCRIPTION: SEO Focus. NOT a story. "How to [Benefit]..." or "5 Ways to...". Keyword rich description for search indexing.`);
}

// 7. GOOGLE STRATEGY
if (platforms.some(p => p.platform === 'Google')) {
  strategies.push(`
  [GOOGLE BUSINESS STRATEGY]
  - UPDATE: Transactional. "What's New" or "Special Offer". Direct, urgent CTA: "Call Now" or "Book Appointment". Local SEO keywords.`);
}

return {
  json: {
    strategyPrompt: strategies.join('\n\n'),
    coreConcept: $input.item.json.output // Output from previous Core Agent
  }
};
```
