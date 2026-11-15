BLOCKED-FOLLOWUP: infographic prompt has no producer for converter-origin decks

Filed by PD-105 (lane FL17), as the spec's amendment (c) requires when nobody in
the pipeline authors the infographic prompt for a `content_general` deck.

Evidence (read-only, at branch head before this unit's commit):

- `presentation_job/dispatcher.py` (11,058 lines): `ARTIFACT_CONTRACTS` holds 11
  entries and not one is P8.3-INFOGRAPHIC; the strings "infographic" and "P8.3"
  do not occur anywhere in the file.
- `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json`: 56 phases.
  P8.3-INFOGRAPHIC (order 8.3) lists `working/prompts/infographic-prompt.txt` in
  `consumes`; ZERO phases list it in `produces_artifact`.
- The six fan-out phases are P4-COPY (by section), P4-PROMPT (by slide, width
  12), P-PROMPT-QC (by slide), P-STYLE-SPEC (by slide, 3), P-IMAGE-QC (by slide),
  P9-SPEECH (by slide). P4-PROMPT produces only `working/prompts/slide-*.txt`;
  `fanout._slides_for_units` returns slides only, so no extra unit is invented.
- CHANGELOG.md lines 4244-4255: the prompt was REMOVED from
  `P4-PROMPT.produces_artifact` because no unit could ever write it. The author
  is named as role `slide-image-creator` in `build_infographic.py`'s own failure
  text and in `sops/slide-image-creator-sops.md` step 5 — but nothing in the
  dispatcher or the manifest schedules that role for a converter-origin deck.

Conclusion: for a `content_general` (converter-origin) deck, no phase authors
`working/prompts/infographic-prompt.txt`, so P8.3-INFOGRAPHIC parks on a prompt
nothing writes. Not fixed here: out of PD-105's scope (its owned path is
`phase_verifiers.py`).
