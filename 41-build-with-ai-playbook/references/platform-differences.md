# Platform Differences -- Mac mini vs VPS (Docker) -- Skill 41

The Build With AI logic itself is identical on both platforms, because it is GHL-API-driven and
prompt-based: triggers, actions, filters, If/Else, dependency creation, and the generated prompt do
not change with the host. What differs is the filesystem layout and whether an interactive terminal
is available. The skill's scripts already branch on uname -s, so paths are handled automatically. The
items below are the operational differences the operator and the agent must know.

## Path layout (handled automatically by uname -s)

| Item | Mac mini (Darwin) | VPS (Linux, Docker) |
|---|---|---|
| OpenClaw home | $HOME/.openclaw | /data/.openclaw |
| Skills dir | $HOME/.openclaw/skills | /data/.openclaw/skills |
| Master files default | $HOME/Downloads/OpenClaw Master Files | /data/openclaw-master-files |
| Skill 41 pointer | $HOME/.openclaw/.skill-41-master-files-dir | $HOME/.openclaw/.skill-41-master-files-dir (resolves under /data in-container) |

## The real difference: interactive terminal

01-locate-master-files-folder.sh disambiguates multiple candidate folders and asks YES before creating
one. That requires a TTY.

- Mac mini: the operator is usually at the machine with an interactive Terminal, so the prompts work
  normally. Run the install scripts directly in Terminal.
- VPS (Docker): runs are frequently HEADLESS (no TTY). In that case 01-locate cannot prompt, and by
  design it will NOT create or guess silently. Before running it on a headless VPS, do one of:
  1. Export MASTER_FILES_DIR to the intended path, or
  2. Ensure Skill 38's pointer (.skill-38-master-files-dir) already exists so 01-locate reuses it.
  Run the scripts inside the container (for example via docker exec). If neither the env var nor the
  Skill 38 pointer is set and there is no TTY, 01-locate exits with guidance rather than choosing for you.

## Persistence (VPS only)

The pointer and the master files live under /data. Ensure the Docker /data volume is persistent so the
pointer and build-with-ai-events.jsonl survive container restarts. On Mac mini this is a normal home
directory and persists by default.

## Same on both platforms

- Mandatory binaries jq and curl (Homebrew on Mac, the image on VPS). 00-verify checks both.
- GHL credentials: GOHIGHLEVEL_API_KEY and GOHIGHLEVEL_LOCATION_ID via environment.
- The OpenClaw version check, the QC gates, the dependency-first rule, and the generated prompt format.
