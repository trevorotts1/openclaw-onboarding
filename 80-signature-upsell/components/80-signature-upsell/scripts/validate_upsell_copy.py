#!/usr/bin/env python3
"""Skill 80 eight-section upsell copy validator (S80-03).

Validates a Signature Upsell copy document (JSON) against the owner's
eight-section derived profile (profiles/upsell-profile.json):

  sections 1-7 retained from the 12-section format, original sections
  8-11 EXCLUDED, original section 12 replaced by the new section 8,
  '7 Reasons To Commit To Your {inspiring phrase} Future', a CTA in
  EVERY section, the offer named in section 1, seven distinct
  substantive reasons, no private framework labels in public output,
  no invented testimonial/scarcity, and (with --compare) U2 copy that
  is not merely renamed U1 copy.

Stdlib only. Exit codes (Skill 49 house convention):
  0 = pass, 2 = violation, 3 = fail-closed on malformed input.

Repairs from the independent review of S80-01/02/03 (defects D-01..D-05):
scarcity and testimonial detection use pattern families from the profile,
not denylists alone; CTA action refs must take the native guarded form and
agree with an externally supplied expectation; purchase directives embedded
in body text are unbound CTAs; section-8 distinctness includes
concept-signature collapse detection. A PASS is a deterministic
no-violation finding, never proof that scarcity/proof are absent or that
a native binding exists.

Second repair pass (re-review defects R2-01, R2-02, R2-06; R2-03/R2-04
folded into the profile pattern families):
  R2-01 - the copy document's own action_binding block is a CLAIM, never
    the trusted expectation. Binding PASS requires an expectation from
    OUTSIDE the copy document: --expected-action-ref, or a separate
    --binding-manifest keyed by page_id/offer_id/copy_id. With neither,
    binding_verification is UNVERIFIED: a violation in the default
    (production) mode, and only a printed limitation under the explicitly
    local --allow-unverified-binding mode.
  R2-02 - unbound purchase-path detection covers paraphrased alternate
    buy paths (payment-page directions, 'complete your purchase', ...),
    scanned per segment; decline/continuation segments are modelled
    explicitly and exempt only when they carry no purchase direction.
  R2-06 - evidence entries must be structured external references
    (U80-EVIDENCE-REF): a bare self-assertion inside the same document
    ('because the copy author says so', source_ref 'this document')
    clears nothing. Structure is required deterministically; the truth
    of the referenced record is S80-06 / S44 read-back territory.

Third repair pass (closing re-review defects R3-01, R3-02, R3-04;
R3-03/R3-05 pattern edges folded into the profile families):
  R3-01 - a caller-supplied binding manifest is no longer trusted on
    presence alone: the matching entry's source_ref must pass the SAME
    structured-external-reference standard as evidence refs (structured
    prefix - request:/graph: admitted so a manifest can cite the S49
    request / route graph - URL, or separator-structured id; assertion
    denylist applied). Prose self-assertion as a manifest source
    ('my own say-so, not a manifest') rejects the manifest
    (U80-CTA-BINDING). Structure is enforced; a forger can still mint
    structured strings - the truth anchor remains S49 / S80-06.
  R3-02 - the decline exemption can no longer shield a purchase
    direction: a decline segment is exempt only when every unbound-CTA
    pattern it trips is the descriptive payment-page direction family
    AND it carries no purchase verb. Decline wording prefixed onto a
    genuine purchase directive ('tap the enrolment link ... to
    activate the upgrade instantly') fails U80-UNBOUND-CTA.
  R3-04 - (schema layer) factual_scarcity_evidence[].source_ref and
    payment_capability.evidence_ref now carry the structured pattern.

Fourth repair pass (closing R3 re-review defects R4-01, R4-02; both Low):
  R4-01 - the R3-05 pause/halt scarcity fold was verb-first only, so its
    subject-first inversion escaped ('Admissions halt on Sunday',
    'Enrolment pauses after this weekend'). The family now carries the
    subject-first alternation, and cheap sibling inversions are folded
    alongside (enrolment closes subject-first, places/spots/seats
    filling, articled/progressive price rises).
  R4-02 - the decline exemption could still shield an imperative spoken
    through the descriptive direction family ('No thanks is an option;
    go to the payment page'). The exemption now also requires NO
    imperative direction (profile imperative_direction_regex: go to /
    head to / visit / navigate to / proceed to + payment/checkout/order
    page, screen or step): the exemption covers descriptive mentions of
    the payment page, never directions to go there. R4-03/R4-04 were
    NOT pattern-chased (declared paraphrase/proof classes, rubric R4/R10;
    BUILD-NOTES Appendix D).

Usage:
  python3 validate_upsell_copy.py COPY.json [--compare OTHER.json]
                                  [--expected-action-ref REF]
                                  [--binding-manifest MANIFEST.json]
                                  [--allow-unverified-binding]
                                  [--profile PROFILE.json] [--self-test]
"""
import argparse
import json
import re
import sys
from pathlib import Path

EXIT_PASS, EXIT_VIOLATION, EXIT_FAIL_CLOSED = 0, 2, 3

DEFAULT_PROFILE = Path(__file__).resolve().parents[1] / "profiles" / "upsell-profile.json"
EXPECTED_KEYS = ["big_bold_claim", "big_bold_pain_1", "big_bold_pain_2", "big_bold_pain_3",
                 "big_bold_why", "big_bold_who", "big_bold_what", "seven_reasons"]
STOPWORDS = set("the a an and or of to your you is are it its in on for with this that "
                "when what who why how get got have has will can all not but from".split())
