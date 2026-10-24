"""claims.py: claim provenance, research authoring, bundle validation.

S75-T04 (research authoring + source-to-owner-fact mapping). SPEC row 1 and
the foundation contract in SPEC.md §"Foundation and authoring contract":
every research claim carries where it came from, and no research artifact may
pass because it is merely non-empty or large.

Three provenance classes, no others:

  owner-fact   what the business owner said. Retains the raw answer identity
               (`owner_ref`) and is never presented as independently verified.
  public-fact  an independently sourced claim. Needs a source id that resolves
               to a recorded {url, retrieved} and may not assert the named
               client's own results, prices, guarantees or testimonials.
  fiction      proposed story content. Allowed and expected; labelled fiction
               can never be re-read as a real-business fact.

`validate_bundle` refuses an artifact whose claims carry no provenance tag and
refuses section bodies that hold only a brief echo. It never looks at byte
size — a 40 KB file of untagged keyword lists fails exactly like a 95-byte one.

Stdlib only, same as the rest of research_engine.
"""
from __future__ import annotations

import re

PROVENANCE = ("owner-fact", "public-fact", "fiction")
SECTIONS = ("market", "audience", "competitors")
PREMISE = "premise"
VALID_SECTIONS = SECTIONS + (PREMISE,)
BUNDLE_SCHEMA_VERSION = "blackceo.research.bundle/v1"

# Assertions about the named client's own commercial outcome. General market
# evidence cannot verify these, so they may only come from the owner (with the
# raw answer identity kept) or be explicitly fictional.
BUSINESS_RE = re.compile(
    r"(?:\$\s?\d"
    r"|\b\d{1,3}\s?%"
    r"|\bguarantee[ds]?\b|\bmoney[- ]back\b|\brisk[- ]free\b"
    r"|\bour\s+(?:clients?|customers?|students?|patients?)\b"
    r"|\bwe\s+(?:helped|increased|doubled|tripled|generated|earned|grew)\b"
    r"|\bnumber one\b|\b#1\b)",
    re.IGNORECASE)
TERMINATOR_RE = re.compile(r"[.!?][\"')\]]?\s*$")
TOKEN_RE = re.compile(r"[a-z0-9]{3,}")


def _nonempty(v):
    return isinstance(v, str) and bool(v.strip())


def _norm(text):
    return " ".join(str(text or "").split()).strip()


def _tokens(text):
    return set(TOKEN_RE.findall(str(text or "").lower()))


def _brief_claim_ids(brief):
    """Ids of claims the owner supplied in the brief — their raw answer
    identity even when the brief did not spell one out."""
    ids = set()
    for i, c in enumerate((brief or {}).get("claims") or []):
        if isinstance(c, dict) and _nonempty(c.get("id")):
            ids.add(c["id"].strip())
        elif isinstance(c, dict):
            ids.add("claim-%d" % (i + 1))
    return ids


def is_fiction_claim(claim):
    return isinstance(claim, dict) and claim.get("provenance") == "fiction"


def tag_claims(claims, brief=None, source_ids=None):
    """Attach a provenance tag to each claim. Returns (tagged, errors).

    This is the authoring step's job: an untagged claim that came with a
    citation becomes public-fact; an untagged claim the owner filed in the
    brief becomes owner-fact with its answer identity kept. An untagged claim
    from nowhere stays untagged and is returned as an error — the validator
    below refuses it rather than inventing an origin.
    """
    source_ids = set(source_ids or ())
    brief_ids = _brief_claim_ids(brief)
    tagged, errors = [], []
    for i, claim in enumerate(claims or []):
        if not isinstance(claim, dict):
            errors.append("claim %d: not an object" % (i + 1))
            tagged.append({"id": "claim-%d" % (i + 1), "text": str(claim),
                           "status": "PASS"})
            continue
        rec = dict(claim)
        rec.setdefault("id", "claim-%d" % (i + 1))
        prov = _norm(rec.get("provenance")).lower()
        if prov and prov not in PROVENANCE:
            errors.append("%s: provenance %r is not one of %s"
                          % (rec["id"], rec.get("provenance"), ", ".join(PROVENANCE)))
        elif not prov:
            src = _norm(rec.get("source"))
            if src and (not source_ids or src in source_ids):
                rec["provenance"] = "public-fact"
                rec["capture_date"] = rec.get("capture_date") or rec.get("retrieved")
            elif rec["id"] in brief_ids:
                rec["provenance"] = "owner-fact"
                rec["owner_ref"] = rec.get("owner_ref") or "brief-claim:%s" % rec["id"]
            # else: leave untagged — validate_bundle refuses it.
        tagged.append(rec)
    return tagged, errors


def _sections_for(claim):
    explicit = claim.get("sections")
    if isinstance(explicit, list) and explicit:
        return [s for s in explicit if s in VALID_SECTIONS]
    if is_fiction_claim(claim):
        return [PREMISE]
    return list(SECTIONS)


def _dedupe(tagged):
    """One record per distinct assertion. The same sentence filed by the owner
    and again by the gatherer is one claim with the better support attached —
    not two lines of padding. Ids are kept so lineage stays visible."""
    out, by_text = [], {}
    for claim in tagged:
        if not isinstance(claim, dict):
            out.append(claim)
            continue
        key = _norm(claim.get("text")).lower()
        first = by_text.get(key) if key else None
        if first is None:
            claim.setdefault("merged_ids", [])
            by_text[key] = claim
            out.append(claim)
            continue
        if not first.get("source") and claim.get("source"):
            first["source"] = claim["source"]
            first["provenance"] = claim.get("provenance", first.get("provenance"))
        if claim.get("owner_ref") and not first.get("owner_ref"):
            first["owner_ref"] = claim["owner_ref"]
        first["merged_ids"].append(claim.get("id"))
        for section in claim.get("sections") or []:
            if section not in first.setdefault("sections", []):
                first["sections"].append(section)
    return out


