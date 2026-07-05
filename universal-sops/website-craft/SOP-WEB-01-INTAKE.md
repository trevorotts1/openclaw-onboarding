# SOP-WEB-01: LOCK THE WEBSITE BRIEF IN ONE BLOCK

**Cluster:** Website-Craft Rules (`universal-sops/website-craft/`)
**Master authority:** `WEBSITE-PIPELINE-MANIFEST.json` + `MASTER-WEBSITE-QC-AUTOFAIL-RULESET.md`
**Owning role:** Conversion Copywriter (Marketing) — build DELEGATED to Web-Development / Skill 6
**Stage:** P0-INTAKE
**Produces:** `working/copy/website-brief.json`

---

## 0. WHY THIS SOP EXISTS

A website authored on a thin or split brief ships pages that say nothing — the exact failure mode this
cluster exists to end. The brief is the precondition for the per-page-type copy contract: it is asked
as ONE block, answered, and LOCKED before a single page section is written. A self-attested "brief
complete" flag is never trusted — the downstream `prove_web_pages.py` reads the actual copy.

## 1. THE ONE-BLOCK RULE

Deliver the intake questions in a SINGLE message, never one-question-per-turn. At minimum capture:

| Field | What it is |
|---|---|
| `brand` | The business name; anchors the voice + Grade Block palette. |
| `sitemap` | The page set to build — a subset/superset of `home`, `services`, `about`, `faq`, `contact`. Home is REQUIRED. |
| per-page `goal` | The single job of each page (Home = clarify + CTA; Services = sell each service; About = trust; FAQ = objection removal). |
| `services[]` | For a Services page: the concrete services (name + what each delivers). |
| `offer` / primary CTA | The one action the site drives (book a call, buy, subscribe). |
| `traffic_source` | Where visitors arrive from (ad, search, referral) — threads to the copy depth. |
| `copy_depth` | short / standard / long-form — the authoring target (see SOP-WEB-02). |
| `brand_colors` | Anchors the image Grade Block. |
| `proof` | Real testimonials / results / credentials — **NEVER fabricated** (truth gate). |
| `brand_voice_source` | `brand-voice-lock.md` if it exists; else the provisional source (Skill 55 Product Bio / Skill 52) per SOP-WEB-02 §1b. |

## 2. THE TRUTH GATE

Every testimonial, statistic, credential, guarantee, and scarcity claim MUST be confirmed REAL at
intake. The engine NEVER fabricates proof, urgency, or a credential. An unconfirmed claim is returned
to the owner, not invented.

## 3. LOCK IT

Write `working/copy/website-brief.json` with the sitemap, per-page goals, the services list, the
confirmed proof, and the resolved `brand_voice_source`, then mark it locked. An unlocked brief blocks
P1-COPY.

## 4. HAND TO P1-COPY

With the brief locked and `persona-selection-log.md` produced (the persona Step 0, see SOP-WEB-02 §0),
advance to **SOP-WEB-02** to author the per-page-type copy against the floors. Never guess a missing
field — return the gap list to the owner and STOP.