MIN_REASON_CHARS = 30          # structural floor for 'substantive'; NOT an imported copy band
DISTINCT_JACCARD_MAX = 0.80    # pairwise reason similarity ceiling
PAIN_JACCARD_MAX = 0.85        # pairwise pain-section similarity ceiling
PAIR_JACCARD_MAX = 0.65        # whole-document renamed-copy similarity ceiling
# Repair constants (independent review S80-01-03, defects D-01..D-05):
NATIVE_ACTION_REF = re.compile(r"^native-one-click:[A-Za-z0-9][A-Za-z0-9._-]*$")
FORBIDDEN_ACTION_MARKERS = ("://", "custom-fetch", "fetch:", "http:", "https:")
CONCEPT_PAIR_COLLAPSE_MIN = 5   # of 7 reasons: one concept pair co-occurring this often = collapse
CONCEPT_SIGNATURE_COLLAPSE_MIN = 5  # of 7 reasons sharing one identical concept signature
# R2-06 fallbacks (profile validator_patterns.evidence_ref_structure wins when
# present); request:/graph: prefixes added by R3-01 for manifest citations.
STRUCTURED_REF_DEFAULT = (r"^(?:(?:ledger|provider-event|s44|native|catalog|request|graph):[A-Za-z0-9][A-Za-z0-9._/-]*"
                          r"|https?://\S+|[A-Za-z0-9]+(?:[/_#-][A-Za-z0-9]+)+)$")
ASSERTION_DENYLIST_DEFAULT = ("says so", "say-so", "trust me", "believe me", "just trust",
                              "my own say-so", "own say-so", "this document", "because i said",
                              "author says so", "self-asserted", "no external source",
                              "not a manifest", "my own word")


class FailClosed(Exception):
    pass


def fail(code, message, violations):
    violations.append({"code": code, "message": message})


def tokens(text):
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


def jaccard(a, b):
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / max(1, len(sa | sb))