def author_bundle(brief, evidence):
    """Author the research_bundle for this run.

    Tags every claim, assigns it to the research sections it supports, keeps
    the owner's premise as explicitly fictional, and records the brief facts
    as owner statements. No network, no model call, no byte-size gate.
    """
    brief = brief or {}
    evidence = evidence or {}
    sources = evidence.get("sources") or []
    tagged, errors = tag_claims(evidence.get("claims") or brief.get("claims"),
                                brief, {s.get("id") for s in sources})
    premise = brief.get("premise")
    if premise:
        text = premise.get("text") if isinstance(premise, dict) else premise
        if _nonempty(text) and _norm(text).lower() not in {
                _norm(c.get("text")).lower() for c in tagged if isinstance(c, dict)}:
            tagged.append({"id": "premise-1", "text": _norm(text),
                           "provenance": "fiction", "sections": [PREMISE],
                           "label": "proposed-fiction"})
    for claim in tagged:
        claim.setdefault("sections", _sections_for(claim))
    tagged = _dedupe(tagged)
    bundle = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "offer": _norm(brief.get("offer")),
        "audience": _norm(brief.get("audience")),
        "action": _norm(brief.get("action") or brief.get("cta")),
        "facts": [{"role": "owner-fact", "field": f, "text": _norm(brief.get(f))}
                  for f in ("offer", "audience")
                  if _nonempty(brief.get(f))],
        "sources": [dict(s) for s in sources],
        "claims": tagged,
        "tagging_errors": errors,
        "generated": evidence.get("generated"),
    }
    return bundle


def validate_bundle(bundle):
    """Refuse a research bundle that is not real research.

    Returns a list of error strings; empty list == accepted. Every rule is
    about content and provenance. Nothing here counts bytes or lines, so a
    padded file cannot buy a pass.
    """
    errors = []
    if not isinstance(bundle, dict):
        return ["bundle: not an object"]
    claims = bundle.get("claims")
    sources = bundle.get("sources") or []
    if not isinstance(claims, list) or not claims:
        return ["claims: empty research bundle (at least one claim required)"]
    by_id = {s.get("id"): s for s in sources if isinstance(s, dict)}
    for err in bundle.get("tagging_errors") or []:
        errors.append("tagging: %s" % err)

    seen_text = {}
    for i, claim in enumerate(claims):
        ref = claim.get("id") if isinstance(claim, dict) else None
        ref = ref or "claim-%d" % (i + 1)
        if not isinstance(claim, dict):
            errors.append("%s: not an object" % ref)
            continue
        prov = claim.get("provenance")
        if prov not in PROVENANCE:
            errors.append("%s: no provenance tag (expected one of %s)"
                          % (ref, ", ".join(PROVENANCE)))
        text = _norm(claim.get("text"))
        if not text:
            errors.append("%s: claim text is empty" % ref)
            continue
        if TERMINATOR_RE.search(text) is None and text.count(",") >= 3:
            errors.append("%s: keyword stuffing — comma list without a "
                          "sentence, not a research claim" % ref)
        key = text.lower()
        if key in seen_text:
            errors.append("%s: duplicate of %s" % (ref, seen_text[key]))
        seen_text.setdefault(key, ref)

        sections = claim.get("sections")
        if not isinstance(sections, list) or not sections:
            errors.append("%s: no research section assigned" % ref)
        else:
            for s in sections:
                if s not in VALID_SECTIONS:
                    errors.append("%s: unknown section %r" % (ref, s))

        if prov == "public-fact":
            src_id = claim.get("source")
            source = by_id.get(src_id) if isinstance(src_id, str) else None
            if not source:
                errors.append("%s: public-fact with no resolvable source" % ref)
            else:
                if not _nonempty(source.get("url")):
                    errors.append("%s: source %s has no url" % (ref, src_id))
                if not _nonempty(source.get("retrieved")):
                    errors.append("%s: source %s has no capture date"
                                  % (ref, src_id))
                claim.setdefault("capture_date", source.get("retrieved"))
            if BUSINESS_RE.search(text):
                errors.append(
                    "%s: unsupported business claim — market evidence cannot "
                    "verify the client's own results/price/guarantee; make it "
                    "an owner-fact with its raw answer identity, or remove or "
                    "qualify it" % ref)
        elif prov == "owner-fact":
            if not _nonempty(claim.get("owner_ref")):
                errors.append("%s: owner-fact with no raw answer identity "
                              "(owner_ref)" % ref)
            claim.setdefault("verification", "owner-asserted-unverified")
        elif prov == "fiction":
            claim.setdefault("label", "proposed-fiction")

    covered = {s: 0 for s in SECTIONS}
    for claim in claims:
        if isinstance(claim, dict) and claim.get("provenance") in PROVENANCE:
            for s in claim.get("sections") or []:
                if s in covered:
                    covered[s] += 1
    # A fiction-only bundle is an explicitly proposed premise, not market
    # research: row 1 allows that. Anything claiming a real fact still has to
    # support every section with a labelled claim.
    fiction_only = bool(claims) and all(
        isinstance(c, dict) and c.get("provenance") == "fiction" for c in claims)
    for section in SECTIONS:
        if not covered[section] and not fiction_only:
            errors.append(
                "%s: no claim supports this section — a header that echoes the "
                "brief is not research" % section)
    return errors


def section_claims(bundle, section):
    """Claims assigned to one section, in filed order."""
    return [c for c in (bundle.get("claims") or [])
            if isinstance(c, dict) and section in (c.get("sections") or [])]
