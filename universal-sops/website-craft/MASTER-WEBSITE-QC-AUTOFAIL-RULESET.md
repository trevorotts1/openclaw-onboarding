# MASTER WEBSITE QC AUTO-FAIL RULESET (`AF-WEB-*`)

**Cluster:** Website-Craft Rules (`universal-sops/website-craft/`)
**Enforced by:** `prove_web_pages.py` (stdlib, model-free) at P1-COPY and re-run at P4-CERTIFY.

Every code below is a HARD auto-fail: it cannot be averaged away, floored, or self-attested past. The
prover MEASURES the artifact (stripped word counts, role presence, pair counts); a self-reported number
is never trusted.

| Code | Trips when | Fix |
|---|---|---|
| `AF-WEB-VOICE-UNANCHORED` | `brand_voice_source` is neither `brand-voice-lock.md` nor a `provisional:*` lock | Resolve a lock or a provisional lock from Skill 55 Product Bio / Skill 52 (SOP-WEB-02 §1b). |
| `AF-WEB-PERSONA-LOG` | no `persona_selection_log` referenced | Run the persona Step 0 selector; write `persona-selection-log.md`. |
| `AF-WEB-NO-PAGES` | ledger has no `pages` array | Author the sitemap pages. |
| `AF-WEB-UNKNOWN-PAGETYPE` | a page has an unrecognized `page_type` | Use a known type (`home`/`services`/`about`/`faq`) or extend the cluster deliberately. |
| `AF-WEB-HOME-SB7` | Home is missing any StoryBrand SB7 role | Add the missing role section(s). |
| `AF-WEB-HOME-THIN` | Home total < 250 stripped words | Write the Home page to depth. |
| `AF-WEB-SERVICES-EMPTY` | Services page declares no service blocks | Author one block per service. |
| `AF-WEB-SERVICE-THIN` | a service block < 400 stripped words | Expand the service copy to the floor. |
| `AF-WEB-ABOUT-THIN` | About < 500 stripped words | Write the full trust page. |
| `AF-WEB-FAQ-COUNT` | fewer than 8 complete Q&A pairs | Add real objection-removing Q&As. |
| `AF-WEB-LEDGER-UNREADABLE` | the ledger file is missing/invalid JSON | Fix the ledger path/JSON. |

## The floors (adjustable constants table in `prove_web_pages.py`)

```
HOME_MIN_WORDS    = 250
SERVICE_MIN_WORDS = 400
ABOUT_MIN_WORDS   = 500
FAQ_MIN_PAIRS     = 8
```

These are the proposed defaults from FIX-COPY-03. They live as a constants table so a ratified change
is a one-line edit in one place — never scattered magic numbers. Raising a floor is allowed; LOWERING a
floor to make a page pass is a doctrine violation — escalate instead.