def load_json(path, label):
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise FailClosed(f"{label}: cannot read {path}: {exc}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FailClosed(f"{label}: malformed JSON in {path}: {exc}")


def check_doc_shape(doc, label):
    if not isinstance(doc, dict):
        raise FailClosed(f"{label}: top level must be a JSON object")
    for field in ("instance", "offer_name", "inspiring_phrase", "accept_action_ref", "sections"):
        if field not in doc:
            raise FailClosed(f"{label}: missing required field '{field}'")
    if doc["instance"] not in ("upsell_1", "upsell_2"):
        raise FailClosed(f"{label}: instance must be upsell_1 or upsell_2, got {doc['instance']!r}")
    if "action_binding" in doc:
        binding = doc["action_binding"]
        if not isinstance(binding, dict):
            raise FailClosed(f"{label}: action_binding must be an object")
        for field in ("expected_action_ref", "binding_kind", "source_ref"):
            if not isinstance(binding.get(field), str) or not binding[field].strip():
                raise FailClosed(f"{label}: action_binding.{field} must be a non-empty string")
    if not isinstance(doc["sections"], list):
        raise FailClosed(f"{label}: sections must be a list")
    for i, sec in enumerate(doc["sections"], 1):
        if not isinstance(sec, dict):
            raise FailClosed(f"{label}: section entry {i} is not an object")
        for field in ("number", "key", "heading", "body", "cta"):
            if field not in sec:
                raise FailClosed(f"{label}: section entry {i} missing '{field}'")
        if not isinstance(sec["cta"], dict) or "text" not in sec["cta"] or "action_ref" not in sec["cta"]:
            raise FailClosed(f"{label}: section entry {i} cta must carry text and action_ref")


def section_text(sec):
    parts = [sec.get("heading", ""), sec.get("body", "")]
    parts += sec.get("bullets", []) or []
    parts += sec.get("reasons", []) or []
    parts.append((sec.get("cta") or {}).get("text", ""))
    return "\n".join(parts)


def body_text(sec):
    """Section text WITHOUT the mapped CTA: the surface D-05 scans for unbound CTAs."""
    parts = [sec.get("heading", ""), sec.get("body", "")]
    parts += sec.get("bullets", []) or []
    parts += sec.get("reasons", []) or []
    return "\n".join(parts)


def body_segments(sec):
    """Body text split into scan segments (lines, then sentences).

    The unbound-CTA scan (R2-02) works per segment so the decline /
    continuation exemption can be modelled explicitly per statement.
    """
    segments = []
    for line in body_text(sec).split("\n"):
        for piece in re.split(r"(?<=[.!?])\s+", line):
            piece = piece.strip()
            if piece:
                segments.append(piece)
    return segments


def evidence_structure_config(profile):
    cfg = ((profile.get("validator_patterns") or {}).get("evidence_ref_structure") or {})
    pattern = cfg.get("source_ref_pattern") or STRUCTURED_REF_DEFAULT
    denylist = cfg.get("assertion_denylist") or list(ASSERTION_DENYLIST_DEFAULT)
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise FailClosed(f"profile: invalid evidence source_ref_pattern: {exc}")
    return compiled, [d.lower() for d in denylist]


def source_ref_problem(ref, profile):
    """Structured-external-reference check for a single source_ref string.

    Shared by evidence entries (R2-06) and binding-manifest entries
    (R3-01): the same standard applies wherever a document or a
    caller-supplied file names its own source - a prefixed record ref
    (ledger:/provider-event:/s44:/native:/catalog:/request:/graph:), an
    http(s) URL, or a separator-structured record id, with no assertion
    denylist marker. Returns a problem string, or None when the ref is
    structurally valid. Deterministic structure only: this cannot prove
    the referenced record exists (S80-06 / S44 / S49 read-back does).
    """
    if not isinstance(ref, str) or not ref.strip():
        return "carries no source_ref"
    pattern, denylist = evidence_structure_config(profile)
    low = ref.lower()
    for marker in denylist:
        if marker in low:
            return (f"source_ref is a bare self-assertion (matches assertion marker {marker!r}), "
                    "not an external record")
    if not pattern.match(ref.strip()):
        return (f"source_ref {ref!r} is not a structured external reference (required: a prefixed record ref "
                "ledger:/provider-event:/s44:/native:/catalog:/request:/graph:, an http(s) URL, or a "
                "separator-structured record id)")
    return None


def evidence_entry_problems(entry, profile):
    """R2-06: an evidence entry counts only as a structured EXTERNAL reference.

    Returns a problem string, or None when the entry is structurally valid.
    Deterministic structure only: this cannot prove the referenced record
    exists or is truthful (S80-06 / S44 read-back proves that).
    """
    if not isinstance(entry, dict):
        return "entry is not an object with fact + source_ref"
    fact, ref = entry.get("fact"), entry.get("source_ref")
    if not isinstance(fact, str) or not fact.strip():
        return "entry carries no fact"
    if not isinstance(ref, str) or not ref.strip():
        return "entry carries no source_ref"
    _, denylist = evidence_structure_config(profile)
    hay = (fact + " " + ref).lower()
    for marker in denylist:
        if marker in hay:
            return f"entry is a bare self-assertion (matches assertion marker {marker!r}), not an external record"
    return source_ref_problem(ref, profile)


def valid_evidence_entries(entries, kind, profile, violations):
    """Split evidence entries into valid ones; invalid ones are violations
    (U80-EVIDENCE-REF) and clear NOTHING (R2-06)."""
    valid = []
    for i, entry in enumerate(entries or [], 1):
        problem = evidence_entry_problems(entry, profile)
        if problem is None:
            valid.append(entry)
        else:
            fail("U80-EVIDENCE-REF",
                 f"verified_{kind}_evidence entry {i} rejected: {problem}; an in-document self-assertion "
                 "is not evidence and does not clear scarcity/proof checks", violations)
    return valid


def lookup_binding_manifest(doc, manifest, profile):
    """Find the manifest entry for this copy document (repair R2-01).

    Entries are keyed by page_id / offer_id / copy_id and must carry their
    own expected_action_ref + source_ref (the instance request id / S49
    route-graph reference). The entry's source_ref must ALSO pass the
    structured-external-reference standard that evidence refs are held
    to (repair R3-01): a caller-supplied manifest is not authenticated
    by prose, so an entry whose source_ref is a bare self-assertion
    ('my own say-so, not a manifest') rejects the manifest. Returns
    (entry, problem): exactly one is None when a manifest was supplied;
    (None, None) when no manifest was given.
    """
    if manifest is None:
        return None, None
    if isinstance(manifest, dict) and isinstance(manifest.get("bindings"), list):
        entries = manifest["bindings"]
    elif isinstance(manifest, dict):
        entries = [e for e in manifest.values() if isinstance(e, dict)]
    else:
        raise FailClosed("binding manifest: top level must be an object with a 'bindings' list")
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for key in ("page_id", "offer_id", "copy_id"):
            if entry.get(key) and doc.get(key) and entry[key] == doc[key]:
                if not isinstance(entry.get("expected_action_ref"), str) \
                        or not entry["expected_action_ref"].strip():
                    return None, f"binding manifest entry for {key}={entry[key]!r} carries no expected_action_ref"
                if not isinstance(entry.get("source_ref"), str) or not entry["source_ref"].strip():
                    return None, (f"binding manifest entry for {key}={entry[key]!r} carries no source_ref "
                                  "naming its own external source (request id / S49 graph reference)")
                problem = source_ref_problem(entry["source_ref"], profile)
                if problem:
                    return None, (f"binding manifest entry for {key}={entry[key]!r} rejected: its source_ref "
                                  f"fails the structured-external-reference standard (repair R3-01): {problem}. "
                                  "A caller-supplied manifest is not authenticated by prose; its entries must "
                                  "name a structured external source (a request:/graph:/ledger: record ref, an "
                                  "http(s) URL, or a separator-structured record id)")
                return entry, None
    return None, ("binding manifest supplied but no entry is keyed to this copy document "
                  "(looked up page_id / offer_id / copy_id)")


def compile_patterns(profile, group):
    patterns = (profile.get("validator_patterns") or {}).get(group) or []
    compiled = []
    for entry in patterns:
        try:
            compiled.append((entry.get("id", group), re.compile(entry["regex"], re.IGNORECASE)))
        except (KeyError, re.error) as exc:
            raise FailClosed(f"profile: invalid regex in validator_patterns.{group}: {exc}")
    return compiled


def concept_signature(reason, groups):
    """Map a reason to the concept groups it expresses (stem/phrase matching)."""
    toks = tokens(reason)
    joined = " " + " ".join(toks) + " "
    hits = set()
    for name, stems in groups.items():
        for stem in stems:
            stem_norm = stem.lower().replace("-", " ")
            if " " in stem_norm:
                if f" {stem_norm} " in joined:
                    hits.add(name)
                    break
            elif any(t.startswith(stem_norm) for t in toks):
                hits.add(name)
                break
    return frozenset(hits)


def testimonial_pattern_hits(text, profile):
    """Return testimonial-construction hits in text (repair D-02).

    Catches the profile's endorsement pattern families plus attributed quotes:
    a quoted span of 10+ chars with an attribution verb in the surrounding
    window, or quoted first-person result language.
    """
    hits = []
    for pid, rx in compile_patterns(profile, "testimonial_claim_patterns"):
        if rx.search(text):
            hits.append(pid)
    patterns_cfg = profile.get("validator_patterns") or {}
    quote_rx = patterns_cfg.get("quote_span_regex")
    verb_rx = patterns_cfg.get("attribution_verbs_regex")
    if quote_rx and verb_rx:
        try:
            quotes = list(re.compile(quote_rx, re.IGNORECASE).finditer(text))
            verbs = re.compile(verb_rx, re.IGNORECASE)
            first_person = re.compile(
                r"\bi (doubled|tripled|increased|grew|made|earned|saved|lost)\b", re.IGNORECASE)
        except re.error as exc:
            raise FailClosed(f"profile: invalid testimonial regex: {exc}")
        for m in quotes:
            window = text[max(0, m.start() - 100): m.end() + 100]
            if verbs.search(window) or first_person.search(m.group(1)):
                hits.append("attributed_quote")
                break
    return hits


def validate_copy_report(doc, profile, label="copy", expected_action_ref=None,
                         binding_manifest=None, allow_unverified_binding=False):
    """Validate and return {"violations": [...], "binding_verification": ...,
    "binding_source": ...}. Raises FailClosed on malformed input.

    Binding expectation (repairs D-03 + R2-01): the guarded native action
    reference expected for this instance must come from OUTSIDE the copy
    document - expected_action_ref (CLI, sourced from the instance
    request/manifest) wins, then a --binding-manifest entry keyed to this
    document. The copy document's own accept_action_ref AND its in-document
    action_binding block are claims, never the trusted expectation: the
    block is checked for internal consistency only. With no external
    expectation the binding is UNVERIFIED - a violation unless
    allow_unverified_binding (explicit local/fixture mode) is set.
    """
    check_doc_shape(doc, label)
    v = []
    denylists = profile["validator_denylists"]
    sections = doc["sections"]
    visibility = doc.get("visibility", "public")
    # R2-06: only structurally valid external evidence entries count.
    evidence = valid_evidence_entries(doc.get("verified_scarcity_evidence") or [],
                                      "scarcity", profile, v)
    proof = valid_evidence_entries(doc.get("verified_proof_evidence") or [],
                                   "proof", profile, v)
    scarcity_patterns = compile_patterns(profile, "scarcity_claim_patterns")
    unbound_patterns = compile_patterns(profile, "unbound_cta_patterns")
    decline_cfg = (profile.get("validator_patterns") or {}).get("decline_continuation_allowlist") or {}
    try:
        decline_rx = re.compile(decline_cfg["segment_regex"], re.IGNORECASE) if decline_cfg else None
        purchase_verb_rx = re.compile(decline_cfg["purchase_verb_regex"], re.IGNORECASE) if decline_cfg else None
        # R4-02: an imperative direction ('go to the payment page') voids the
        # decline exemption. A profile written before R4-02 has no such field;
        # it then compiles to None and the exemption keeps its R3-02 shape.
        imperative_rx = re.compile(decline_cfg["imperative_direction_regex"], re.IGNORECASE) \
            if decline_cfg.get("imperative_direction_regex") else None
    except (KeyError, re.error) as exc:
        raise FailClosed(f"profile: invalid decline_continuation_allowlist regex: {exc}")
    # R3-02: pattern families whose hit in a decline segment is a mere
    # descriptive mention of the payment page, not a purchase directive.
    descriptive_direction_ids = set(decline_cfg.get("descriptive_direction_pattern_ids") or [])

    # U80-CTA-BINDING (repairs D-03 + R2-01): the accept action must be a
    # native product-bound guarded action and must agree with an
    # expectation supplied from OUTSIDE the copy document.
    ref = doc["accept_action_ref"]
    binding = doc.get("action_binding") or {}
    if binding:
        if binding["binding_kind"] != "native_one_click_guarded":
            fail("U80-CTA-BINDING",
                 f"action_binding.binding_kind {binding['binding_kind']!r} is not the guarded native one-click binding", v)
        if binding["expected_action_ref"] != ref:
            fail("U80-CTA-BINDING",
                 f"the document's own action_binding block expects {binding['expected_action_ref']!r} "
                 f"(claimed source: {binding['source_ref']}) but the document declares accept_action_ref {ref!r}; "
                 "the in-document block is a claim and is checked for consistency only, never trusted as the expectation", v)
    manifest_entry, manifest_problem = lookup_binding_manifest(doc, binding_manifest, profile)
    if manifest_problem:
        fail("U80-CTA-BINDING", manifest_problem, v)
    if expected_action_ref is not None:
        expected, binding_source = expected_action_ref, "--expected-action-ref (caller-supplied)"
    elif manifest_entry is not None:
        expected = manifest_entry["expected_action_ref"]
        binding_source = f"binding manifest entry (source: {manifest_entry['source_ref']})"
    else:
        expected, binding_source = None, None
    binding_verification = "verified_external" if expected is not None else "unverified"
    if not isinstance(ref, str) or not NATIVE_ACTION_REF.match(ref) \
            or any(marker in ref.lower() for marker in FORBIDDEN_ACTION_MARKERS):
        fail("U80-CTA-BINDING",
             f"accept_action_ref {ref!r} is not a native product-bound guarded action reference "
             "(required form: native-one-click:<action-id>; custom fetch endpoints and raw charge URLs are forbidden)", v)
    elif expected is not None and ref != expected:
        fail("U80-CTA-BINDING",
             f"accept_action_ref {ref!r} != the externally expected guarded action {expected!r} "
             f"from {binding_source}", v)
    if expected is None and not allow_unverified_binding:
        fail("U80-CTA-BINDING-UNVERIFIED",
             "no external binding expectation was supplied (--expected-action-ref or --binding-manifest), so the "
             "CTA binding is UNVERIFIED: the copy document cannot expect its own action ref (R2-01). Supply the "
             "expectation from the instance request / S49 manifest, or use --allow-unverified-binding for "
             "explicit local fixture work only", v)

    # U80-SECTION-COUNT / numbering / order / keys
    if len(sections) != 8:
        fail("U80-SECTION-COUNT",
             f"exactly 8 sections required, found {len(sections)}", v)
    numbers = [s["number"] for s in sections]
    if numbers != list(range(1, len(sections) + 1)):
        fail("U80-SECTION-ORDER",
             f"section numbers must be consecutive from 1, found {numbers}", v)
    keys = [s["key"] for s in sections]
    if keys != EXPECTED_KEYS[:len(sections)] or len(sections) != 8:
        if len(sections) == 8:
            fail("U80-SECTION-KEYS",
                 f"section keys must be the derived profile keys {EXPECTED_KEYS}, found {keys}", v)

    # U80-ORIGINAL-SECTIONS-EXCLUDED: original 8-11 (Benefits / How To / founder
    # message as an extra section) must never be reintroduced.
    for sec in sections:
        marker_text = (sec["key"] + " " + sec["heading"]).lower()
        for marker in denylists["reintroduced_original_section_markers"]:
            if marker.lower() in marker_text:
                fail("U80-ORIGINAL-SECTIONS-EXCLUDED",
                     f"section {sec['number']} reintroduces an excluded original section marker: {marker!r}", v)
        if sec["number"] > 8:
            fail("U80-ORIGINAL-SECTIONS-EXCLUDED",
                 f"section number {sec['number']} exceeds the derived 8-section profile", v)

    for sec in sections:
        n = sec["number"]
        # U80-CTA-MISSING / U80-CTA-BINDING: CTA in EVERY section, same guarded action
        cta = sec["cta"]
        if not (cta.get("text") or "").strip():
            fail("U80-CTA-MISSING", f"section {n} ({sec['key']}) has no CTA text", v)
        elif cta.get("action_ref") != doc["accept_action_ref"]:
            fail("U80-CTA-BINDING",
                 f"section {n} CTA action_ref {cta.get('action_ref')!r} != the instance's single guarded action {doc['accept_action_ref']!r}", v)
        # U80-INVENTED-TESTIMONIAL / U80-INVENTED-SCARCITY (repairs D-01, D-02):
        # denylist markers PLUS pattern families; each class is gated on its
        # own verified evidence array (missing proof stays missing).
        text_low = section_text(sec).lower()
        if not proof:
            for marker in denylists["invented_testimonial_markers"]:
                if marker in text_low:
                    fail("U80-INVENTED-TESTIMONIAL",
                         f"section {n} contains an invented-proof marker: {marker!r} (missing proof stays missing)", v)
            for pid in testimonial_pattern_hits(section_text(sec), profile):
                fail("U80-INVENTED-TESTIMONIAL",
                     f"section {n} contains a testimonial construction matching pattern {pid!r} "
                     "with no verified_proof_evidence entry (missing proof stays missing)", v)
        if not evidence:
            for marker in denylists["invented_scarcity_markers"]:
                if marker in text_low:
                    fail("U80-INVENTED-SCARCITY",
                         f"section {n} contains a scarcity marker {marker!r} with no verified_scarcity_evidence entry", v)
            for pid, rx in scarcity_patterns:
                if rx.search(section_text(sec)):
                    fail("U80-INVENTED-SCARCITY",
                         f"section {n} contains a scarcity claim matching pattern {pid!r} "
                         "with no verified_scarcity_evidence entry", v)
        # U80-UNBOUND-CTA (repairs D-05 + R2-02 + R3-02 + R4-02): purchase
        # directives embedded in body text are a second, unbound buy path
        # next to the mapped CTA. Scanned per segment; a segment that models
        # the DECLINE path (no-thanks / continue-without / skip wording) is
        # exempt ONLY when it carries no purchase direction: every unbound
        # pattern it trips must be a descriptive-direction family (a mere
        # mention of the payment page, e.g. 'the payment page is only for
        # buyers'), it must contain no purchase verb, AND it must contain no
        # imperative direction (go to / head to / visit / navigate to /
        # proceed to + a payment/checkout/order page, screen or step). The
        # R2-02 exemption tested only the purchase-verb list, which is
        # narrower than the families it exempted from - decline wording
        # prefixed onto a genuine purchase directive ('tap the enrolment
        # link ... to activate the upgrade instantly', tap_to_buy family,
        # no listed verb) was exempted from a scan it would otherwise fail
        # (defect R3-02). R3-02 narrowed the exemption to descriptive-family
        # hits, but that family's regex cannot distinguish a descriptive
        # mention from a true imperative spoken through the same family
        # ('No thanks is an option; go to the payment page' - defect R4-02),
        # so the exemption now also requires the absence of an imperative
        # direction: it covers descriptive mentions, never directions. A
        # decline segment tripping any directive family, carrying a purchase
        # verb, or speaking an imperative direction is NOT exempt.
        for segment in body_segments(sec):
            hits = []
            for pid, rx in unbound_patterns:
                m = rx.search(segment)
                if m:
                    hits.append((pid, m.group(0)))
            if not hits:
                continue
            if decline_rx is not None and purchase_verb_rx is not None \
                    and decline_rx.search(segment) \
                    and not purchase_verb_rx.search(segment) \
                    and not (imperative_rx is not None and imperative_rx.search(segment)) \
                    and all(pid in descriptive_direction_ids for pid, _ in hits):
                continue
            fail("U80-UNBOUND-CTA",
                 f"section {n} embeds an unbound purchase directive in body text "
                 f"(pattern {hits[0][0]!r}: ...{hits[0][1]!r}...); every purchase action must be "
                 "the mapped CTA bound to the single guarded native action", v)
            break
        # U80-PRIVATE-LABEL-LEAK: public output only; private authoring source is lawful
        if visibility == "public":
            for marker in denylists["private_framework_labels"]:
                if marker.lower() in text_low:
                    fail("U80-PRIVATE-LABEL-LEAK",
                         f"section {n} leaks a private framework label into public output: {marker!r}", v)

    if len(sections) >= 1:
        # U80-OFFER-NAMED-EARLY: offer clear from the start
        first = sections[0]
        hay = (first["heading"] + " " + first["body"]).lower()
        names = [doc["offer_name"].lower()] + [s.lower() for s in doc.get("offer_aliases", [])]
        if not any(name and name in hay for name in names):
            fail("U80-OFFER-NAMED-EARLY",
                 f"section 1 does not name the offer {doc['offer_name']!r}; the offer must be clear from the beginning", v)

    # Pains must be three distinct challenges
    pains = [s for s in sections if s["key"].startswith("big_bold_pain_")]
    for i in range(len(pains)):
        for j in range(i + 1, len(pains)):
            sim = jaccard(tokens(section_text(pains[i])), tokens(section_text(pains[j])))
            if sim >= PAIN_JACCARD_MAX:
                fail("U80-PAIN-DISTINCT",
                     f"pain sections {pains[i]['number']} and {pains[j]['number']} are near-duplicates (jaccard {sim:.2f})", v)

    # Section 8: heading pattern + exactly 7 distinct substantive reasons
    sec8 = next((s for s in sections if s["key"] == "seven_reasons"), None)
    if sec8 is not None:
        heading = sec8["heading"].strip()
        phrase = doc["inspiring_phrase"].strip()
        pattern = r"^7 Reasons To Commit To Your .+ Future$"
        if not re.match(pattern, heading, re.IGNORECASE):
            fail("U80-REASON-HEADING",
                 f"section 8 heading {heading!r} does not match the approved pattern '7 Reasons To Commit To Your <phrase> Future'", v)
        elif phrase.lower() not in heading.lower():
            fail("U80-REASON-HEADING",
                 f"section 8 heading {heading!r} does not carry the approved inspiring phrase {phrase!r}", v)
        reasons = sec8.get("reasons")
        if not isinstance(reasons, list):
            raise FailClosed(f"{label}: section 8 must carry a 'reasons' list")
        if len(reasons) != 7:
            fail("U80-REASON-COUNT", f"section 8 must have exactly 7 reasons, found {len(reasons)}", v)
        seen = {}
        for idx, reason in enumerate(reasons, 1):
            if not isinstance(reason, str):
                raise FailClosed(f"{label}: reason {idx} is not a string")
            norm = " ".join(tokens(reason))
            if len(reason.strip()) < MIN_REASON_CHARS or len(set(tokens(reason))) < 6:
                fail("U80-REASON-SUBSTANCE",
                     f"reason {idx} is not substantive ({len(reason.strip())} chars, floor {MIN_REASON_CHARS})", v)
            if norm in seen:
                fail("U80-REASON-DISTINCT", f"reason {idx} duplicates reason {seen[norm]}", v)
            seen[norm] = idx
        for i in range(len(reasons)):
            for j in range(i + 1, len(reasons)):
                sim = jaccard(tokens(reasons[i]), tokens(reasons[j]))
                if sim >= DISTINCT_JACCARD_MAX:
                    fail("U80-REASON-DISTINCT",
                         f"reasons {i+1} and {j+1} are near-duplicates (jaccard {sim:.2f})", v)
        # Concept-signature collapse (repair D-04): lexical metrics cannot
        # separate paraphrases of ONE proposition from distinct reasons
        # (measured in the review: the paraphrase set scores lower on raw
        # similarity than the owner's own sample). Map each reason to the
        # concept groups it expresses; seven reasons that keep restating the
        # same concept pair, or share one identical signature, have collapsed
        # to a single repeated idea however they are worded.
        groups = (profile.get("reason_concept_groups") or {}).get("groups") or {}
        if groups and len(reasons) == 7:
            signatures = [concept_signature(r, groups) for r in reasons]
            pair_counts = {}
            signature_counts = {}
            for sig in signatures:
                if sig:
                    signature_counts[sig] = signature_counts.get(sig, 0) + 1
                for a in sig:
                    for b in sig:
                        if a < b:
                            pair_counts[(a, b)] = pair_counts.get((a, b), 0) + 1
            for (a, b), count in sorted(pair_counts.items()):
                if count >= CONCEPT_PAIR_COLLAPSE_MIN:
                    fail("U80-REASON-DISTINCT",
                         f"reasons collapse to a single repeated proposition: concept pair "
                         f"({a}, {b}) is restated in {count} of 7 reasons; the seven reasons "
                         "must be substantively distinct benefits, not paraphrases of one", v)
            for sig, count in sorted(signature_counts.items(), key=lambda kv: sorted(kv[0])):
                if count >= CONCEPT_SIGNATURE_COLLAPSE_MIN:
                    fail("U80-REASON-DISTINCT",
                         f"{count} of 7 reasons share the identical concept signature "
                         f"{sorted(sig)}; the seven reasons must cover distinct ground", v)
    return {"violations": v, "binding_verification": binding_verification,
            "binding_source": binding_source}


def validate_copy(doc, profile, label="copy", expected_action_ref=None,
                  binding_manifest=None, allow_unverified_binding=False):
    """Back-compatible wrapper: return only the violation dicts.

    Callers that need the binding_verification status (R2-01) use
    validate_copy_report.
    """
    return validate_copy_report(
        doc, profile, label=label, expected_action_ref=expected_action_ref,
        binding_manifest=binding_manifest,
        allow_unverified_binding=allow_unverified_binding)["violations"]


def validate_pair(u1_doc, u2_doc, profile):
    """U2 distinctness against its U1 (spec 10 section 4; acceptance A12)."""
    v = []
    check_doc_shape(u1_doc, "compare-u1")
    check_doc_shape(u2_doc, "copy-u2")

    def normalized(doc):
        text = "\n".join(section_text(s) for s in doc["sections"])
        for name in (doc["offer_name"], doc["inspiring_phrase"]):
            text = re.sub(re.escape(name), " ", text, flags=re.IGNORECASE)
        return tokens(text)

    sim = jaccard(normalized(u1_doc), normalized(u2_doc))
    if sim >= PAIR_JACCARD_MAX:
        fail("U80-U2-DISTINCT",
             f"U2 is merely renamed U1 copy (similarity {sim:.2f} >= {PAIR_JACCARD_MAX} after offer/phrase removal); "
             "U2 must explain a genuinely different incremental outcome", v)
    s8_1 = next((s for s in u1_doc["sections"] if s["key"] == "seven_reasons"), None)
    s8_2 = next((s for s in u2_doc["sections"] if s["key"] == "seven_reasons"), None)
    if s8_1 and s8_2:
        rsim = jaccard(tokens(" ".join(s8_1.get("reasons", []))), tokens(" ".join(s8_2.get("reasons", []))))
        if rsim >= PAIR_JACCARD_MAX:
            fail("U80-U2-DISTINCT",
                 f"U2 section 8 reasons are a rename of U1 reasons (similarity {rsim:.2f})", v)
    return v


def self_test():
    profile = json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))
    fixtures = DEFAULT_PROFILE.parents[1] / "fixtures"
    ok = True

    def expect(name, doc, compare=None, want=EXIT_PASS, want_code=None, expected_ref=None,
               want_codes=None, manifest=None):
        nonlocal ok
        try:
            report = validate_copy_report(doc, profile, name,
                                          expected_action_ref=expected_ref,
                                          binding_manifest=manifest)
            result = report["violations"]
            if compare is not None:
                result += validate_pair(compare, doc, profile)
            code = EXIT_PASS if not result else EXIT_VIOLATION
            codes = [x["code"] for x in result]
        except FailClosed:
            code, codes = EXIT_FAIL_CLOSED, []
        passed = code == want and (want_code is None or want_code in codes) \
            and (want_codes is None or set(want_codes) <= set(codes))
        if not passed:
            ok = False
        detail = f" codes={codes}" if (want_code is not None or want_codes is not None) else ""
        print(f"  [{'PASS' if passed else 'FAIL'}] self-test {name}: exit {code} (expected {want}){detail}")

    u1 = load_json(fixtures / "copy-upsell1-public.valid.json", "u1")
    u2 = load_json(fixtures / "copy-upsell2-public.valid.json", "u2")
    sample = load_json(fixtures / "copy-owner-sample-upsell1.private.json", "sample")
    binding_manifest = load_json(fixtures / "binding-manifest.testonly.json", "binding-manifest")
    expect("valid-public-u1", u1, expected_ref="native-one-click:TEST-ONLY-U1")
    expect("valid-public-u2-vs-u1", u2, compare=u1, manifest=binding_manifest)
    expect("owner-sample-private", sample, expected_ref="native-one-click:TEST-ONLY-SAMPLE-U1")
    expect("seven-sections", load_json(fixtures / "copy-neg-seven-sections.json", "n"), want=EXIT_VIOLATION)
    expect("missing-cta", load_json(fixtures / "copy-neg-missing-cta-who.json", "n"), want=EXIT_VIOLATION)
    renamed = load_json(fixtures / "copy-neg-u2-renamed-u1.json", "n")
    expect("u2-renamed-u1", renamed, compare=u1, want=EXIT_VIOLATION)
    # Regression entries from the independent review's adversarial fixtures
    # (fixtures/regression-fixtures-manifest.json; defects D-01..D-05).
    manifest_path = fixtures / "regression-fixtures-manifest.json"
    if manifest_path.exists():
        for entry in load_json(manifest_path, "regression-manifest")["fixtures"]:
            doc_r = load_json(fixtures / entry["file"], "regression")
            expect(f"regression-{entry['defect']}", doc_r, want=EXIT_VIOLATION,
                   want_code=entry["expected_code"])
    # R2 regression entries (re-review adversarial fixtures; R2-01..R2-06).
    expect("r2-01-self-authored-binding",
           load_json(fixtures / "copy-r2-self-authored-binding.json", "r2"),
           want=EXIT_VIOLATION, want_code="U80-CTA-BINDING-UNVERIFIED")
    expect("r2-02-unbound-cta-paraphrase",
           load_json(fixtures / "copy-r2-unbound-cta-paraphrase.json", "r2"),
           want=EXIT_VIOLATION, want_codes=["U80-UNBOUND-CTA", "U80-CTA-BINDING-UNVERIFIED"])
    expect("r2-03-scarcity-morphology",
           load_json(fixtures / "copy-r2-scarcity-morphology.json", "r2"),
           want=EXIT_VIOLATION, want_code="U80-INVENTED-SCARCITY")
    expect("r2-04-testimonial-collective",
           load_json(fixtures / "copy-r2-testimonial-collective.json", "r2"),
           want=EXIT_VIOLATION, want_code="U80-INVENTED-TESTIMONIAL")
    expect("r2-06-self-asserted-evidence",
           load_json(fixtures / "copy-r2-self-asserted-evidence.json", "r2"),
           want=EXIT_VIOLATION, want_codes=["U80-EVIDENCE-REF", "U80-INVENTED-SCARCITY"])
    # R3 regression entries (closing re-review adversarial constructions;
    # R3-01/R3-02/R3-03/R3-05).
    expect("r3-01-manifest-self-authored",
           load_json(fixtures / "copy-r2-self-authored-binding.json", "r3"),
           manifest=load_json(fixtures / "binding-manifest-r3-self-authored.testonly.json", "r3-manifest"),
           want=EXIT_VIOLATION, want_code="U80-CTA-BINDING")
    expect("r3-02-decline-smuggled-cta",
           load_json(fixtures / "copy-r3-decline-smuggled-cta.json", "r3"),
           want=EXIT_VIOLATION, want_code="U80-UNBOUND-CTA")
    expect("r3-03-unbound-buy-paths",
           load_json(fixtures / "copy-r3-unbound-buy-paths.json", "r3"),
           want=EXIT_VIOLATION, want_code="U80-UNBOUND-CTA")
    expect("r3-05-scarcity-pause-enrolments",
           load_json(fixtures / "copy-r3-scarcity-pause-enrolments.json", "r3"),
           want=EXIT_VIOLATION, want_code="U80-INVENTED-SCARCITY")
    # R4 regression entries (closing R3 re-review adversarial constructions;
    # R4-01 subject-first scarcity, R4-02 decline-shielded imperative).
    expect("r4-01-scarcity-subject-first",
           load_json(fixtures / "copy-r4-scarcity-subject-first.json", "r4"),
           want=EXIT_VIOLATION, want_code="U80-INVENTED-SCARCITY")
    expect("r4-02-decline-shielded-imperative",
           load_json(fixtures / "copy-r4-decline-shielded-imperative.json", "r4"),
           want=EXIT_VIOLATION, want_code="U80-UNBOUND-CTA")
    print("SELF-TEST RESULT:", "PASS" if ok else "FAIL")
    return EXIT_PASS if ok else EXIT_VIOLATION


