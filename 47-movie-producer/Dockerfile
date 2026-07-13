# Skill 47 — Movie Producer (Automated Video Production)
# LINUX / VPS CONTAINER IMAGE for the headless-Chromium render paths.
#
# WHY: the upstream OpenMontage `make setup` installs NO Chromium system libraries and
# pre-stages NO Piper voice model, so a fresh Linux container FAILS every Remotion /
# HyperFrames render and often has no offline Piper TTS (see OPENMONTAGE-VPS-READINESS).
# This image bakes in exactly the missing pieces so the animated-render paths work on a
# VPS the same way they already work on the operator's Mac.
#
# BASE: node:22-bookworm-slim — Node 22 is required by HyperFrames (engines: node>=22)
#       and is Remotion's own recommended Docker base.
#       Source: https://www.remotion.dev/docs/docker
#
# BUILD (context = this skill directory):
#     docker build -t openmontage-skill47 47-movie-producer/
# RUN (client's OWN Kie key injected at runtime — NEVER baked into the image):
#     docker run --rm -e KIE_API_KEY=... -v "$PWD/out:/work/out" openmontage-skill47 \
#       bash -lc 'cd $OPENCLAW_OPENMONTAGE_DIR && make demo'
#
# Bump the pinned versions via the ARGs below (they mirror provision-render-deps.sh).
FROM node:22-bookworm-slim

# ── Pinned latest-stable versions (each cites its source in provision-render-deps.sh) ──
ARG REMOTION_VERSION=4.0.489
ARG HYPERFRAMES_VERSION=0.7.56
ARG PIPER_VERSION=1.4.2
ARG PIPER_DEFAULT_VOICE=en_US-lessac-medium
# Upstream OpenMontage engine (AGPLv3) + the SHA install.sh pins.
ARG OPENMONTAGE_REPO=https://github.com/calesthio/OpenMontage.git
ARG OPENMONTAGE_SHA=ce11f6a24f5c92e97d1461ffe1cd7a238dda1417

ENV DEBIAN_FRONTEND=noninteractive \
    OPENCLAW_OPENMONTAGE_DIR=/opt/openmontage/OpenMontage \
    REMOTION_VERSION=${REMOTION_VERSION} \
    HYPERFRAMES_VERSION=${HYPERFRAMES_VERSION} \
    PIPER_VERSION=${PIPER_VERSION} \
    PIPER_DEFAULT_VOICE=${PIPER_DEFAULT_VOICE} \
    PIPER_DATA_DIR=/root/.piper/models

# ── 1. System deps: Chromium runtime libraries + ffmpeg + Python + git ─────────────────
# The Chromium library set is Remotion's documented Debian prerequisite (the SAME libs
# HyperFrames' bundled Chrome needs to launch). fonts-liberation covers text rendering.
# Source: https://www.remotion.dev/docs/docker  +  .../miscellaneous/linux-dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git make \
      python3 python3-pip python3-venv \
      ffmpeg \
      libnss3 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libgbm-dev \
      libxrandr2 libxkbcommon-dev libxfixes3 libxcomposite1 libxdamage1 \
      libpango-1.0-0 libcairo2 libcups2 libasound2 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# ── 2. Clone the upstream OpenMontage engine at the pinned SHA (AGPLv3 stays here) ─────
RUN mkdir -p /opt/openmontage \
    && git clone "${OPENMONTAGE_REPO}" "${OPENCLAW_OPENMONTAGE_DIR}" \
    && git -C "${OPENCLAW_OPENMONTAGE_DIR}" fetch --quiet origin "${OPENMONTAGE_SHA}" \
    && git -C "${OPENCLAW_OPENMONTAGE_DIR}" checkout --quiet "${OPENMONTAGE_SHA}"

# ── 3. make setup — upstream deps (pip requirements, Remotion npm, HyperFrames warm) ──
RUN cd "${OPENCLAW_OPENMONTAGE_DIR}" && make setup

# ── 4. Skill provisioner: pin Remotion + compositor + Chrome-Headless-Shell, HyperFrames
#      bundled Chrome, Piper (fail-loud) + a pre-staged voice model. apt libs already
#      baked in layer 1, so skip the apt step here. ─────────────────────────────────────
COPY provision-render-deps.sh /opt/skill47/provision-render-deps.sh
COPY kie-adapters /opt/skill47/kie-adapters
RUN cp /opt/skill47/kie-adapters/tools/graphics/kie_image.py "${OPENCLAW_OPENMONTAGE_DIR}/tools/graphics/kie_image.py" \
    && cp /opt/skill47/kie-adapters/tools/video/kie_video.py "${OPENCLAW_OPENMONTAGE_DIR}/tools/video/kie_video.py" \
    && SKILL47_SKIP_APT=1 bash /opt/skill47/provision-render-deps.sh

# ── 5. Client .env with a placeholder ONLY. The real KIE_API_KEY is the CLIENT'S own key
#      and is injected at RUNTIME (docker run -e KIE_API_KEY=... or a mounted .env). It is
#      NEVER baked into the image. Absent key => the free documentary-montage path runs. ─
RUN printf '%s\n' \
      '# Kie.AI API key — CLIENT OWN KEY ONLY. Inject at runtime; never bake it in.' \
      'KIE_API_KEY=YOUR_CLIENT_KIE_API_KEY_HERE' \
      > "${OPENCLAW_OPENMONTAGE_DIR}/.env"

WORKDIR /work

# NOTE (root-in-container Chrome): Remotion's Chrome-Headless-Shell renders fine as root
# (matching Remotion's official Docker image). HyperFrames drives its own bundled Chrome;
# if a render fails to launch Chrome as root, run the container as a non-root user or pass
# the renderer's --no-sandbox option (see OPENMONTAGE-VPS-READINESS). The free ffmpeg
# documentary-montage path and the Kie.AI remote path need no browser at all.
CMD ["bash"]
