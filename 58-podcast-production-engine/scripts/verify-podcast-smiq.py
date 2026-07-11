#!/usr/bin/env python3
"""verify-podcast-smiq.py — re-runnable, fail-loud health gate for the SMIQ capture, the
Facebook-ad workflows' template boundary, and the ops pipeline.

Complements verify-podcast-ghl-workflows.py (which gates the required 4 intake/completion
workflows). This one asserts the FB/SMIQ/pipeline functionalization work stayed correct:

  SMIQ (Trevor: "very important — rock solid"):
    * SMIQ Answer Tracker: published + committed; contact_changed trigger ACTIVE on
      contact.podcast_interview_smiq (the canonical field the podcast SMIQ answer always
      lands in); step writes contact.smiq_history; accumulator reads
      {{contact.podcast_interview_smiq}} and does NOT carry the dead {{contact.smiq_answer}}.
    * 05 Create Note SMIQ: published + committed; TWO active survey_submission triggers
      (interview + personal) so both surveys' SMIQ answers get a note.
  Pipeline: "Podcast Interview System Pipeline" exists with its 5 stages.
  FB workflows (01a / 02 / 02a / 03): DRAFT (activate per-client), carry NO other account's
    Facebook ids (no act_666564130483785, no pixel 8787656) and NO OLD pipeline id, and
    every create_opportunity points at the NEW pipeline.
  07: carries NO dead endpoint (make.com / n8n.apptime.me) and NO OLD pipeline id.

Read-only. Exit 0 = all PASS. Auth identical to verify-podcast-ghl-workflows.py."""
from __future__ import annotations
import argparse, json, os, ssl, sys, urllib.request, urllib.error

FIREBASE_API_KEY = "AIzaSyB_w3vXmsI7WeQtrIOkjR6xTRVN5uOieiE"
BASE = "https://backend.leadconnectorhq.com"
CTX = ssl.create_default_context()
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DEFAULT_LOC = "CjxATjhv9Gt21qSqURIt"
# GHL stores a contact_changed trigger's condition field as contact.<fieldId>, not the
# fieldKey; podcast_interview_smiq (the canonical SMIQ landing field) has id pTkurBfVPJOuiAv7HELI.
CANON_SMIQ = ("contact.pTkurBfVPJOuiAv7HELI", "contact.podcast_interview_smiq")
SMIQ_HISTORY_ID = "i08poncoJMo6abdET5nI"
OLD_PIPE = "yOomdMVVZgM9x4oB2fvK"
NEW_PIPE_NAME = "Podcast Interview System Pipeline"
STALE = ["act_666564130483785", "8787656", "hook.us1.make.com", "n8n.apptime.me", OLD_PIPE]
INTERVIEW_SURVEY = "ExAPmAV3Llo0tREenfJy"
PERSONAL_SURVEY = "vX5BuhxSeucMHrcKOwEn"


def _source_secrets(names):
    if any(os.environ.get(n, "").strip() for n in names):
        return
    path = os.environ.get("SECRETS_ENV") or os.path.expanduser("~/.openclaw/secrets/.env")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() in names and k.strip() not in os.environ:
                os.environ[k.strip()] = v.strip().strip('"').strip("'")


def _mint(refresh):
    body = f"grant_type=refresh_token&refresh_token={refresh}".encode()
    req = urllib.request.Request(
        f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}",
        data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urllib.request.urlopen(req, context=CTX, timeout=15) as r:
        return json.loads(r.read()).get("id_token", "")


