#!/usr/bin/env python3
"""ghl-client-emails.py - READ-ONLY GoHighLevel (Convert and Flow) lookup of one
client's email addresses, for ensure-cc-access.sh. Python 3 standard library only.

  printf '%s' '{"slug":"eddie-otts-trading","seeds":["a@x"],"operator":["op@y"],"location_id":"<id>"}' \
    | python3 -I ghl-client-emails.py

stdin  JSON: slug (the Command Center host's first label), seeds (verified client
       emails already known: the emails file and the client's own Access pages),
       operator (operator emails, never returned), location_id (the Black CEO LLC
       location; empty = not configured).
stdout JSON: {"status": S, "emails": [...], "contacts": N}
       S = ok (emails found) | none (configured, no match) | ambiguous (more than one
       person matched: nothing returned) | skipped (no token or no location id) |
       error (an API call failed or results were truncated: nothing returned).
Nothing is ever written to stderr except a status word. Emails go only to stdout,
for the caller to count; the caller never prints them. The token is never printed.

TOKEN: GOHIGHLEVEL_API_KEY parsed (never sourced) from COUNCIL_GHL_ENV_FILE when set,
       else $HOME/.openclaw/secrets/.env, then $HOME/.openclaw/.env.
API:   COUNCIL_GHL_API_BASE (default https://services.leadconnectorhq.com), headers
       Authorization: Bearer, Version: 2021-07-28 and a curl-style User-Agent (the
       Python default is blocked by Cloudflare, error 1010). GET only.

MATCHING (strict: a wrong match lets a stranger into a client's dashboard). A
contact is the client ONLY when (i) its email or additionalEmails contains a seed
email, or (ii) its companyName equals the slug read as a business name (hyphens to
spaces, lowercased, punctuation dropped), exactly or after dropping the words
the/inc/llc/enterprises/consulting on both sides; never when that leaves the slug
one word (a first name such as "ann") or when the company is just the contact's
own full name. Then add that contact's emails,
plus the emails of any other contact with the SAME full name AND the SAME phone.
Never first name alone, never full name alone, no fuzzy matching. Matched contacts
with two different full names or two different phones, or a nameless contact among
two or more matches = ambiguous. Plus-addresses,
blackceo.com addresses (unless already a seed), operator, malformed and pending+
addresses are never returned.
"""
import json, os, re, sys, time
import urllib.error, urllib.parse, urllib.request

API = os.environ.get("COUNCIL_GHL_API_BASE", "https://services.leadconnectorhq.com").rstrip("/")
UA = "curl/8.7.1"
LIMIT = 20
MAX_PAGES = 10          # ponytail: 200 contacts per query; more = truncated = error, raise if a real query needs it
STOP = {"the", "inc", "llc", "enterprises", "consulting"}
EMAIL_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$")


class Fail(Exception):
    pass


def env_value(path, key):
    """Last KEY=value in an env file, quotes stripped. Parsed, never executed."""
    val = ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"^\s*(?:export\s+)?" + re.escape(key) + r"=(.*)$", line.rstrip("\r\n"))
                if m:
                    val = m.group(1).strip()
    except OSError:
        return ""
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
        val = val[1:-1]
    return val


def token():
    files = [os.environ["COUNCIL_GHL_ENV_FILE"]] if os.environ.get("COUNCIL_GHL_ENV_FILE") else [
        os.path.expanduser("~/.openclaw/secrets/.env"), os.path.expanduser("~/.openclaw/.env")]
    for p in files:
        v = env_value(p, "GOHIGHLEVEL_API_KEY")
        if v:
            return v
    return ""


def clean(e):
    e = (e or "").strip().lower() if isinstance(e, str) else ""
    return e if EMAIL_RE.match(e) else ""


def norm(s):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split())


def strip_words(s):
    return " ".join(w for w in s.split() if w not in STOP)


def company_match(company, slug_name, person=""):
    """The company IS the slug read as a business name. Refused when the slug is one
    word once the/inc/llc/... are dropped (slugs are often a first name: "ann") and
    when the company is only the contact's own full name (a name match, not a business)."""
    c = norm(company)
    a, b = strip_words(c), strip_words(slug_name or "")
    if not c or len(b.split()) < 2 or not a or a == person:
        return False
    return c == slug_name or a == b


