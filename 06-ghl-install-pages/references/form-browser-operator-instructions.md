# BROWSER-OPERATOR-INSTRUCTIONS — the explicit low-IQ click script

**Audience:** the DUMB browser operator (often MiniMax-M3). You make **NO
decisions**. Every value you type and every thing you click is spelled out
below or injected by the SMART layer as a `{{PLACEHOLDER}}` that is ALREADY
RESOLVED in the `form-click-list.json` you receive. If anything is ambiguous,
STOP and report — do not guess.

> ⚠️ The platform is **Convert and Flow = Go High Level (GHL)** — one
> platform; never a non-GHL tool name. The builder runs inside a cross-origin iframe
> (`app.gohighlevel.com` → `*.leadconnectorhq.com`): DOM ids/classes drift
> between releases, so you NEVER rely on remembered CSS.

---

## 1. TWO-LAYER HANDOFF CONTRACT

### What the SMART layer hands you (input)
`routing/form-click-list.json` — an ordered array of steps:

```json
{
  "run_id": "…",
  "location_id": "…",
  "form_name": "ZHC <name>",            // already ZHC-prefixed
  "steps": [
    {
      "id": "F5-03",
      "phase": "F5",
      "goal": "Drag the State tile onto the canvas above Phone",
      "pre_wait": {"visible_text": "Quick Add", "timeout_s": 20},
      "find": {
        "primary": {"role": "…", "name": "State", "container_hint": "Address group, left panel"},
        "fallback_text": "State",
        "position_hint": "~x190,y254 in 1280w space (hint only)"
      },
      "action": {"type": "drag", "to": {"drop_hint": "between Last Name and Phone"}},
      "type_value": null,
      "post_verify": {"visible_text": "Enter your state", "timeout_s": 15},
      "evidence": "screenshot"
    }
  ]
}
```

Guarantees you can rely on: every `type_value` is final text (no placeholders
left); custom fields are ALREADY created via the API (you only drag them from
**Add Object Fields**); the form name is already `ZHC `-prefixed; tags are NOT
your job.

### What you hand back (output)
`routing/form-operator-report.json`: per step → `{"id", "status":
"done|skipped_already_true|failed", "anchor_used": "a11y|text", "evidence":
"<path>"}`, plus the captured **embed snippet text**, the **share link**, and
the **form ID** parsed from the builder URL / share link.

---

## 2. RULES OF ENGAGEMENT (every step, no exceptions)

1. **One action per step.** Never chain.
2. **Snapshot first.** Before acting, take an accessibility snapshot
   (`snapshot -i` / `browser_snapshot`) and bind the target by **role + exact
   visible text** (`find.primary`). Coordinates in the script are HINTS for
   disambiguation only — never click blind coordinates.
3. **Fallback order:** a11y ref → exact visible text (`fallback_text`) →
   STOP-AND-REPORT. You never invent a CSS selector.
4. **Explicit waits, no fixed sleeps.** Wait for `pre_wait.visible_text` before
   acting and `post_verify.visible_text` after. Timeout → one retry from a
   fresh snapshot → then fail the step.
5. **Idempotent resume:** before acting, if `post_verify` is ALREADY true, mark
   `skipped_already_true` and move on.
6. **Screenshot after every step whose `evidence` says so.**
7. **Type by replacing:** click the input, select-all, type the value, verify
   the input now shows exactly that value.
8. **Two consecutive failed steps → abort the run** and return the report. The
   SMART layer diagnoses; you do not improvise.
9. **Never touch:** browser profile, login forms (a login form on screen means
   the seeded session FAILED — abort immediately), other sub-accounts, the
   Settings gear of GHL itself, anything not in the script.

---

## 3. THE CLICK SCRIPT (canonical form build)

Anchors verified against the source video frames (see `form-click-map.md` for the
full 42-anchor table + frame refs). Positions are 1280-wide-space hints.

### PHASE A — Navigate to Forms
| # | Goal | Find (primary → fallback) | Act | Wait/verify after |
|---|---|---|---|---|
| A1 | Open Sites | left nav item, text **`Sites`** (globe icon, ~x42,y260) | click | orange secondary nav bar visible; `Funnels` tab active |
| A2 | Open Forms | secondary-nav button, text **`Forms`** (~¾ across, ~x815,y50; NOT `Form features`) | click | tabs `All forms · Analytics · Submissions` + button `+ Create form` visible |

