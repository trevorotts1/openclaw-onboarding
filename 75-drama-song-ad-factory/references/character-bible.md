# The Character Bible (DEL-02)

The CHARACTER BIBLE is the client's approval document for the person who stars in the
video: who they are, where they come from, how they look, and the four reference
photographs every shot has to match. It is a PDF in the run's delivery folder, laid out
to the same look as the client guide -- bright white page, dark ink, generous margins,
a teal header band with a gold rule, and **nothing smaller than 12 point anywhere**.

## It is part of intake, not a document written afterwards

The character's **description**, **background** and **ethnicity** are asked by intake.
`intake_preflight.intake.evaluate()` calls `character_bible.questions(brief)` as soon as
the story essentials are answered, and holds the run at `missing-character` until the
character is complete. A brief that declares no character is untouched, and the story
slots keep their order and their three-question cap.

A brief declares a character when it carries any `character_*` field, or when the
CHARACTER card answer is a new character (`saved_character` / `character_new` set to
`new` / `1` / `Create a new character`).

When the answer is complete, `character_bible.record(brief)` builds the bible record and
`write_delivery()` renders it.

## Reuse: the character library holds the data

`character_library.save_character(..., background=..., ethnicity=...)` stores both bible
fields next to the description and the reference images, and
`character_library.brief_fields()` hands them back as `character_background` and
`character_ethnicity`. A character answered once is answered for every later ad, so
intake asks only for the parts that are genuinely missing. Records saved before those
two fields existed read back as empty strings and are asked for once.

## The CHARACTER IMAGE BIBLE

Page two lays the four reference angles out together with the text, in this order:

| View | Panel label |
|---|---|
| `close-up` | Close-Up |
| `side-profile` | Side Profile |
| `three-quarter` | Three-Quarter View |
| `full-standing` | Full Standing |

`resolve_images()` maps a directory, a list of paths or an explicit `{view: path}` dict
onto those four views by filename, so `close-up.png`, `side profile.png`,
`three-quarter-view.png` and `full-standing.png` all land in the right panel. A view
with no image is a labelled placeholder -- "Not supplied yet" -- never a blank box. A
path that does not exist fails by name (`IMAGE_NOT_FOUND`), and an image format the
writer cannot embed fails by name rather than disappearing from the page.

PNG (8-bit, non-interlaced: grayscale, palette, RGB or RGBA) and JPEG are supported.
RGBA and palette transparency are composited over white, so nothing renders murky.

## What can never reach a client PDF

Every string is checked by `assert_client_safe()` before it is drawn, and the test suite
runs every module string through the same guard:

* money amounts of any currency;
* income promises ("guaranteed income", "financial freedom", and the rest of the list);
* product, model and tool names.

`record()` refuses the whole document (`CLIENT_TEXT_REFUSED`) rather than editing the
client's words. The guard carries the paid job host as a bare word on purpose: the
endpoint string belongs to `qc-no-direct-kie.sh`, not to this file.

## Two font gates

1. `pdf_writer.text()` refuses to draw anything under 12 point, so a small size can
   never be authored;
2. `pdf_writer.check_font_floor()` re-reads the **finished file** and fails on any font
   size under 12 point. It reads only unfiltered streams, so compressed image bytes are
   never mistaken for a text operator.

The PDF itself is written by `pdf_writer.py`, standard library only -- no renderer
binary, no third-party package, so the suite runs under an empty home.

## Command line

```bash
# What is still missing from this character?
python3 scripts/core/character_bible/character_bible.py questions --brief brief.json

# Write the bible into the run's delivery folder (02 - Character Bible.pdf)
python3 scripts/core/character_bible/character_bible.py render \
    --brief brief.json --delivery /path/to/run/delivery \
    --image /path/to/reference-images
```

## Delivery file

One delivery folder per client run, numbered so every unit owns its own slot.
Item 02 is BOTH files: the bible itself and the reference pictures as
separate files beside it (the same pictures the layout used, written by the
one `write_delivery` deliver path -- no reference picture, no item):

```
02 - Character Bible.pdf
02 - Character Bible Images/
```
