# PowerPoint packaging for motion components (MG-035)

How a rendered `powerpoint_graphic` component becomes a slide-ready
delivery package: what the package contains, the gates it must pass,
how the poster is chosen, how the deck embeds the video, and what is
and is not claimed about playback.

Code: `scripts/powerpoint_package.py` (the packager),
`scripts/poster_select.py` (the poster selector),
`scripts/powerpoint_adapter.py` (the presentation adapter).
Record schema: `references/powerpoint-package-schema.json`.

## The package

`powerpoint_package.py package --job-dir DIR --out DIR` writes:

| File | What it is |
| --- | --- |
| `component.mp4` | The rendered artifact, byte-identical to the job's `renders/final.mp4`. 16:9 H.264, yuv420p, normally silent. |
| `poster.png` | The deliberately selected poster frame (see below), extracted from the artifact at full canvas size. |
| `fallback.png` | The static fallback image for PDF export and nonplaying environments. It carries the poster's readable final state. |
| `deck.pptx` | The embedded-video test deck built by the adapter: slide 1 the video, slide 2 the static fallback. |
| `package-record.json` | The governed package record: hashes for every file, the poster selection and its recorded reason, playback metadata, the placement text audit, the loop and hold checks, and the QC binding. Validated against `references/powerpoint-package-schema.json` before the package is released. |
| `final-qc.json` | The consumed MG-034 final QC record, copied in so the package carries its own gate evidence. |
| `export-record.json` | The MG-040 export record for the artifact, when the render produced one. |
| `source/` | The job package records the deck was built from (the manifest delivery requirement `source_package`): manifest, compiled timeline and sidecar, storyboard, design, assets, media, scene specs, datasets. |

`powerpoint_package.py verify --package-dir DIR` re-reads the
record, re-hashes every file it binds, and re-runs the deck's
structural embed proof.

## The QC gate

Packaging is a post-`FINAL_QC_PASSED` lifecycle step (directive
Section 16.8). The packager consumes the MG-034 record at
`qc/final-qc.json`; it never re-runs or imports the QC layer. The
gate refuses by name:

- no record: `PPTX_QC_RECORD_MISSING` (MG_INPUT_MISSING, exit 3)
- the record names a different job: `PPTX_QC_FOREIGN_JOB`
  (MG_FOREIGN_JOB, exit 9)
- the record's artifact hash differs from the artifact's bytes:
  `PPTX_QC_HASH_MISMATCH` (MG_HASH_MISMATCH, exit 9)
- verdict is not pass: `PPTX_QC_NOT_PASSED` (MG_QC_FAILED, exit 6),
  naming the failed checks

The packager then re-probes the artifact itself (codec, pixel
format, canvas dimensions, decoded frame count against the
compiled timeline, frame rate, duration within one frame per M01)
and resolves the MG-023 audio plan once from the compiled timeline
through `scripts/audio_policy.py`. Mode `none` with an audio stream
in the artifact refuses as `PPTX_AUDIO_MODE_VIOLATION`: a
PowerPoint component is silent because the presenter narrates live.

## Poster selection

The poster is the still that stands for the piece everywhere the
video does not play, so it is selected from the compiled plan, not
grabbed. A frame is eligible only when every scene has completed
its motion there and the frame sits inside the terminal hold; the
poster therefore always shows the piece's final readable state.

- A declared `delivery.poster_frame` is honored only when
  eligible. A declared frame inside a changing interval refuses as
  `PPTX_POSTER_FRAME_INVALID`, citing the scene's own semantic
  assertion when one pins the partial state. This is the Section
  17.2 defect: at frame 45 of the C05 fixture the bars stand at
  half reveal (widths 240, 360, 600) while the final value labels
  already print, so a poster there would present partial data as
  final.
- With no declaration, the earliest proof event inside the hold
  wins; failing that, the first frame of the hold.
- A piece that never reaches a stable state refuses as
  `PPTX_POSTER_STATE_UNAVAILABLE` rather than shipping a guess.
  One bounded exception: a loop package has no final state by
  construction, so a declared poster frame, or failing that a
  proof event frame, is taken as the loop's representative state
  and recorded as such. The exception never applies when a stable
  state exists.

The selection is also measured against the rendered artifact: the
decoded poster frame must match the decoded final frame within
encoder noise (both sit in the hold), and must differ from a
mid-reveal frame. The package record carries the frame, the rule
that chose it, the reason in words, the stable interval, and the
measurements.

## Playback metadata and the deck

The package record carries the playback contract from the manifest:
start (`on_click` or `automatic`), repeat (`once` or `loop`), end
behavior, the intended duration in frames and seconds, and the
final hold state.

