#!/usr/bin/env python3
"""Read-only KIE recordInfo probe. Never prints or stores the API key."""
import json
import os
import re
import sys
import urllib.request

CANDIDATES = [
    os.path.expanduser("~/.openclaw/secrets/.env"),
    os.path.expanduser("~/.openclaw/.env"),
]
API = "https://api.kie.ai"
TASK = sys.argv[1] if len(sys.argv) > 1 else ""
OUT = sys.argv[2] if len(sys.argv) > 2 else ""


def key():
    for p in CANDIDATES:
        if not os.path.isfile(p):
            continue
        for line in open(p, encoding="utf-8", errors="replace"):
            m = re.match(r"\s*KIE_API_KEY\s*=\s*(.*)$", line)
            if m:
                v = m.group(1).strip().strip('"').strip("'")
                if v and not v.startswith("$"):
                    return v
    return None


def main():
    k = key()
    if not k:
        print("KIE_API_KEY not found", file=sys.stderr)
        return 2
    if not TASK:
        return 2
    req = urllib.request.Request(
        "%s/api/v1/jobs/recordInfo?taskId=%s" % (API, urllib.parse.quote(TASK)),
        headers={"Authorization": "Bearer %s" % k,
                 "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.loads(r.read().decode("utf-8"))
    # never persist the key; it never appears in this payload anyway
    txt = json.dumps(body, indent=1, sort_keys=True, default=str)
    if k and k in txt:
        txt = txt.replace(k, "***REDACTED***")
    if OUT:
        open(OUT, "w", encoding="utf-8").write(txt)
    print("keys", sorted(body) if isinstance(body, dict) else type(body).__name__)
    d = body.get("data") if isinstance(body, dict) else None
    if isinstance(d, dict):
        print("data keys", sorted(d))
        resp = d.get("response")
        if isinstance(resp, str):
            try:
                resp = json.loads(resp)
            except ValueError:
                pass
        if isinstance(resp, dict):
            print("response keys", sorted(resp))
            for kk in ("tags", "duration", "title", "lyrics", "model_name",
                       "audioUrl", "audio_url", "streamAudioUrl"):
                if kk in resp:
                    print(kk, "=", repr(resp[kk])[:300])
    return 0


if __name__ == "__main__":
    import urllib.parse
    sys.exit(main())
