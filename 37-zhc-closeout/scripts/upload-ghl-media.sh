#!/usr/bin/env bash
# upload-ghl-media.sh -- conditional GHL media-library upload for ZHC Closeout.
#
# If (and only if) the client has the GHL / Convert-and-Flow skill installed AND
# a working LOCATION-scoped Private Integration Token (PIT), this uploads the
# closeout media (the two infographics + the celebration video) into the client's
# Convert and Flow / GHL media library via POST /medias/upload-file
# (Version: 2021-07-28) and captures each file's REAL, publicly-shareable URL so
# the Telegram closeout can post an OPENABLE LINK per artifact (not "saved in a
# folder").
#
# Skips gracefully -- exits 0 with a log line -- when GHL is absent or the PIT
# does not resolve / verify. Never blocks closeout.
#
# IDEMPOTENT + RETRIED: re-running on a resume is a no-op once .ghlMediaUploaded
# is true (no duplicate media-library entries / no orphaned URLs), and each
# per-file upload POST is retried up to GHL_UPLOAD_MAX_ATTEMPTS with exponential
# backoff so a transient 5xx/429/network blip no longer silently drops the
# durable GHL link (knobs: ZHC_GHL_UPLOAD_MAX_ATTEMPTS / ZHC_GHL_UPLOAD_RETRY_BACKOFF_BASE).
#
# CONVENTIONS (verified against ~/clawd/TOOLS.md "Convert and Flow (GHL)" +
# docs: marketplace.gohighlevel.com/docs/ghl/medias/upload-media-content):
#   - Auth: Authorization: Bearer <LOCATION PIT>   (PIT, not a deprecated key)
#   - ENV: canonical names are GOHIGHLEVEL_API_KEY + GOHIGHLEVEL_LOCATION_ID
#          (the closeout also accepts the legacy aliases GHL_API_KEY /
#          GHL_LOCATION_ID so an older box still works). Media uploads REQUIRE
#          the LOCATION PIT -- the Agency PIT returns 401 for media ops.
#   - Base:  https://services.leadconnectorhq.com
#   - Header: Version: 2021-07-28
#   - Upload form fields (per the official spec): file, locationId, hosted,
#     name, parentId (the FOLDER id -- the field is `parentId`, NOT `folderId`).
#   - FOLDER CREATION VIA API IS BROKEN (TOOLS.md ground truth): a folder must be
#     pre-created in the Convert and Flow UI and its id passed via
#     GHL_MEDIA_FOLDER_ID. We never POST a folder-create (it 404s). With no
#     folder id the files land in the media root (still fully shareable).
#   - Response: {"fileId":"...","url":"https://storage.googleapis.com/msgsndr/..."}
#     The `url` is a PUBLIC GCS object URL -- openable without a GHL login. That
#     public URL is what we surface to Telegram as the durable openable link.
#
# Only uploads REAL files that exist on disk (the *LocalPath state fields written
# by generate-infographics.sh / generate-celebration-video.sh). Never uploads a
# placeholder or a file:// URL string.

set -u

if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[ghl-media] no OpenClaw root found; skipping" >&2
  exit 0
fi

STATE_FILE="$OC_ROOT/workspace/.workforce-build-state.json"
LOG_FILE="$OC_ROOT/workspace/.zhc-closeout.log"
GHL_BASE="https://services.leadconnectorhq.com"
GHL_VERSION="2021-07-28"

