# Ready-to-Post Kit (unit DEL-07)

The kit that finishes a delivery: one bright, client-facing PDF that says
**which version to post where**, carries **the link**, hands over a caption
and a suggested hashtag set for **YouTube, Instagram, TikTok and Facebook**,
and does **YouTube properly** — title, description and tags.

Deliverables, written into the ad's own delivery folder (numbered, so they
sort next to the files they talk about):

| File | What it is |
|---|---|
| `07 - Ready-to-Post Kit.pdf` | the kit the client reads and posts from |
| `07 - Ready-to-Post Kit.json` | the same kit as data, for QC and manifests |

## The command

```bash
python3 scripts/core/ready_post_kit/ready_post_kit.py \
    --run-dir "$RUN" --delivery "$DELIVERY" \
    [--client-dir <client data folder>] [--out <folder>] [--quiet]
```

Exit codes: `0` built, `2` refused (a named `KIT_*` code on stderr), `1`
unexpected error. No network, no spend, no third-party package: the PDF is
written by the module's own small writer, so it builds on a client box.

## What it reads

| Source | Used for |
|---|---|
| `brief.json` | the offer and the link (`link` / `buy_link` / `purchase_url` / `buy_url` / `url` / `website` / `banner`) |
| `card-answers.json` | length (which cutdowns the run carries) and shape (which way the master is framed) |
| `creative/script.json` | the title, the story lines and the lyric lines the captions open with |
| `creative/script-approval.json` | the "client read it before the song" line |
| `storyboard/gate.json` | proof the shots were approved before filming |
| `delivery-receipt.json` | the measured pre-delivery answers the kit reports |
| the delivery folder's files | every video, clip and song it can place, plus the `Banner link` line in `README.md` |
| `character-library/` (`--client-dir`) | a saved character's name in the hashtag set |

The link itself is resolved in that order — brief alias, a URL inside the
offer sentence, then the `Banner link` line the batch README publishes — and
no kit is built without one.

## What is on the page

1. **The link**, big, at the top, and repeated inside every caption.
2. **Which version to post where** — one row per delivered file (shape,
   cutdown or song) with the platforms that shape travels on. The cutdown
   rows come from `clip_cutdown.clips_for(length)`, so a 3-, 5- or 10-minute
   run always schedules the 60- and 90-second rows even before the files
   land, and a 60- or 90-second run never shows them.
3. **YouTube**: title (100 characters max), description (the hook, the
   offer, the link and the hashtag line) and tags (500 characters max), with
   the counts shown so the client can see the room left.
4. **Instagram, TikTok, Facebook**: one caption each in a panel, the
   hashtags underneath and a short note on where the link goes on that
   platform.
5. **Suggested hashtags**: the shared set plus the per-platform sets.
6. **Checked before you post**: storyboard shots approved, script on file,
   the script approval record and the measured delivery answers —
   honestly, including "not measured yet" when the receipt has none.

## The laws (all fail closed, all named)

| Code | Refused when |
|---|---|
| `KIT_NO_LINK` | no link resolves from any source |
| `KIT_STORYBOARD_NOT_APPROVED` | `storyboard/gate.json` is missing or has no approved shots |
| `KIT_NO_SCRIPT` | `creative/script.json` is missing or has no title |
| `KIT_DELIVERY_RECEIPT_MISSING` | the delivery folder carries no `delivery-receipt.json` |
| `KIT_CHECKLIST_FAILED` | a measured answer in the delivery checklist is still "no" |
| `KIT_BANNED_TEXT` | any copy reaching the page carries a tool or model name, a dollar amount or an income promise |
| `KIT_FONT_FLOOR` | the layout was ever asked to draw below 12 pt |
| `KIT_NO_DELIVERY` | the delivery folder does not exist |

`KIT_BANNED_TEXT` audits **every** string in the kit — the client's own
offer included — because the page is the deliverable. A brief that carries a
price or a product-tool name is refused, not printed.

## Look

White page, near-black ink, deep-blue headings with a gold rule (the same
gold the client guide uses for its "you approve" stars), light panels behind
each caption. **Nothing on the page is under 12 pt** — body, notes, table
cells and the smallest caption are all 12 pt or larger, and the floor is
enforced twice: in the layout (`KIT_FONT_FLOOR`) and in the test suite,
which parses the drawn sizes out of the finished PDF.

## Reuse (never re-implemented here)

- `clip_cutdown.clips_for` — which short clips the chosen length carries;
- `batch_zip` — the `Banner link` line format the kit reads as a link source;
- `delivery_checklist` — the measured answers reported, and the gate that
  refuses a kit while one is still "no";
- `character_library.list_characters` — a saved character's name;
- the storyboard approval gate — `storyboard/gate.json`;
- the script approval record — `creative/script-approval.json` plus the
  approved `creative/script.json`;
- `card answers` — `card-answers.json` for length and shape;
- `captions_burn` — the caption words are the approved sheet's own words;
  this kit never re-spells them.

Proof: `scripts/core/ready_post_kit/test_ready_post_kit.py` (19 cases — the
build, the four platforms, the YouTube limits, the placement rows, every
named refusal, the CLI exit codes, the 12 pt floor read back out of the
finished PDF, and the saved-character hashtag).
