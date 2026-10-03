# Pre-production 01: Studio setup

Do this once per machine before the first video, and re-check it whenever a run behaves oddly.

## 1. Toolchain check

Confirm each of these is installed. Install only what is missing:

- Node 22 or newer, with the `playwright-core` package available to the skill's scripts.
- A headless Chromium that playwright-core can launch.
- FFmpeg and ffprobe on the PATH.
- Python 3 with numpy (needed by the sound synthesis scripts).

On the Mac, the motion-videos root is `~/Downloads/openclaw-master-files/motion-videos/`. On a Docker VPS it is a persistent volume such as `/data/motion-videos`, never ephemeral container storage.

## 2. Secrets check

- `FISH_AUDIO_API_KEY` must be set in the environment at voiceover time. The skill never stores keys in files.
- A Fish Audio voice reference id for the brand's voice.

## 3. House rules on file

Read `02-house-rules.md` next and keep it open for the whole run. Every later chapter assumes it.
