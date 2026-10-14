# Skill 71 standalone test image (fix plan Item 29, Amendment 1 rider).
#
# The suite must run identically on fleet-mac, fleet-hostinger, and
# fleet-contabo hosts and on a plain CI box. This image is the pinned
# environment for that: one Python, one Pillow, one Playwright, and the
# Chromium that Playwright release bundles (the Playwright pin IS the
# Chromium pin; Playwright ships exactly one Chromium revision per
# release and installs it below).
#
# Layout contract: the image expects a repo checkout mounted or copied
# at /work with the skill folder and its shared-utils sibling side by
# side, exactly as in trevorotts1/openclaw-onboarding:
#
#   /work/71-blackceo-signature-page/...
#   /work/shared-utils/kie_prompt_enforcer.py
#
# Run:
#   docker build -t skill71-tests tests/docker
#   docker run --rm -v /path/to/checkout:/work skill71-tests
#
# Capability behavior: the suite self-skips render tests (SKIP-RENDER)
# and pixel tests (SKIP-IMAGE) on hosts lacking a capability. Inside
# this image nothing skips: every capability is installed, so a skip
# here means the image drifted from this spec.
FROM python:3.12.7-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      fontconfig fonts-liberation fonts-dejavu-core \
      libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
      libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
      libgbm1 libasound2 libpango-1.0-0 libcairo2 \
 && rm -rf /var/lib/apt/lists/*

RUN pip install \
      pillow==11.3.0 \
      playwright==1.64.0 \
      jsonschema==4.23.0

# The Chromium revision bundled with Playwright 1.64.0, plus its
# runtime dependencies (already covered above, kept explicit so the
# install never depends on apt state from the pip step).
RUN python3 -m playwright install chromium

WORKDIR /work/71-blackceo-signature-page
CMD ["python3", "tests/run_tests.py"]