log() { printf '%s [%-5s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" >> "$LOG_FILE"; }
state_get() { jq -r "$1 // empty" "$STATE_FILE" 2>/dev/null; }
state_set() { local tmp; tmp=$(mktemp); jq "$1" "$STATE_FILE" > "$tmp" && mv "$tmp" "$STATE_FILE"; }
now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

if [[ ! -f "$STATE_FILE" ]]; then
  log "WARN" "ghl-media: no state file -- skipping"
  exit 0
fi

# ---- idempotency guard: never re-upload on a resume / re-fire ----
# run-closeout.sh Step 5.5 invokes this script on EVERY run/resume. If a prior
# run already uploaded successfully (.ghlMediaUploaded == true), re-running would
# create DUPLICATE media-library entries and mint fresh public URLs, orphaning
# the durable links already written to state + posted to Telegram. So skip
# cleanly once the upload is genuinely done. NOTE: only the boolean `true` is a
# success; the "skipped-*"/"failed-*" string markers are NOT, so an earlier skip
# or transient failure is still retried on the next resume.
if [[ "$(state_get '.ghlMediaUploaded')" == "true" ]]; then
  log "INFO" "ghl-media: .ghlMediaUploaded already true -- skipping (idempotent; not re-uploading)"
  exit 0
fi

# ---- detection: is GHL/Convert-and-Flow even installed for this client? ----
GHL_SKILL_PRESENT=0
for d in "$OC_ROOT/skills/29-ghl-convert-and-flow" "$OC_ROOT/skills/05-ghl-setup" "$OC_ROOT/skills/36-ghl-mcp-setup"; do
  [[ -d "$d" ]] && GHL_SKILL_PRESENT=1 && break
done

# ---- resolve the LOCATION PIT + location id ----
# Canonical env names (TOOLS.md): GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_LOCATION_ID.
# Legacy aliases still accepted so an older box keeps working: GHL_API_KEY /
# GHL_LOCATION_ID. A build-state .ghlLocationId (set at interview time) is the
# final fallback for the location id. The PIT MUST come from the environment.
GHL_PIT="${GOHIGHLEVEL_API_KEY:-${GHL_API_KEY:-}}"
GHL_LOC="${GOHIGHLEVEL_LOCATION_ID:-${GHL_LOCATION_ID:-}}"
[[ -z "$GHL_LOC" ]] && GHL_LOC="$(state_get '.ghlLocationId')"

# If there is no GHL presence signal at all (no skill AND no creds AND no
# location in state), this client simply has no GHL -- skip silently (not error).
if [[ "$GHL_SKILL_PRESENT" -eq 0 && -z "$GHL_PIT" && -z "$GHL_LOC" ]]; then
  log "INFO" "ghl-media: no GHL/Convert-and-Flow skill, PIT, or location -- skipping (client has no GHL; not an error)"
  state_set '.ghlMediaUploaded = "skipped-no-ghl"'
  exit 0
fi

if [[ -z "$GHL_PIT" || -z "$GHL_LOC" ]]; then
  log "INFO" "ghl-media: LOCATION PIT (GOHIGHLEVEL_API_KEY/GHL_API_KEY) and/or LOCATION id (GOHIGHLEVEL_LOCATION_ID/GHL_LOCATION_ID/.ghlLocationId) not both resolvable -- skipping (no working LOCATION PIT)"
  state_set '.ghlMediaUploaded = "skipped-no-pit"'
  exit 0
fi

if ! command -v curl >/dev/null 2>&1; then
  log "WARN" "ghl-media: curl not found -- skipping"
  exit 0
fi

# ---- verify the LOCATION PIT actually works before uploading ----
verify_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 \
  -H "Authorization: Bearer $GHL_PIT" \
  -H "Version: $GHL_VERSION" \
  "$GHL_BASE/locations/$GHL_LOC" 2>/dev/null || echo "000")
if [[ ! "$verify_code" =~ ^2 ]]; then
  log "WARN" "ghl-media: LOCATION PIT verify returned HTTP $verify_code -- skipping upload (PIT not working for this location)"
  state_set '.ghlMediaUploaded = "skipped-pit-verify-failed"'
  exit 0
fi
log "INFO" "ghl-media: LOCATION PIT verified (HTTP $verify_code) for location $GHL_LOC -- proceeding with uploads"

