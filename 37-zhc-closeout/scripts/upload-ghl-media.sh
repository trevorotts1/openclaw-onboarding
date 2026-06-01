#!/usr/bin/env bash
# upload-ghl-media.sh -- conditional GHL media-library upload for ZHC Closeout.
#
# If (and only if) the client has the GHL / Convert-and-Flow skill installed AND
# a working LOCATION-scoped Private Integration Token (PIT), this uploads the
# closeout media (the two infographics + the celebration video) into the client's
# GHL media library via POST /medias/upload-file (Version: 2021-07-28).
#
# Skips gracefully -- exits 0 with a log line -- when GHL is absent or the PIT
# does not resolve / verify. Never blocks closeout.
#
# CONVENTIONS (per Skill 29 GHL Convert-and-Flow INSTALL.md / TOOLS.md):
#   - Auth: Authorization: Bearer $GHL_API_KEY  (PIT, not deprecated API key)
#   - Scope: LOCATION PIT only -- requires $GHL_LOCATION_ID
#   - Base:  https://services.leadconnectorhq.com
#   - Header: Version: 2021-07-28
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

# ---- detection: is GHL/Convert-and-Flow even installed for this client? ----
GHL_SKILL_PRESENT=0
for d in "$OC_ROOT/skills/29-ghl-convert-and-flow" "$OC_ROOT/skills/05-ghl-setup" "$OC_ROOT/skills/36-ghl-mcp-setup"; do
  [[ -d "$d" ]] && GHL_SKILL_PRESENT=1 && break
done
if [[ "$GHL_SKILL_PRESENT" -eq 0 ]]; then
  log "INFO" "ghl-media: no GHL/Convert-and-Flow skill installed -- skipping (not an error)"
  state_set '.ghlMediaUploaded = "skipped-no-ghl-skill"'
  exit 0
fi

# ---- detection: do we have a LOCATION PIT + location id? ----
if [[ -z "${GHL_API_KEY:-}" || -z "${GHL_LOCATION_ID:-}" ]]; then
  log "INFO" "ghl-media: GHL_API_KEY / GHL_LOCATION_ID not both set -- skipping (no working LOCATION PIT)"
  state_set '.ghlMediaUploaded = "skipped-no-pit"'
  exit 0
fi

if ! command -v curl >/dev/null 2>&1; then
  log "WARN" "ghl-media: curl not found -- skipping"
  exit 0
fi

# ---- verify the LOCATION PIT actually works before uploading ----
verify_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: $GHL_VERSION" \
  "$GHL_BASE/locations/$GHL_LOCATION_ID" 2>/dev/null || echo "000")
if [[ ! "$verify_code" =~ ^2 ]]; then
  log "WARN" "ghl-media: LOCATION PIT verify returned HTTP $verify_code -- skipping upload (PIT not working for this location)"
  state_set '.ghlMediaUploaded = "skipped-pit-verify-failed"'
  exit 0
fi
log "INFO" "ghl-media: LOCATION PIT verified (HTTP $verify_code) -- proceeding with uploads"

# ---- collect the real local media files written by the generators ----
declare -a TO_UPLOAD=()
INF1_PATH="$(state_get '.infographic1LocalPath')"
INF2_PATH="$(state_get '.infographic2LocalPath')"
VIDEO_PATH="$(state_get '.celebrationVideoLocalPath')"
[[ -n "$INF1_PATH"  && -s "$INF1_PATH"  ]] && TO_UPLOAD+=("$INF1_PATH")
[[ -n "$INF2_PATH"  && -s "$INF2_PATH"  ]] && TO_UPLOAD+=("$INF2_PATH")
[[ -n "$VIDEO_PATH" && -s "$VIDEO_PATH" ]] && TO_UPLOAD+=("$VIDEO_PATH")

