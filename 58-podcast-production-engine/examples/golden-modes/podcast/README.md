Golden regression fixtures, Podcast Production Engine (Skill 58)

Four fictional brands, none of them fleet clients, exercising the four output-type presets end to end, each with genuinely authored content and no padding to hit a floor. These fixtures adapt the Skill 57 golden-modes pattern (delivery certificate plus a working tree of provenance, gates, config, and media) to the Skill 58 eighteen-step pipeline and its state machine.

Every file here obeys the two writing rules that bind everything this engine produces: zero em dash characters, and no triple-backtick code fences inside produced output. The fixtures are data, not runnable code; they are the reference the runtime engine and its provers regenerate against.

THE FOUR FIXTURES

    fixture           preset               proves
    personal/         solo                 a full Personal-mode episode that passes the whole EPISODE gate
    interview/        interview            a full Interview-mode episode plus a book teaser, whole EPISODE gate
    season-strategy/  season_strategy      a planning deliverable, document QC only, mints NO episode certificate
    asset-pack/       episode_asset_pack   regenerates one existing episode's assets, idempotent, no re-publish

MEASURED FACTS (honest, computed with Fish emotion tags stripped)

    personal   The Winter I Almost Locked the Door   vulnerable       1284 words   550 s   14 tags   she/her
    interview  The Least Important Farmer on the Block  counter_intuitive  1179 words   505 s   13 tags   guest they/them
    interview  book teaser Unnecessary                  guest voice      603 words    3-page cap, 14-point PDF floor
    season     Harborline Coffee, eight-episode slate   mixed            document QC, no render, no publish
    asset-pack First Light, print cover plus docs        regeneration     idempotent against the ledger

Both episodes choose a runtime inside the seven to fifteen minute band at one hundred forty words per minute. Neither is padded; the Personal episode runs about nine point two minutes and the Interview about eight point four, because tight material becomes a tight short episode, never filler.

THE TWO GATES ARE NEVER CONFLATED

There are two separate quality gates in this project and these fixtures keep them apart on purpose.

Gate B, the EPISODE gate, decides whether an episode ships to a listener: sixteen Tier 1 hard-fail checks (all binary), then the ten-dimension rubric at eight or higher on every dimension with no averaging, then the honest Part A checklist, with a three-strike cap. The personal/ and interview/ fixtures carry an EPISODE-CERTIFICATE that records this gate. Their working/qc/tier1.json and working/qc/rubric.json hold the per-check and per-dimension results.

Gate A, the BUILD gate, is the fleet ten-category rubric at the eight point five threshold, and it decides whether build work merges. It is administered separately per unit, not from these fixtures. The season-strategy/ and asset-pack/ fixtures produce documents and assets rather than an episode, so they carry a strategy or asset-pack certificate under the build gate's document and media quality control, and they deliberately mint no episode certificate.

A build unit scoring nine says nothing about an episode, and a perfect episode says nothing about merge readiness. The certificates in this tree state which gate they belong to in their gate_note field.

CONTENT AUTHENTICITY (no padding, no fabrication)

Every script and document is real, distinct prose written for its fictional brand and theme.

- personal is a Vulnerable first-person confession built only from the respondent's own supplied stories (a fallen wholesale order, a closed account, a sick parent two states away, and a customer named Ruth who asked to watch one bowl be thrown). First person throughout, she/her, no external study or statistic cited, nothing fabricated.
- interview is a Counter Intuitive episode where the host speaks in first person and the guest, Sasha Okafor, is third person by name with an epic guest introduction present and the pronoun they/them governing every reference. The word paradox never appears, as the Counter Intuitive engine forbids. The claim is carried by the guest's own lived operating history, no external data invented.
- book teaser is a first-chapter intro in the guest's own voice ending on a cliffhanger, built only from what the guest shared.
- season-strategy is a genuine eight-episode plan with a style and a mode per slot, drawn on the director-of-podcast doctrine, with real key performance indicators.

No case study, statistic, institution, person, or biography anywhere in these fixtures is fabricated. Where an episode is intentionally source-light, that is the honest posture the no-fabrication check requires over inventing sources.

RUNTIME PROVENANCE, ZERO ANTHROPIC

Each fixture's working/provenance/calls.json records the runtime models that produced it: the writer chain is Ollama Cloud Kimi 2.6 first, then GLM 5.2, then the OpenRouter equivalents, then Gemini 3.1 Flash Lite as the final fallback; the semantic judge tier is Gemini 3.1 Flash Lite or GLM 5.2 and is always distinct from the writer; audio is Fish Audio s2.1-pro with the client's own reference_id and never the free tier; cover art is Kie.ai gpt-image-2. Every certificate carries zero_anthropic true. No Anthropic model id, provider, package, key, or host appears in any runtime file, which is what guard-no-anthropic-runtime.py enforces at the merge gate.

SILENCE AND SECRECY

Every delivery report is operator-only; the engine emits zero customer-facing messages, because Convert and Flow owns all customer messaging. Every credential in every config.json is stored as REFERENCED-FROM-ENV; no secret value is ever printed. The client-facing name is Convert and Flow, never the platform's other name.

TREE

    <preset>/
      delivery/
        EPISODE-CERTIFICATE.{md,json}   or STRATEGY / ASSET-PACK certificate for the thin presets
        episode-script.txt              the pure deliverable (episodes only; script and emotion tags, nothing else)
        book-teaser.txt                 interview only
        season-strategy.md              season-strategy only
        delivery-report.md              operator-channel-only report reproducing Part A honestly
      working/
        config.json                     per-client config, secrets referenced from env, routing chain, silence posture
        intake/canonical-payload.json   the canonical payload with the derived pd- job key and the preset
        research/research-package.json   frozen research package (episodes and season-strategy)
        blueprint/blueprint.json         internal blueprint (episodes)
        qc/tier1.json, qc/rubric.json    the EPISODE gate results (episodes)
        state/ledger.json                the state-machine transitions recorded by podcast_state.py
        provenance/calls.json            the runtime models used, zero Anthropic
        media/episode.json               audio and cover manifest with the honest measured metrics

REUSE

This directory is the Skill 58 counterpart to 57-social-media-in-a-box/examples/golden-modes/podcast/. Skill 57 remains the social packaging lane; Skill 58 is canonical for full published episodes. The Episode Asset Pack preset is the sanctioned handoff between them.