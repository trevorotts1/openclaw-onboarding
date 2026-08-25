# Book Writer — INSTRUCTIONS (downstream + cross-skill handoffs)

All handoffs are LOCAL artifacts or in-conversation; the skill never calls an external service.

## Outbound

| Artifact | Goes to | How |
|---|---|---|
| `433_Deck_Data.json` + `433_Deck_Outline.md` (4x3x3) | **Skill 51** (signature-presentation) | schema-valid deck data + outline; Skill 51 builds the offer deck. `prove_bw_433.py` guarantees the schema. |
| Avatar dossier + blended tone (`08-blended-tone.md`) | **Skill 52** (avatar-alchemist) | accepted in BOTH directions; the shared tone core keeps them consistent. |
| `Book_Cover_Prompt.md` | any image provider | the prompt file always ships; the client runs it on their own IMAGE tier. |
| The manuscript (`*-Manuscript.md`) | **Skills 49 / 50** (signature-funnel / email-engine) | launch assets from the finished book. |

## Inbound

| From | Artifact | Use |
|---|---|---|
| **Skill 52** selector | a `version=book` intake (its `test-fixtures/intake-book.json` shape) | validated by `prove_bw_intake.py --handoff`; the book run completes the gap (mode + book_about + cover_description) in one intake. |
| **Skill 52** | an existing avatar dossier + tone doc | consumed directly in `mode=4x3x3` (skips the avatar/tone phases, faithful to the source). |

## Version routing (binding)

- `version=book` → runs here.
- `version=brand` → hands off to **Skill 52** (or parks `brand-skill-not-available`) — **never** the
  book pipeline. No silent cross-version fallback in either direction; the hand-off is explicit and
  receipted, and the receiving skill re-validates under its own G0.

## Notification posture

Primary delivery = the skill's final answer in the invoking conversation (deliverables path +
`00-INDEX.md` list + certificate status). Human gates are in-conversation checkpoints, not emails.
Optional owner notification ONLY via the box's existing OpenClaw gateway if the owning department
wires it — never raw Slack/Gmail, never operator credentials. We move in silence.