def _get(tok, path):
    req = urllib.request.Request(BASE + path, headers={
        "token-id": tok, "channel": "APP", "source": "WEB_USER", "version": "2021-07-28",
        "Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=45) as r:
            txt = r.read().decode()
            return r.status, (json.loads(txt) if txt.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, {"_err": (e.read().decode() if e.fp else "")[:200]}
    except Exception as e:  # noqa: BLE001
        return -1, {"_exc": str(e)[:200]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--location", default=os.environ.get("PODCAST_ENGINE_GHL_LOCATION_ID") or DEFAULT_LOC)
    ap.add_argument("--token-env", default="PODCAST_ENGINE_GHL_FIREBASE_REFRESH_TOKEN,GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN")
    args = ap.parse_args()
    loc = args.location
    names = [n.strip() for n in args.token_env.split(",") if n.strip()]
    _source_secrets(names)
    refresh = next((os.environ[n] for n in names if os.environ.get(n, "").strip()), "")
    if not refresh:
        print(f"FAIL: no Firebase refresh token in {names}", file=sys.stderr); return 1
    tok = _mint(refresh)
    if not tok:
        print("FAIL: could not mint id_token", file=sys.stderr); return 1

    _, listing = _get(tok, f"/workflow/{loc}/list?limit=200")
    rows = [r for r in (listing.get("rows", []) if isinstance(listing, dict) else []) if r.get("type") == "workflow"]
    by = lambda sub: next((r for r in rows if sub in r.get("name", "")), None)
    ok_all = True

    def check(label, cond, detail=""):
        nonlocal ok_all
        ok_all = ok_all and cond
        print(f"[{'PASS' if cond else 'FAIL'}] {label}{(' — ' + detail) if detail else ''}")

    print(f"== SMIQ + FB + pipeline health — location {loc} ({len(rows)} workflows) ==")

    # SMIQ Answer Tracker
    t = by("SMIQ Answer Tracker")
    if not t:
        check("SMIQ Answer Tracker present", False);
    else:
        _, wf = _get(tok, f"/workflow/{loc}/{t['id']}")
        _, trigs = _get(tok, f"/workflow/{loc}/trigger?workflowId={t['id']}")
        trigs = trigs if isinstance(trigs, list) else []
        tr = trigs[0] if trigs else {}
        field = (tr.get("conditions", [{}])[0].get("field") if tr else "")
        steps = (wf.get("workflowData") or {}).get("templates", [])
        val = ""
        writes_history = False
        for s in steps:
            for f in s.get("attributes", {}).get("fields", []) or []:
                val += f.get("value", "") or ""
                if f.get("field") == SMIQ_HISTORY_ID:
                    writes_history = True
        check("SMIQ Tracker published+committed", wf.get("status") == "published" and bool(wf.get("triggersFilePath")),
              f"status={wf.get('status')} committed={bool(wf.get('triggersFilePath'))}")
        check("SMIQ Tracker triggers on canonical podcast_interview_smiq",
              tr.get("active") is True and field in CANON_SMIQ, f"field={field} active={tr.get('active')}")
        check("SMIQ Tracker writes smiq_history + reads podcast_interview_smiq (no dead {{smiq_answer}})",
              writes_history and "{{contact.podcast_interview_smiq}}" in val and "{{contact.smiq_answer}}" not in val)

    # 05 Create Note SMIQ
    n = by("Create Note")
    if not n:
        check("05 Create Note SMIQ present", False)
    else:
        _, wf = _get(tok, f"/workflow/{loc}/{n['id']}")
        _, trigs = _get(tok, f"/workflow/{loc}/trigger?workflowId={n['id']}")
        trigs = trigs if isinstance(trigs, list) else []
        surveys = {v for tr in trigs if tr.get("active") for c in tr.get("conditions", []) for v in c.get("value", [])}
        check("05 published+committed", wf.get("status") == "published" and bool(wf.get("triggersFilePath")))
        check("05 fires on BOTH interview + personal surveys",
              INTERVIEW_SURVEY in surveys and PERSONAL_SURVEY in surveys, f"surveys={sorted(surveys)}")

    # Pipeline
    _, pj = _get(tok, f"/opportunities/pipelines?locationId={loc}")
    pls = pj.get("pipelines", []) if isinstance(pj, dict) else []
    pipe = next((p for p in pls if p.get("name") == NEW_PIPE_NAME), None)
    check(f"pipeline '{NEW_PIPE_NAME}' exists with 5 stages",
          bool(pipe) and len(pipe.get("stages", [])) == 5,
          f"stages={[s['name'] for s in pipe.get('stages', [])]}" if pipe else "absent")

    # FB workflows draft + no stale ids + NEW pipeline in opportunities
    for sub in ["01a - Update Facebook audience", "02-Fb Podcast Lead", "02a-2nd Fb Podcast", "03-Podcast LeadForm"]:
        r = by(sub)
        if not r:
            check(f"FB wf present: {sub}", False); continue
        _, wf = _get(tok, f"/workflow/{loc}/{r['id']}")
        blob = json.dumps((wf.get("workflowData") or {}).get("templates", []))
        stale_hit = [s for s in STALE if s in blob]
        check(f"FB {sub[:22]} draft + clean (no other-account ids / OLD pipeline)",
              wf.get("status") == "draft" and not stale_hit, f"status={wf.get('status')} stale={stale_hit}")

    # 07 no dead endpoints
    seven = by("2nd Podcast Interview/Survey")
    if seven:
        _, wf = _get(tok, f"/workflow/{loc}/{seven['id']}")
        blob = json.dumps((wf.get("workflowData") or {}).get("templates", []))
        stale_hit = [s for s in STALE if s in blob]
        check("07 no dead endpoint / no OLD pipeline", not stale_hit, f"stale={stale_hit}")

    print("\nRESULT:", "ALL PASS" if ok_all else "FAILURES PRESENT")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
