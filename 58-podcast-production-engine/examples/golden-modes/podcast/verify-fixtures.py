#!/usr/bin/env python3
"""Golden-fixture regression verifier for the Podcast Production Engine (Skill 58).

Scope: this proves the COMMITTED golden fixtures have not drifted. It re-measures
the two episode scripts (Fish emotion tags stripped), re-runs the deterministic
Tier 1 mechanical checks, re-derives the pd- job keys from each canonical
submission, and asserts the committed manifests and certificates still match.

It is NOT the engine's canonical prover. The canonical deterministic Tier 1 prover
is qc-tier1-mechanical.py (Wave 2.4) and the semantic checks 12, 13, 14 run on the
cheap judge tier. This verifier only guards the fixtures against silent drift, the
way 57-social-media-in-a-box verify.sh step 2b guards its golden modes.

Exit 0 on all pass, non-zero on any drift. No em dashes, no triple-backtick fences.
"""
import os, re, json, hashlib, sys

HERE = os.path.dirname(os.path.abspath(__file__))
WPM = 140
# Built from code points so this detector file itself contains zero literal em
# dashes and zero literal triple-backtick fences (the bans are absolute).
BANNED_DASHES = [chr(0x2014), chr(0x2013), chr(0x2012), chr(0x2015), chr(0x2E3A), chr(0x2E3B)]
FENCE = chr(0x60) * 3

fails = []
def check(cond, msg):
    if not cond:
        fails.append(msg)

def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()

def sha_str(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def sha_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def strip_tags(t):
    return re.sub(r"\[[^\]]*\]", "", t)

def words(t):
    return len(re.findall(r"[A-Za-z']+", strip_tags(t)))

def canonical(fields):
    return json.dumps(fields, sort_keys=True, separators=(",", ":"))

def job_key(cid, canon):
    return "pd-" + cid + "-" + sha_str(canon)[:16]

def mechanical_tier1(name, raw, style):
    check(not any(d in raw for d in BANNED_DASHES), f"{name}: em dash present")
    check(FENCE not in raw, f"{name}: triple backtick present")
    check(re.search(r"[0-9]", raw) is None, f"{name}: numeral present (check 6 speakable)")
    check("*" not in raw and "__" not in raw, f"{name}: markdown emphasis present")
    check(raw.count("[") == raw.count("]"), f"{name}: unbalanced tag brackets")
    tags = re.findall(r"\[([^\]]*)\]", raw)
    check(all(re.fullmatch(r"[a-z]+", t) for t in tags), f"{name}: malformed emotion tag")
    check(re.search(r"(?mi)^\s*(HOST|GUEST|SPEAKER|NARRATOR|MUSIC|SFX|TITLE|INTRO|OUTRO)\s*:", raw) is None, f"{name}: label or stage direction present")
    check(re.search(r"(?i)\btitle\s*:", raw) is None, f"{name}: 'Title:' prefix present")
    if style == "counter_intuitive":
        check(re.search(r"(?i)\bparadox\b", raw) is None, f"{name}: forbidden word 'paradox' in Counter Intuitive episode")

# ---- episode fixtures ----
EPISODES = [
    {"dir": "personal", "style": "vulnerable", "contact": "cN7kQ2vDELIA0001"},
    {"dir": "interview", "style": "counter_intuitive", "contact": "cH3mR9tSASHA0002"},
]
for ep in EPISODES:
    d = os.path.join(HERE, ep["dir"])
    script = read(os.path.join(d, "delivery/episode-script.txt"))
    mechanical_tier1(ep["dir"], script, ep["style"])
    media = json.loads(read(os.path.join(d, "working/media/episode.json")))
    w = words(script)
    dur = round(w / WPM * 60)
    check(media["scriptWords"] == w, f"{ep['dir']}: scriptWords manifest {media['scriptWords']} != measured {w}")
    check(media["durationSeconds"] == dur, f"{ep['dir']}: durationSeconds manifest {media['durationSeconds']} != measured {dur}")
    check(media["scriptSha256"] == sha_file(os.path.join(d, "delivery/episode-script.txt")), f"{ep['dir']}: script sha drift")
    check(7 * 60 <= dur <= 15 * 60, f"{ep['dir']}: duration {dur}s outside 7 to 15 minute band")
    # rubric: every dimension at or above 8
    rub = json.loads(read(os.path.join(d, "working/qc/rubric.json")))
    check(all(v["score"] >= 8 for v in rub["dimensions"].values()), f"{ep['dir']}: a rubric dimension is below 8")
    check(len(rub["dimensions"]) == 10, f"{ep['dir']}: rubric does not have 10 dimensions")
    # tier1 manifest: all 16 pass
    t1 = json.loads(read(os.path.join(d, "working/qc/tier1.json")))
    check(len(t1["checks"]) == 16 and t1["allPass"] is True, f"{ep['dir']}: tier1 manifest not 16-all-pass")
    # job key derivation matches canonical payload
    payload = json.loads(read(os.path.join(d, "working/intake/canonical-payload.json")))
    derived = job_key(ep["contact"], canonical(payload["fields"]))
    check(payload["jobKey"] == derived, f"{ep['dir']}: job key drift, manifest {payload['jobKey']} != derived {derived}")
    # certificate script_words match
    cert = json.loads(read(os.path.join(d, "delivery/EPISODE-CERTIFICATE.json")))
    check(cert["script_words"] == w, f"{ep['dir']}: certificate script_words drift")
    check(cert["zero_anthropic"] is True, f"{ep['dir']}: certificate not zero_anthropic")
    check(cert["fish_audio"]["free_tier"] is False and cert["fish_audio"]["model"] == "s2.1-pro", f"{ep['dir']}: fish audio spec wrong")

# ---- interview book teaser ----
teaser = read(os.path.join(HERE, "interview/delivery/book-teaser.txt"))
check(not any(d in teaser for d in BANNED_DASHES), "teaser: em dash present")
check(FENCE not in teaser, "teaser: triple backtick present")

# ---- thin presets: certificates present and self-consistent ----
ss_cert = json.loads(read(os.path.join(HERE, "season-strategy/delivery/STRATEGY-CERTIFICATE.json")))
check(ss_cert["deliverable_sha256"] == sha_file(os.path.join(HERE, "season-strategy/delivery/season-strategy.md")), "season: doc sha drift")
check(ss_cert["render"] is False and ss_cert["publish"] is False, "season: should not render or publish")
ap_cert = json.loads(read(os.path.join(HERE, "asset-pack/delivery/ASSET-PACK-CERTIFICATE.json")))
check(ap_cert["idempotent_against_ledger"] is True, "asset-pack: not marked idempotent")
check("audio_render" in ap_cert["skipped_idempotent"] and "podbean_publish" in ap_cert["skipped_idempotent"], "asset-pack: did not skip audio or publish")

# ---- tree-wide dash and fence sweep ----
for root, _, fns in os.walk(HERE):
    for fn in fns:
        p = os.path.join(root, fn)
        if p == os.path.abspath(__file__):
            continue
        raw = read(p)
        check(not any(d in raw for d in BANNED_DASHES), f"{os.path.relpath(p, HERE)}: banned dash")
        check(FENCE not in raw, f"{os.path.relpath(p, HERE)}: triple backtick fence")

if fails:
    print("FIXTURE VERIFY FAILED:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("ALL GOLDEN FIXTURES VERIFIED: 2 episodes pass the deterministic Tier 1 checks and the 10-dimension rubric floor of 8; job keys re-derive; season-strategy and asset-pack certificates self-consistent; zero em dashes and zero fences tree-wide.")
sys.exit(0)