def full_name(c):
    return norm("%s %s" % (c.get("firstName") or "", c.get("lastName") or ""))


def phone(c):
    d = re.sub(r"\D", "", c.get("phone") or "")
    return d[1:] if len(d) == 11 and d.startswith("1") else d   # ponytail: US +1 only


def emails_of(c):
    out = [c.get("email")]
    for x in c.get("additionalEmails") or []:
        out.append(x.get("email") if isinstance(x, dict) else x)
    return [e for e in (clean(x) for x in out) if e]


class GHL:
    def __init__(self, tok, loc):
        self.tok, self.loc = tok, loc

    def get(self, params):
        url = API + "/contacts/?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + self.tok, "Version": "2021-07-28",
            "Accept": "application/json", "User-Agent": UA})
        for attempt in (1, 2):
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    d = json.loads(r.read().decode("utf-8") or "{}")
                if not isinstance(d, dict):
                    raise Fail("bad body")
                return d
            except urllib.error.HTTPError as e:
                if attempt == 1 and (e.code == 429 or e.code >= 500):
                    time.sleep(1)
                    continue
                raise Fail("http %d" % e.code)
            except (urllib.error.URLError, OSError, ValueError):
                if attempt == 1:
                    time.sleep(1)
                    continue
                raise Fail("network")
        raise Fail("unreachable")

    def search(self, text):
        found, seen = [], set()
        for pg in range(1, MAX_PAGES + 1):
            d = self.get({"locationId": self.loc, "query": text, "limit": LIMIT, "page": pg})
            batch = [c for c in (d.get("contacts") or []) if isinstance(c, dict) and c.get("id")]
            new = [c for c in batch if c["id"] not in seen]
            for c in new:
                seen.add(c["id"])
                found.append(c)
            total = (d.get("meta") or {}).get("total")
            if len(batch) < LIMIT or not new or (isinstance(total, int) and len(found) >= total):
                return found
        raise Fail("truncated")


def lookup(req, api):
    seeds = sorted({e for e in (clean(x) for x in req.get("seeds") or []) if e})
    ops = {e for e in (clean(x) for x in req.get("operator") or []) if e}
    slug_name = norm((req.get("slug") or "").replace("-", " "))
    matched = {}
    for s in seeds:
        for c in api.search(s):
            if s in emails_of(c):
                matched[c["id"]] = c
    if slug_name:
        for c in api.search(slug_name):
            if company_match(c.get("companyName"), slug_name, full_name(c)):
                matched[c["id"]] = c
    if not matched:
        return "none", [], 0
    names = {full_name(c) for c in matched.values()} - {""}
    phones = {phone(c) for c in matched.values()} - {""}
    # a nameless contact next to another match cannot be shown to be the same person
    nameless = len(matched) > 1 and any(not full_name(c) for c in matched.values())
    if len(names) > 1 or len(phones) > 1 or nameless:
        return "ambiguous", [], len(matched)
    people = dict(matched)
    for c in list(matched.values()):
        n, p = full_name(c), phone(c)
        if not n or not p:
            continue
        for d in api.search(n):
            if full_name(d) == n and phone(d) == p:
                people[d["id"]] = d
    out = set()
    for c in people.values():
        for e in emails_of(c):
            local, _, dom = e.partition("@")
            if "+" in local or e in ops or e in seeds:
                continue
            if dom == "blackceo.com" or dom.endswith(".blackceo.com"):
                continue
            out.add(e)
    return ("ok" if out else "none"), sorted(out), len(people)


def main():
    try:
        req = json.loads(sys.stdin.read() or "{}")
        if not isinstance(req, dict):
            raise ValueError
    except ValueError:
        req = {}
    loc = str(req.get("location_id") or "").strip()
    tok = token() if re.match(r"^[A-Za-z0-9_-]{4,64}$", loc) else ""
    if not tok:
        status, emails, n = "skipped", [], 0
    else:
        try:
            status, emails, n = lookup(req, GHL(tok, loc))
        except Exception:   # any failure: fail closed, nothing returned, nothing printed
            status, emails, n = "error", [], 0
    print(json.dumps({"status": status, "emails": emails, "contacts": n}))


if __name__ == "__main__":
    main()
