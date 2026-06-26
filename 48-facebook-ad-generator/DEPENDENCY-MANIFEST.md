# Skill 48 — Dependency Manifest

## Runtime
- `python3 >= 3.8` — the entire enforcement spine (foreman + checkers + sync + Guard A +
  tests) is **stdlib-only** (`json`, `re`, `ast`, `pathlib`, `urllib`). No third-party
  dependency is needed to run the gates.
- `requests` — used by the REUSED Kie image adapter at S5 generation time (client box).

## Reused modules (NOT written fresh)
- `47-movie-producer/kie-adapters/tools/graphics/kie_image.py` — image generation via Kie
  `gpt-image-*`. Reused as-is; auto-adopts future gpt-image versions. Uses the client's
  own `KIE_API_KEY` only.
- `tools/ghl_media.py` — ported from `06-ghl-install-pages/tools/ghl_media.py`, with ONE
  addition: `create_media_folder()` (`POST /medias/folder`, `Version: 2021-07-28`,
  client's own LOCATION PIT) + the "upload to root with a name prefix" fallback. Hosts the
  images and returns public, login-free GoHighLevel URLs.

## Keys (client's own — operator keys NEVER appear on the client box)
- `KIE_API_KEY` — image generation.
- `GOHIGHLEVEL_API_KEY` / `GHL_API_KEY` (LOCATION Private Integration Token, `medias.write`)
  + `GHL_LOCATION_ID` — image hosting.

## Re-indexing — NONE
Skill 48 adds no persona blueprint and runs no indexer. Verified no-op: the search box is
built only from author blueprint files; this skill reuses the 42 built authors and is read
by direct file path.

## Deliberately NOT a dependency
- No Meta/Facebook API SDK — PLAI is the only ad path.
- No OCR / text-reading library — text is baked into the image; legibility is judged by an
  independent VISION reviewer + the human at the approve pause.
- No native paid image provider (FAL/Runway/OpenAI/Google) — generation routes through Kie
  only.
