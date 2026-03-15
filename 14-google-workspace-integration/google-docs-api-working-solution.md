## 🔴🔴🔴 GOOGLE DOCS API - EXACT WORKING SOLUTION (Added 2026-02-28 - PERMANENT)

**WHY 401s HAPPEN:** Every fresh session I guess at which scope to request. I kept guessing `documents.readonly` alone. That scope is NOT in the DWD list. The working scope is `drive + documents` TOGETHER. NEVER guess - always use the exact scopes below.

**🔴 `documents` = READ + WRITE. Not read-only. Full access. This is the write scope.**
- `documents.readonly` = read only (do NOT use alone, will 401 if not in DWD)
- `documents` = full read AND write to Google Docs (THIS IS WHAT WE NEED)
- Same pattern for drive, calendar, gmail, spreadsheets

**COMPLETE DWD SCOPE LIST (all 10 must be in admin.google.com DWD for clawdbot@n8nbceo.iam.gserviceaccount.com):**
```
https://www.googleapis.com/auth/documents
https://www.googleapis.com/auth/documents.readonly
https://www.googleapis.com/auth/drive
https://www.googleapis.com/auth/drive.readonly
https://www.googleapis.com/auth/calendar
https://www.googleapis.com/auth/calendar.readonly
https://www.googleapis.com/auth/gmail.modify
https://www.googleapis.com/auth/gmail.readonly
https://www.googleapis.com/auth/spreadsheets
https://www.googleapis.com/auth/spreadsheets.readonly
```
**Where to set DWD:** admin.google.com > Security > Access and data control > API controls > Manage Domain Wide Delegation

**THE EXACT WORKING CODE:**
```python
import json, time, base64, requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

import os
# SA key path: use environment variable if set, otherwise fall back to standard location
# Set GCP_SA_KEY_PATH in your env or ~/clawd/secrets/.env to override
SA_PATH = os.environ.get(
    "GCP_SA_KEY_PATH",
    os.path.expanduser("~/clawd/secrets/gcp-service-account.json")
)
SCOPE = "https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/documents"
# SUB: the Google Workspace user to impersonate via DWD
SUB = os.environ.get("GOOGLE_IMPERSONATE_EMAIL", "trevor@blackceo.com")

with open(SA_PATH) as f: sa = json.load(f)
def b64url(d):
    if isinstance(d, str): d = d.encode()
    return base64.urlsafe_b64encode(d).rstrip(b'=').decode()
now = int(time.time())
h = b64url(json.dumps({"alg":"RS256","typ":"JWT"}))
p = b64url(json.dumps({"iss":sa["client_email"],"sub":SUB,"scope":SCOPE,"aud":"https://oauth2.googleapis.com/token","iat":now,"exp":now+3600}))
si = f"{h}.{p}"
pk = serialization.load_pem_private_key(sa["private_key"].encode(), password=None)
sig = pk.sign(si.encode(), padding.PKCS1v15(), hashes.SHA256())
jwt = f"{si}.{b64url(sig)}"
token = requests.post("https://oauth2.googleapis.com/token",
    data={"grant_type":"urn:ietf:params:oauth:grant-type:jwt-bearer","assertion":jwt},
    timeout=10).json()["access_token"]

doc = requests.get(f"https://docs.googleapis.com/v1/documents/{DOC_ID}?includeTabsContent=true",
    headers={"Authorization": f"Bearer {token}"}, timeout=120).json()
```

**RULES - NON-NEGOTIABLE:**
- SA key: `~/clawd/secrets/gcp-service-account.json` (standard location — override with `GCP_SA_KEY_PATH` env var if needed)
- Scope: `drive + documents` TOGETHER. Never just documents alone. Never just drive alone.
- Library: `requests` NOT `urllib`. urllib times out on large docs (42MB+).
- Timeout: 120 seconds minimum for multi-tab docs.
- Sub: `trevor@blackceo.com` for Workspace docs.
- BROWSER: BANNED. Zero exceptions. Zero tolerance. This rule has been broken 2+ times Feb 2026.
- If I get a 401: CHECK THE SCOPE FIRST. It's almost always the scope.