### PHASE B — Create the form
| # | Goal | Find | Act | Wait/verify |
|---|---|---|---|---|
| B1 | Open create modal | button **`+ Create form`** (top-right, ~x1230,y90) | click | modal title **`Create new form`** visible |
| B2 | Choose scratch | card text **`Start from Scratch`** (left card) | click card/radio | card shows blue border + filled radio |
| B3 | Create | modal button **`Create`** (bottom-right) | click | builder chrome loaded: `← Back`, name `Form <n>` + pencil, `Preview · Integrate · Save`. HEAVY load — wait for **`Save`** to render (≤60 s) |

### PHASE C — Rename
| # | Goal | Find | Act | Wait/verify |
|---|---|---|---|---|
| C1 | Edit name | top-center text matching **`Form <number>`** (or its ✎ pencil) | click | name becomes an editable/selected text field |
| C2 | Type name | the now-editable name field | select-all, type **`{{FORM_NAME}}`** (arrives as `ZHC …`) | field shows the value |
| C3 | Commit | keyboard | press **Enter** | top bar shows `{{FORM_NAME}}` |

### PHASE D — Trim defaults (only the steps the script contains)
Per field the plan removes: click the field on canvas (its label text) → wait
for the blue selection bar (gear + copy + **trash** icons top-right of the
field) → click the **trash** icon → verify the label text is GONE from the
canvas. ⚠️ Trash icon is `[runtime-capture]` — bind it from the fresh snapshot
of the selected field's toolbar, rightmost icon.

### PHASE E — Standard fields (Quick Add) — repeated per field
| # | Goal | Find | Act | Wait/verify |
|---|---|---|---|---|
| E1 | Open element panel | toolbar **`+`** (first icon, row 2, ~x27,y50) — skip if panel already shows header **`Form Element`** | click | header `Form Element` + tabs `Quick Add · Add Object Fields` |
| E2 | Ensure Quick Add tab | tab text **`Quick Add`** | click (skip if active) | category list visible |
| E3 | Find the tile | scroll left panel until tile text **`{{TILE}}`** (e.g. `State`, under its category header e.g. `Address`) visible | scroll | tile visible |
| E4 | Drag onto canvas | drag source = tile **`{{TILE}}`**; drop target = **`{{DROP_HINT}}`** (e.g. "between Last Name and Phone" — locate by the two neighbor labels) | drag | new field appears with its default label; right properties panel opens (shows `Label` input) |
| E5 | Set Label | right-panel input under label **`Label`** | select-all, type **`{{LABEL}}`** | canvas label updates |
| E6 | Set Placeholder | input under **`Placeholder`** | type **`{{PLACEHOLDER_TEXT}}`** | value shown |
| E7 | Set Query Key | input under **`Query Key`** | type **`{{QUERY_KEY}}`** (lowercase, no spaces) | value shown |
| E8 | Required OR Hidden | checkbox **`Required`** or **`Hidden`** (script says which; NEVER both — the other greys out) | click | label gains `*` (Required) / other checkbox disabled |
| E9 | Field Width | numeric input under **`Field Width`** | select-all, type **`{{WIDTH}}`** (e.g. `50`) | value = `{{WIDTH}}`, unit `%`; 50%-pairs share one row |

### PHASE F — Custom fields (Add Object Fields) — repeated per field
| # | Goal | Find | Act | Wait/verify |
|---|---|---|---|---|
| F1 | Switch tab | tab text **`Add Object Fields`** (~x178,y104) | click | object dropdown **`Contact`** + **`+ Add`** + **`Search by Name`** + folder list visible |
| F2 | Search | input placeholder **`Search by Name`** | type **`{{FIELD_LABEL_OR_KEY}}`** | matching field row(s) visible with ⋮⋮ handle |
| F3 | Drag in | row text **`{{FIELD_LABEL}}`** (its ⋮⋮ handle) → drop at **`{{DROP_HINT}}`** | drag | field on canvas + right panel opens |
| F4 | Prove it's the pre-created field | right panel → click disclosure text **`ADVANCED SETTINGS`** | click | **`Custom Field Name`** AND **`Unique Key`** are greyed/LOCKED; Unique Key contains **`zhc_`**. If EDITABLE or key lacks `zhc_` → **FAIL THE STEP** (wrong field / accidental on-the-fly create) |
| F5 | Set Label | input **`Label`** | type **`{{LABEL}}`** | canvas label updates; key unchanged |
| F6 | Required/Hidden, Width | as E8/E9 | … | … |
| F7 | Type-specific settings | disclosure e.g. **`RATING SETTINGS`**: icon buttons (star/heart/thumbs-up/flag/globe), `Icon Alignment`, `Count` dropdown, `Lowest/Highest Rating`, **`How to Store Rating Fields in Custom Fields`** dropdown (`Absolute·Percentage·Fraction`), color swatches | set each **only as scripted** | panel shows chosen values |