# ---- collect the real local media files written by the generators ----
# Each entry is "label|path" so we can attach a human-friendly name + map the
# returned public URL back to the right artifact in state for the Telegram step.
declare -a TO_UPLOAD=()
INF1_PATH="$(state_get '.infographic1LocalPath')"
INF2_PATH="$(state_get '.infographic2LocalPath')"
VIDEO_PATH="$(state_get '.celebrationVideoLocalPath')"
COMPANY_NAME="$(state_get '.companyName')"; [[ -z "$COMPANY_NAME" ]] && COMPANY_NAME="$(state_get '.companySlug')"
[[ -z "$COMPANY_NAME" ]] && COMPANY_NAME="ZHC"
[[ -n "$INF1_PATH"  && -s "$INF1_PATH"  ]] && TO_UPLOAD+=("infographic1|Workforce Structure|$INF1_PATH")
[[ -n "$INF2_PATH"  && -s "$INF2_PATH"  ]] && TO_UPLOAD+=("infographic2|How Work Flows|$INF2_PATH")
[[ -n "$VIDEO_PATH" && -s "$VIDEO_PATH" ]] && TO_UPLOAD+=("celebrationVideo|Celebration Video|$VIDEO_PATH")

if [[ ${#TO_UPLOAD[@]} -eq 0 ]]; then
  log "WARN" "ghl-media: no real local media files found to upload -- skipping"
  state_set '.ghlMediaUploaded = "skipped-no-files"'
  exit 0
fi

# ---- optional target folder ----
# Folder CREATE via API is broken (TOOLS.md). If the operator pre-created a
# "ZHC Closeout -- <Company>" folder in the UI and exported GHL_MEDIA_FOLDER_ID,
# we upload INTO it (field name is `parentId`); otherwise files land in the media
# root. Either way we capture each file's PUBLIC url for the Telegram closeout.
GHL_FOLDER_ID="${GHL_MEDIA_FOLDER_ID:-}"
[[ -n "$GHL_FOLDER_ID" ]] && log "INFO" "ghl-media: uploading into pre-created folder parentId=$GHL_FOLDER_ID"

# ---- upload retry / backoff knobs ----
# Each upload is a SINGLE multipart POST; a transient 5xx / 429 / network blip
# would otherwise silently drop the durable GHL link (best-effort, never blocks
# closeout). Retry up to N attempts with exponential backoff, mirroring
# wire-n8n-closeout.sh and generate-celebration-video.sh. The backoff base is
# overridable so the test harness can run with no real waits.
GHL_UPLOAD_MAX_ATTEMPTS="${ZHC_GHL_UPLOAD_MAX_ATTEMPTS:-3}"
GHL_UPLOAD_RETRY_BACKOFF_BASE="${ZHC_GHL_UPLOAD_RETRY_BACKOFF_BASE:-2}"

uploaded=0
declare -a UPLOADED_IDS=()
declare -a UPLOADED_URLS=()
# Per-artifact public URL fields written back to state so the Telegram step can
# post a real openable link for each one.
GHL_VIDEO_PUBLIC_URL=""
GHL_INF1_PUBLIC_URL=""
GHL_INF2_PUBLIC_URL=""

for entry in "${TO_UPLOAD[@]}"; do
  key="${entry%%|*}"; rest="${entry#*|}"; label="${rest%%|*}"; f="${rest#*|}"
  fname="$(basename "$f")"
  # A clean, human-readable media-library name: "<Company> -- <Label>.<ext>"
  ext="${fname##*.}"; [[ "$ext" == "$fname" ]] && ext=""
  nice_name="$COMPANY_NAME -- $label"; [[ -n "$ext" ]] && nice_name="$nice_name.$ext"
  _folder_arg=()
  # Documented folder field is `parentId` (NOT `folderId`).
  [[ -n "$GHL_FOLDER_ID" ]] && _folder_arg=(-F "parentId=$GHL_FOLDER_ID")

  # Retry the upload POST up to GHL_UPLOAD_MAX_ATTEMPTS with exponential backoff.
  # Break the instant a fileId comes back; a transient curl failure or a non-
  # fileId body (5xx/429) re-tries instead of silently dropping the durable link.
  file_id=""
  file_url=""
  resp=""
  attempt=0
  while (( attempt < GHL_UPLOAD_MAX_ATTEMPTS )); do
    attempt=$((attempt + 1))
    log "INFO" "ghl-media: uploading '$nice_name' ($fname) attempt $attempt/$GHL_UPLOAD_MAX_ATTEMPTS -> $GHL_BASE/medias/upload-file (location $GHL_LOC)"
    resp=$(curl -s --max-time 300 \
      -H "Authorization: Bearer $GHL_PIT" \
      -H "Version: $GHL_VERSION" \
      -F "file=@$f" \
      -F "locationId=$GHL_LOC" \
      -F "name=$nice_name" \
      -F "hosted=false" \
      "${_folder_arg[@]}" \
      "$GHL_BASE/medias/upload-file" 2>>"$LOG_FILE") || resp=""
    file_id=$(printf '%s' "$resp" | jq -r '.fileId // .id // empty' 2>/dev/null)
    file_url=$(printf '%s' "$resp" | jq -r '.url // .fileUrl // empty' 2>/dev/null)
    [[ -n "$file_id" ]] && break
    if (( attempt < GHL_UPLOAD_MAX_ATTEMPTS )); then
      _backoff=$(( GHL_UPLOAD_RETRY_BACKOFF_BASE ** attempt ))
      log "WARN" "ghl-media: upload of '$nice_name' attempt $attempt/$GHL_UPLOAD_MAX_ATTEMPTS returned no fileId (resp: $(printf '%s' "$resp" | head -c 200)) -- retrying in ${_backoff}s"
      sleep "$_backoff"
    fi
  done

  if [[ -n "$file_id" ]]; then
    uploaded=$((uploaded + 1))
    UPLOADED_IDS+=("$file_id")
    if [[ -n "$file_url" ]]; then
      UPLOADED_URLS+=("$file_url")
      case "$key" in
        celebrationVideo) GHL_VIDEO_PUBLIC_URL="$file_url" ;;
        infographic1)     GHL_INF1_PUBLIC_URL="$file_url" ;;
        infographic2)     GHL_INF2_PUBLIC_URL="$file_url" ;;
      esac
    fi
    log "INFO" "ghl-media: uploaded '$nice_name' -> fileId=$file_id publicUrl=${file_url:-<none>} (attempt $attempt/$GHL_UPLOAD_MAX_ATTEMPTS)"
  else
    log "WARN" "ghl-media: upload of '$nice_name' FAILED after $GHL_UPLOAD_MAX_ATTEMPTS attempts (last resp: $(printf '%s' "$resp" | head -c 200))"
  fi
