# Brand intake: what the client is asked, and what happens when they do not know

Skill 71 never guesses a brand. The questions below come from the shared bank
(`shared-utils/client_intake/question-bank.json`); the answers arrive in the client's answers file
(`write_intake.py --answers-file`, `brand_colors.py record-answers`). Full flow: `49-signature-funnel/intake/INTAKE.md`.

| Ask | Brand file field | If the client does not know |
|---|---|---|
| Brand colors, and which is the MAIN color | `palette_roles` (primary, secondary, accent, background, text), `palette_status` | Read from logo or website, or pick one of three palettes; else the neutral default, `palette_status: default_to_confirm` |
| Fonts | `fonts`, `fonts_status`, `fonts_suggested` | Fonts stay `CLIENT_MUST_SUPPLY`; the derive-document policy picks a pair and shows it; flagged to confirm |
| Logo | `logo` (files, `wordmark_text`, status) | The business name as a text logo; flagged to confirm |
| Photos and permission | `photos` (status, permission, `empty_frame`, `likeness_generation: never`), `founder_photos` | An empty photo frame; no likeness is ever generated |

`palette_status` is `provided` (the client gave or chose it), `suggested` (we proposed it, no yes yet),
`default_to_confirm` (neutral palette applied), or `missing` (the template). An unconfirmed default is
permitted and is always labelled a proposal: `suggested` and `default_to_confirm` are proposals for the
client to confirm, never an accepted palette. A proposal may carry the internal design work, yet it may not ship: publish needs `provided`. The shared intake reports it as `palette_status`, with `confirmed` true only for `provided`. `brand_colors.py check` passes for the first three and prints `TO CONFIRM` for
the last two; it fails only when no palette exists. The legacy slots `palette.gold`, `navy` and `cream` stay
filled (primary, text, first background) so nothing downstream changes.

Skill 71 asks these brand questions through the shared bank's page-only profile, `profiles.page`
(`--mode page`), reopened on the client's existing answers file: a brand answer the client already confirmed
is reused, never asked again, and only the brand questions still open are put to them.

Another client's palette is never a source: the brand file must belong to the run's `brand_owner`, and the neutral default is
written only into that client's own file.