⛔ **You NEVER drag a Quick-Add tile that creates a NEW custom field** (the
signal: a label with a random letters+numbers suffix like `Rating rat584 1ssw`
and an EDITABLE Custom Field Name). If that appears, delete the element (trash
icon), fail the step, report. Custom fields come ONLY from Add Object Fields.

### PHASE G — Consent + footer text (scripted values)
| # | Goal | Find | Act | Wait/verify |
|---|---|---|---|---|
| G1 | Fix consent copy | canvas block containing **`[BUSINESS NAME]`** | click → rich-text editor opens → select-all → type `{{CONSENT_TEXT_1}}` (repeat for block 2) | canvas no longer contains `[BUSINESS NAME]` |
| G2 | Fix footer links | canvas text **`Privacy Policy`** (Text element) | click → in the rich-text toolbar use the **link 🔗** control → set `{{PRIVACY_URL}}`; same for `Terms of Service` → `{{TERMS_URL}}` | links point at the scripted URLs |

### PHASE H — Save
| # | Goal | Find | Act | Wait/verify |
|---|---|---|---|---|
| H1 | Save | button **`Save`** (top-right, ~x1240,y17) | click | the orange unsaved-dot on Save clears / save toast. Do NOT proceed until clear |

### PHASE I — Style
| # | Goal | Find | Act | Wait/verify |
|---|---|---|---|---|
| I1 | Deselect fields | click empty canvas margin (form-LEVEL styling requires no field selected) | click | right panel not showing a field title |
| I2 | Open styles | toolbar **⇄** icon (LAST icon in row 2, directly under Save, ~x1246,y50) | click | right panel tabs **`Styles · Themes · Advanced`** |
| I3 | Layout values | `Styles` tab → sections `LAYOUT · COLORS & BACKGROUND · MISCELLANEOUS`; inputs per script (`Columns`, `Input Style`, `Width`, `Field Spacing`, …) | set scripted values only | values shown |
| I4 | Theme (if scripted) | tab **`Themes`** → theme named **`{{THEME}}`** | click | theme applied (canvas restyles) |
| I5 | Advanced (if scripted) | tab **`Advanced`** → disclosures `FORM · INPUT FIELD · LABEL · SHORT LABEL · PLACEHOLDER` | set scripted values | values shown |
| I6 | Custom CSS | `Advanced` tab, bottom disclosure **`CUSTOM CSS`** → the line-numbered code box | click, then paste **`{{CUSTOM_CSS}}`** verbatim | editor contains the CSS (it OVERRIDES styles+themes — expected) |
| I7 | Save | as H1 | click | dot clears |

### PHASE J — Preview
| # | Goal | Find | Act | Wait/verify |
|---|---|---|---|---|
| J1 | Preview desktop | button **`Preview`** (top-right, ~x1095,y17) | click | preview renders; **screenshot** |
| J2 | Preview mobile | mobile device icon (row 2, ~x116,y50) | click | mobile layout renders; **screenshot**; return to Edit |

### PHASE K — Integrate (embed code + link)
| # | Goal | Find | Act | Wait/verify |
|---|---|---|---|---|
| K1 | Open modal | button **`Integrate`** (top-right, ~x1170,y17) | click | modal **`Embed or Share Form`**, left menu `Embed Code · Share · Email` |
| K2 | Layout type | option text **`{{EMBED_LAYOUT}}`** (`Inline` default; others: `Sticky sidebar · Polite slide-in · Popup`) + scripted Trigger/Activation/Deactivation radios | click each scripted option | selections highlighted |
| K3 | Copy snippet | button **`Copy embed code`** (bottom-right) | click, then read clipboard | clipboard contains a `<script>` tag with a GHL widget URL → save to report as `embed_snippet` |
| K4 | Share link | menu text **`Share`** → the **`Copy Link`** field (URL contains `/widget/form/`) | copy | report `share_link` + parse trailing segment as `form_id` |
| K5 | Close | modal **✕** | click | builder visible again |

### PHASE L — Handoff (NOT yours)
Embedding the snippet into the host page, CSS wrapper, tag workflow, and QC are
done by the SMART layer / Skill 44 / the QC agent using your report. Your run
ends after K5 + submitting `form-operator-report.json`.

---

## 4. FAILURE PROTOCOL
- Step fails twice (fresh snapshot both times) → mark `failed`, abort, return
  the report with the last snapshot + screenshot attached.
- Login form / 2FA prompt appears → seeded session failure → abort instantly.
- Unexpected modal/toast → screenshot it, try `Escape`/✕ once; if it persists,
  abort. Never click through unknown dialogs.
- You never roll back anything — rollback is the SMART layer's job via the run
  ledger.