def main(argv=None):
    ap = argparse.ArgumentParser(description="Skill 80 eight-section upsell copy validator")
    ap.add_argument("copy", nargs="?", help="copy document JSON to validate")
    ap.add_argument("--compare", help="U1 copy JSON; required to check U2 distinctness for upsell_2 docs")
    ap.add_argument("--expected-action-ref",
                    help="guarded native action ref expected for this instance, sourced from the "
                         "instance request/manifest (repairs D-03/R2-01: the copy document's own "
                         "accept_action_ref and action_binding block are claims, not proof)")
    ap.add_argument("--binding-manifest",
                    help="binding manifest JSON produced OUTSIDE the copy document; entries keyed "
                         "by page_id/offer_id/copy_id, each carrying expected_action_ref and its own "
                         "source_ref (repair R2-01)")
    ap.add_argument("--allow-unverified-binding", action="store_true",
                    help="LOCAL FIXTURE MODE ONLY: report the binding as UNVERIFIED instead of "
                         "failing closed. Never usable as production binding evidence")
    ap.add_argument("--profile", default=str(DEFAULT_PROFILE), help="upsell profile JSON")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        try:
            return self_test()
        except FailClosed as exc:
            print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
            return EXIT_FAIL_CLOSED
    if not args.copy:
        ap.print_usage(sys.stderr)
        return EXIT_FAIL_CLOSED
    try:
        profile = load_json(args.profile, "profile")
        doc = load_json(args.copy, "copy")
        manifest = load_json(args.binding_manifest, "binding-manifest") if args.binding_manifest else None
        report = validate_copy_report(doc, profile,
                                      expected_action_ref=args.expected_action_ref,
                                      binding_manifest=manifest,
                                      allow_unverified_binding=args.allow_unverified_binding)
        violations = report["violations"]
        if args.compare:
            other = load_json(args.compare, "compare")
            if doc.get("instance") == "upsell_2":
                violations += validate_pair(other, doc, profile)
            elif other.get("instance") == "upsell_2":
                violations += validate_pair(doc, other, profile)
            else:
                violations += validate_pair(other, doc, profile)
    except FailClosed as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return EXIT_FAIL_CLOSED
    print(f"BINDING VERIFICATION: {report['binding_verification']}"
          + (f" (expectation source: {report['binding_source']})" if report["binding_source"] else ""))
    if report["binding_verification"] == "unverified" and args.allow_unverified_binding:
        print("LIMITATION: binding_verification=unverified - no external expectation was supplied, so the "
              "copy document's own action ref was checked for form only. This run is local fixture work "
              "and is NOT production binding evidence (repair R2-01).")
    if violations:
        for item in violations:
            print(f"VIOLATION [{item['code']}] {item['message']}")
        print(f"RESULT: FAIL ({len(violations)} violation(s))")
        return EXIT_VIOLATION
    print(f"RESULT: PASS - {args.copy}: no deterministic violation found against profile "
          f"signature-upsell-eight-section (instance={doc['instance']}, 8 sections, CTA in every "
          "section, 7 distinct reasons, native action-binding form; "
          f"binding_verification={report['binding_verification']}). A PASS does NOT prove the "
          "absence of invented scarcity or proof and does NOT prove the native binding exists: "
          "independent substantive review (rubric R4/R10) and S80-06 native-binding evidence "
          "remain required.")
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