The adapter writes the deck at the OOXML package level. Plainly:
the existing PowerPoint assembly path cannot embed video at all.
`assemble_pptx` in the presentation crew's `build_deck.py` places
pictures only; integration map P04 records that `add_movie` does
not exist there, and the governed `add_motion_media` function is
MG-036's deliverable. This adapter does not edit `build_deck.py`.
It writes the package structure that python-pptx's `add_movie`
writes (verified element for element against python-pptx 1.0.2,
the library the existing path uses):

- the MP4 as a media part at `ppt/media/media1.mp4`
- two relationships from the video slide to that part: the
  officeDocument `video` relationship consumed by `a:videoFile`,
  and the Microsoft `media` relationship consumed by the
  `p14:media` extension
- the poster PNG as the video picture's blip, so the slide shows
  the readable poster state whenever the video is not playing,
  including in PDF export
- a click action (`ppaction://media`) on the picture, and a media
  timing node whose start condition is `indefinite` for
  `on_click` and `0` for `automatic`; `loop` adds
  `repeatCount="indefinite"` to the media node

One deviation from the library's output: `[Content_Types].xml`
declares the MP4 part `video/mp4` where python-pptx writes
`video/unknown`.

MG-036's `add_motion_media` replaces this producer mechanism: the
same parts and relationships, created by python-pptx inside the
deck pipeline, with the poster and the fallback slide kept as
separate governed outputs exactly as here. The deck furniture
(Office template master, Blank layout, theme) is the furniture the
existing path's `Presentation()` emits, trimmed to the one layout
the assembly uses; copies live under `scripts/pptx_template/`. The
deck keeps the assembly's shape: 10 x 5.625 inch slides, full-bleed
pictures, atomic save.

`powerpoint_adapter.py verify --deck DECK` is the moved-deck proof:
it unzips a deck at any path, follows the slide relationships, and
shows the media part is inside the file (no external targets),
byte-identical to the packaged artifact, and parseable by ffprobe
at the packaged dimensions and frame count; it also proves the
poster part is the video slide's picture and the fallback slide
carries the fallback image.

## Placement text audit

Essential text is judged at the package's actual placement size
(M07), never at authoring size. The scale is the display width over
the canvas width; the export keeps its own 16:9 aspect regardless
of the slide it sits in. An inset display width is declared in px,
or in mm converted through the slide's own px-per-mm ratio (a
254 mm wide slide against a 1920 px canvas); no display DPI is ever
assumed. Each design field maps to a typography role
(`headline_px` to headline, `label_px` to chart_category_label,
`value_px` to chart_value, `disclosure_px` to disclosure, per
MG-014) and the effective size, authored times scale, must meet
the MG-013 floor in `references/typography-tokens.json`. Any role
below its floor refuses the package as `PPTX_TEXT_BELOW_FLOOR`,
naming the role, the authored size, the effective size, and the
floor: a component whose text fails at placement is refused, not
shipped small. An inset package without a declared display width
refuses as `PPTX_PLACEMENT_UNPROVABLE`.

The record also carries the honest caveat: font size against the
floors is necessary evidence, not a complete legibility guarantee.

## Loop seam and final hold

Loop packages carry the M13 check: the decoded last frame is
compared with the decoded first frame (the state at one full
period against the state at zero), and the seam step must not dwarf
the piece's own typical frame step (refusal `PPTX_LOOP_SEAM` at
more than four times the typical step and above a small absolute
floor). A reveal that ends away from its start cannot loop
seamlessly and is refused by name. Reveal-and-hold packages must
end on the intended readable state: the poster's measured equality
with the final frame is the hold check.

## Platform truth

Playback inside Microsoft PowerPoint is UNVERIFIED on every
platform. This build runs on Linux, where PowerPoint is not
available, and no substitute is installed or consulted under
PowerPoint's name. What is proven is structural: the media is
embedded in the deck file itself, byte-identical after the deck is
moved or copied, with the poster as the slide's image. PDF fallback
evidence is gathered the same honest way: the deck is converted to
PDF by the tools this platform actually has (LibreOffice headless)
and the rendered pages are compared against the poster state;
PowerPoint's own PDF export is likewise UNVERIFIED.

## A known seam, recorded

The canonical contracts schema constrains a font requirement's
`family_alias` to an ID token (the fixture's is `fixture-sans`) and
its `source` to `runtime_registry`; the runtime registry maps the
token to the family that renders (Liberation Sans). MG-034's
`package.fonts` check resolves runtime-registry requirements by
exact family name through fontconfig, which an alias token cannot
satisfy. Delivery-stage job packages therefore record the
requirement with the resolved family name, exactly as MG-034's own
passing job packages do, and keep the intake record beside it
(`intake-assets.json`). The alias, the resolved family, and the
rendered font bytes (hashes in the render evidence) stay visible;
reconciling the three layers' font naming is a contracts-revision
question for the build's documentation pass, not something this
packager decides silently.
