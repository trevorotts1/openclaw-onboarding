# Standalone test image

`Dockerfile` in this folder is the pinned environment for the Skill 71
standalone suite (fix plan Item 29, Amendment 1 rider): Python 3.12.7,
Pillow 11.3.0, Playwright 1.64.0 with its bundled Chromium, and
jsonschema 4.23.0 (the run-events and REPORT.json schemas are part of
the system under test, so the validator is part of the image).

The suite also runs without Docker on any host that has the pieces;
`verify.sh --capabilities` prints the host's capability matrix and the
named skips (SKIP-RENDER for missing Playwright/Chromium, SKIP-IMAGE
for missing Pillow). Inside the Docker image nothing is expected to
skip.

Layout: mount a repo checkout at `/work` so the skill folder and
`shared-utils/` sit side by side, as in the onboarding repo. The
default command runs `tests/run_tests.py`.