done

if [[ "$uploaded" -gt 0 ]]; then
  ids_json=$(printf '%s\n' "${UPLOADED_IDS[@]}" | jq -R . | jq -s -c .)
  urls_json='[]'
  [[ ${#UPLOADED_URLS[@]} -gt 0 ]] && urls_json=$(printf '%s\n' "${UPLOADED_URLS[@]}" | jq -R . | jq -s -c .)
  # The in-app media-library link (folder deep-link if a folder id was provided,
  # else the media-storage root). NOTE: this app link is behind a GHL login, so
  # it is NOT the openable artifact link -- the PER-FILE PUBLIC urls above are.
  # We keep the app link as a "browse them all in your account" convenience.
  if [[ -n "$GHL_FOLDER_ID" ]]; then
    media_lib_url="https://app.gohighlevel.com/location/$GHL_LOC/media-storage?parentId=$GHL_FOLDER_ID"
  else
    media_lib_url="https://app.gohighlevel.com/location/$GHL_LOC/media-storage"
  fi
  state_set "
    .ghlMediaUploaded = true
    | .ghlMediaFileIds = $ids_json
    | .ghlMediaUrls = $urls_json
    | .ghlMediaLibraryUrl = \"$media_lib_url\"
    | .ghlVideoPublicUrl = \"$GHL_VIDEO_PUBLIC_URL\"
    | .ghlInfographic1PublicUrl = \"$GHL_INF1_PUBLIC_URL\"
    | .ghlInfographic2PublicUrl = \"$GHL_INF2_PUBLIC_URL\"
    | .ghlMediaUploadedAt = \"$(now_iso)\"
  "
  log "INFO" "ghl-media: done -- $uploaded/${#TO_UPLOAD[@]} files uploaded; per-file public URLs captured; media library link: $media_lib_url"
else
  state_set '.ghlMediaUploaded = "failed-no-files-accepted"'
  log "WARN" "ghl-media: no files accepted by GHL -- check PIT scope (medias.write)"
fi
exit 0
