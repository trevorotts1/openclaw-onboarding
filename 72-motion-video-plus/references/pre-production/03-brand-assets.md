# Pre-production 03: Brand assets

Collect the real assets before any animation code is written. Real beats redrawn, every time.

## Checklist

- [ ] Logo files: the brand's actual logo in a resolution that survives 1080p. Note which lockup goes where (opener, end card, watermark if any).
- [ ] Typefaces: the brand's real display face and UI face as files the page can load locally. No webfont loading during the timeline; fonts load before frame 0.
- [ ] Palette: exact hex values. One accent color unless the brief approves more.
- [ ] Product UI: real screenshots or captures of the product, at the resolution they will appear. When a piece exists only as a screenshot, rebuild it element by element and note that in a comment.
- [ ] Voice: the Fish Audio reference id and a 10-second sample of the brand's approved delivery for tone matching.
- [ ] Legal: logo clear-space and minimum-size rules, any claims that need on-screen disclaimers, music direction (the synthesized score is original, so licensing is not a concern).

## Output

Copy `references/brand-bible-template.md` to `<brand>-brand-bible.md` and fill every section with the collected assets. The brand bible is loaded on this run and every later run for the brand.
