# GHL Media Library — Upload Reference (Tier 3)

Carved from the proven skill 28/35/37 implementations. This is the authoritative
Tier-3 media upload reference. The Convert and Flow CLI (Tier 0, skill 44) has NO
media commands — media uploads ALWAYS route to Tier 3 (this endpoint).

---

## 1. Endpoint

```
POST https://services.leadconnectorhq.com/medias/upload-file
```

## 2. Authentication

Use the **LOCATION PIT** (Private Integration Token scoped to the location), NOT
an agency-level PIT. An agency PIT returns `401` for media operations.

```
Authorization: Bearer <LOCATION_PIT>
```

The location PIT is stored at `~/.openclaw/secrets/.env` as `GOHIGHLEVEL_API_KEY`
(or the legacy alias `GHL_PRIVATE_INTEGRATION_TOKEN` accepted by skill 38's
self-test).

## 3. Required Headers

```
Version: 2021-07-28
Content-Type: multipart/form-data   (set automatically by curl -F)
```

## 4. Multipart Form Fields

| Field | Required | Notes |
|---|---|---|
| `file` | YES | `@/path/to/file` — the binary payload |
| `locationId` | YES | The GHL location ID (`GOHIGHLEVEL_LOCATION_ID`) |
| `name` | YES | Display name in the media library |
| `hosted` | YES | Set to `false` (boolean string) |
| `parentId` | NO | Folder ID (see caveat below). Omit to upload to media root. |

### Folder caveat (verified skill 37 lines 26-29)

Creating a folder via API returns `404` — the API endpoint for folder creation is
broken. A folder MUST be pre-created in the GHL UI and its ID passed as `parentId`.
Omitting `parentId` uploads to the media root — files are fully shareable from there.
Do NOT attempt to create a folder programmatically; surface the caveat and upload to
the root if no folder ID is available.

## 5. Working curl Block

```bash
# Source credentials
source ~/.openclaw/secrets/.env

# Set variables
FILE_PATH="/path/to/image.jpg"
DISPLAY_NAME="Campaign Hero Image"
PARENT_ID=""   # optional folder ID, leave empty for media root

curl -sS -X POST \
  "https://services.leadconnectorhq.com/medias/upload-file" \
  -H "Authorization: Bearer ${GOHIGHLEVEL_API_KEY}" \
  -H "Version: 2021-07-28" \
  -F "file=@${FILE_PATH}" \
  -F "locationId=${GOHIGHLEVEL_LOCATION_ID}" \
  -F "name=${DISPLAY_NAME}" \
  -F "hosted=false" \
  ${PARENT_ID:+-F "parentId=${PARENT_ID}"}
```

## 6. Response + CDN URL Format

A successful upload returns:

```json
{
  "fileId": "abc123...",
  "url": "https://<CDN_HOST>/..."
}
```

### TRUST the `url` field

The `url` field is the authoritative public URL returned by the API. It is openable
without a GHL login. The CDN host **varies by account and era** — do NOT hardcode
or assert a specific host. Both of these forms are valid:

| Form | Host | Source |
|---|---|---|
| Current CDN form | `https://assets.cdn.filesafe.space/[LOCATION_ID]/media/[filename]` | skill 35, skill 28 |
| GCS form (some accounts) | `https://storage.googleapis.com/msgsndr/...` | skill 37 |

**Criterion 18 note:** when testing, assert `url` is non-empty and openable — do
NOT hardcode a host comparison.

## 7. Required Scopes

`medias.write` (for uploads)
`medias.readonly` (for retrieval/listing)

## 8. Pre-Upload Verification

Verify the LOCATION PIT works before uploading:

```bash
curl -sS -o /dev/null -w "%{http_code}" \
  "https://services.leadconnectorhq.com/locations/${GOHIGHLEVEL_LOCATION_ID}" \
  -H "Authorization: Bearer ${GOHIGHLEVEL_API_KEY}" \
  -H "Version: 2021-07-28"
# Should return 200
```

If this returns 401, the PIT is an agency-level token — switch to the location PIT.

## 9. Retry Pattern

On a missing `fileId` in the response, surface the error and retry ONCE:

```bash
RESPONSE=$(curl -sS -X POST ... # upload call above)
FILE_ID=$(echo "$RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('fileId',''))" 2>/dev/null || echo "")
FILE_URL=$(echo "$RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('url',''))" 2>/dev/null || echo "")

if [ -z "$FILE_ID" ]; then
  echo "Upload returned no fileId — retrying once..."
  RESPONSE=$(curl -sS -X POST ... # retry)
  FILE_ID=$(echo "$RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('fileId',''))" 2>/dev/null || echo "")
  FILE_URL=$(echo "$RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('url',''))" 2>/dev/null || echo "")
fi

if [ -z "$FILE_ID" ]; then
  echo "ERROR: Media upload failed after retry. Response: $RESPONSE"
  exit 1
fi
echo "Upload successful: fileId=$FILE_ID url=$FILE_URL"
```

The imgBB fallback (documented in skill 28) is an out-of-band alternative for
non-GHL clients — it is NOT part of the GHL endpoint contract.

## 10. Sources

- skill 37 (`scripts/upload-ghl-media.sh`) — canonical, most complete implementation
- skill 35 (`SKILL.md` lines 142-149) — CDN URL format documentation
- skill 28 (`SKILL.md` lines 618-627) — CDN URL format + imgBB fallback note