if [[ ${#TO_UPLOAD[@]} -eq 0 ]]; then
  log "WARN" "ghl-media: no real local media files found to upload -- skipping"
  state_set '.ghlMediaUploaded = "skipped-no-files"'
  exit 0
fi

# ---- optional target folder ----
# Per TOOLS.md ground truth: GHL media-FOLDER CREATION VIA API IS BROKEN — a
# folder must be created in the UI and its id passed as folderId on the upload.
# So we do NOT attempt to create a folder over the API (that would 404/no-op).
# If the operator pre-created a "ZHC Closeout — <Company>" folder in the UI and
# set GHL_MEDIA_FOLDER_ID, we upload INTO it; otherwise files land in the root
# media library (still fully shareable). Either way we capture the public URL of
# every uploaded file and surface a shareable link to the Telegram closeout.
GHL_FOLDER_ID="${GHL_MEDIA_FOLDER_ID:-}"
[[ -n "$GHL_FOLDER_ID" ]] && log "INFO" "ghl-media: uploading into pre-created folder id=$GHL_FOLDER_ID"

uploaded=0
declare -a UPLOADED_IDS=()
declare -a UPLOADED_URLS=()
for f in "${TO_UPLOAD[@]}"; do
  fname="$(basename "$f")"
  log "INFO" "ghl-media: uploading $fname -> $GHL_BASE/medias/upload-file (location $GHL_LOCATION_ID)"
  _folder_arg=()
  [[ -n "$GHL_FOLDER_ID" ]] && _folder_arg=(-F "folderId=$GHL_FOLDER_ID")
  resp=$(curl -s --max-time 120 \
    -H "Authorization: Bearer $GHL_API_KEY" \
    -H "Version: $GHL_VERSION" \
    -F "file=@$f" \
    -F "locationId=$GHL_LOCATION_ID" \
    -F "hosted=false" \
    "${_folder_arg[@]}" \
    "$GHL_BASE/medias/upload-file" 2>>"$LOG_FILE") || resp=""
  file_id=$(printf '%s' "$resp" | jq -r '.fileId // .id // empty' 2>/dev/null)
  file_url=$(printf '%s' "$resp" | jq -r '.url // empty' 2>/dev/null)
  if [[ -n "$file_id" ]]; then
    uploaded=$((uploaded + 1))
    UPLOADED_IDS+=("$file_id")
    [[ -n "$file_url" ]] && UPLOADED_URLS+=("$file_url")
    log "INFO" "ghl-media: uploaded $fname -> fileId=$file_id url=${file_url:-<none>}"
  else
    log "WARN" "ghl-media: upload of $fname did not return a fileId (resp: $(printf '%s' "$resp" | head -c 200))"
  fi
done

if [[ "$uploaded" -gt 0 ]]; then
  ids_json=$(printf '%s\n' "${UPLOADED_IDS[@]}" | jq -R . | jq -s -c .)
  urls_json='[]'
  [[ ${#UPLOADED_URLS[@]} -gt 0 ]] && urls_json=$(printf '%s\n' "${UPLOADED_URLS[@]}" | jq -R . | jq -s -c .)
  # Shareable media-library link the client can open in the Convert and Flow app.
  # (Folder deep-link if a folder id was provided, else the media-storage root.)
  if [[ -n "$GHL_FOLDER_ID" ]]; then
    media_lib_url="https://app.gohighlevel.com/location/$GHL_LOCATION_ID/media-storage?folderId=$GHL_FOLDER_ID"
  else
    media_lib_url="https://app.gohighlevel.com/location/$GHL_LOCATION_ID/media-storage"
  fi
  state_set ".ghlMediaUploaded = true | .ghlMediaFileIds = $ids_json | .ghlMediaUrls = $urls_json | .ghlMediaLibraryUrl = \"$media_lib_url\" | .ghlMediaUploadedAt = \"$(now_iso)\""
  log "INFO" "ghl-media: done -- $uploaded/${#TO_UPLOAD[@]} files uploaded; media library link: $media_lib_url"
else
  state_set '.ghlMediaUploaded = "failed-no-files-accepted"'
  log "WARN" "ghl-media: no files accepted by GHL -- check PIT scope (medias.write)"
fi
exit 0
