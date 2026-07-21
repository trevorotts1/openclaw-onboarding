# Changelog - agnes-image

All notable changes to this skill are documented here.

---

## [v1.0.0] - July 21, 2026

### Added
- Initial release: Agnes Image 2.1 Flash endpoint reference (Skill 63).
- Synchronous text-to-image and image-to-image via
  `POST https://apihub.agnes-ai.com/v1/images/generations`
  (model `agnes-image-2.1-flash`) — one request returns the finished image
  (`data[0].url` or `data[0].b64_json`); no task polling.
- Documents required fields (`model`, `prompt`, `size`), the `1K`/`2K`/`3K`/`4K`
  size tiers crossed with aspect `ratio`, and the full ratio×tier
  output-dimension table (for example `16:9` `2K` = `2624x1472`).
- Calls out the two gotchas: `response_format` belongs in `extra_body` (not the
  top level), and image-to-image needs no `tags`.
- Rate-limit / tier awareness sourced from the vendor catalog (dated 2026-06-28)
  with confirmed and UNVERIFIED cells flagged; keys tier behavior off
  operator-set config and HTTP 429, never a hardcoded ceiling.
- References the EXISTING fleet credential `AGNES_AI_API_KEY` (SET/NOT-SET only;
  value never printed).
- Bundled `qc-agnes-image.sh` install QC that fails closed on a corrupted
  reference doc, plus `PREREQS.json` declaring Skills 01/02 and the credential.
