"""Validate access destinations for a Skill 82 order view (S82-07).

Access is the point where a confirmation page can quietly become a
security hole: a link that merely *looks* protected, a URL that carries
the buyer's identity as a query claim, or an access block for something
the buyer never purchased. This validator checks a link manifest against
the resolved order view:

- every access destination must be https (a `mailto:` support link is
  not an access block and is exempt from the https rule);
- no destination URL may carry query parameters that claim identity or
  entitlement (email, name, entitlement, `vip`-style flags, plan/tier,
  offer): a URL parameter is never authority for access. Parameter keys
  are normalized before matching (repeated percent-decoding, control
  characters stripped, case folded, Cyrillic/Greek lookalikes folded
  to Latin) so an encoded or homoglyph claim key cannot slip past the
  blocklist (F-02);
- every access destination must declare that it independently
  authorizes the buyer (`destination_independently_authorizes: true`).
  A page-render condition is never the security boundary;
- every access block must belong to an entitlement that is actually in
  the view (on a displayed item or an access block the resolver built
  from the verified snapshot). Anything else is an unpurchased access
  path.

The manifest shape (one entry per rendered link):

    {"schema_version": "1.0", "test_only": true,
     "links": [{"entitlement_id": "base-a" | null,
                "kind": "access" | "support" | "manage_purchase",
                "url": "https://...",
                "destination_independently_authorizes": true | false | null}]}

Stdlib only. Exit 0 = PASS, 1 = FAIL with named codes, one per line.
"""

import os
import sys
import unicodedata
from urllib.parse import parse_qsl, unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ACCESS_KINDS = {"access", "download", "schedule_included_service"}

# Query parameter names that would turn a URL into an identity or
# entitlement claim. None of these may appear on any rendered link.
CLAIM_PARAM_KEYS = {
    "email", "email_address", "name", "first_name", "last_name",
    "full_name", "buyer", "buyer_email", "contact", "contact_id",
    "entitlement", "entitlements", "entitlement_id", "vip", "is_vip",
    "plan", "tier", "level", "access", "access_level", "grant",
    "offer", "offer_id", "product", "product_id", "premium", "member",
}

# Unicode lookalikes folded onto their Latin twins before the claim
# comparison (F-02). Only the letters that actually occur in claim
# words are mapped; keys are casefolded first, so only the lowercase
# forms are needed. This is a folding for the claim-key comparison
# only — it never rewrites the URL.
_CONFUSABLES = {
    # Cyrillic small letters that look like Latin ones
    "\u0430": "a",  # CYRILLIC SMALL LETTER A
    "\u0441": "c",  # CYRILLIC SMALL LETTER ES
    "\u0435": "e",  # CYRILLIC SMALL LETTER IE
    "\u0456": "i",  # CYRILLIC SMALL LETTER BYELORUSSIAN-UKRAINIAN I
    "\u043e": "o",  # CYRILLIC SMALL LETTER O
    "\u0440": "p",  # CYRILLIC SMALL LETTER ER
    "\u0455": "s",  # CYRILLIC SMALL LETTER DZE
    "\u0445": "x",  # CYRILLIC SMALL LETTER HA
    "\u0443": "y",  # CYRILLIC SMALL LETTER U
    # Greek small letters that look like Latin ones
    "\u03b1": "a",  # GREEK SMALL LETTER ALPHA
    "\u03b5": "e",  # GREEK SMALL LETTER EPSILON
    "\u03b9": "i",  # GREEK SMALL LETTER IOTA
    "\u03ba": "k",  # GREEK SMALL LETTER KAPPA
    "\u03bf": "o",  # GREEK SMALL LETTER OMICRON
    "\u03c1": "p",  # GREEK SMALL LETTER RHO
    "\u03c7": "x",  # GREEK SMALL LETTER CHI
    "\u03c5": "y",  # GREEK SMALL LETTER UPSILON
}

# Bound on repeated percent-decoding: enough to collapse the double-
# and triple-encoded keys seen in practice, never an open-ended loop.
_MAX_DECODE_ROUNDS = 3


def _normalize_param_key(key):
    """Canonicalize a query parameter key for the claim comparison.

    Steps, in order: repeatedly percent-decode (bounded) so an encoded
    or double-encoded claim key collapses to its real name; drop
    control and format characters (null bytes, C0/C1 controls,
    zero-width characters) that a downstream parser might ignore;
    casefold; fold the Cyrillic/Greek lookalikes in _CONFUSABLES onto
    their Latin twins. Only key *names* are ever compared — parameter
    values are not claims and are never inspected.
    """
    normalized = key
    for _ in range(_MAX_DECODE_ROUNDS):
        decoded = unquote(normalized)
        if decoded == normalized:
            break
        normalized = decoded
    normalized = "".join(
        ch for ch in normalized
        if unicodedata.category(ch) not in ("Cc", "Cf"))
    normalized = normalized.casefold()
    return "".join(_CONFUSABLES.get(ch, ch) for ch in normalized)


def _view_entitlements(view):
    entitlements = set()
    for item in view.get("items") or []:
        entitlements.update(item.get("entitlement_ids") or [])
    for block in view.get("access_blocks") or []:
        if block.get("entitlement_id"):
            entitlements.add(block["entitlement_id"])
    return entitlements


def validate_access(view, link_manifest):
    errors = []
    if not isinstance(view, dict):
        return ["invalid_view: order view must be an object"]
    if not isinstance(link_manifest, dict) or not isinstance(
            link_manifest.get("links"), list):
        return ["invalid_link_manifest: manifest must be an object with a "
                "'links' list"]

    view_entitlements = _view_entitlements(view)

    for idx, link in enumerate(link_manifest["links"]):
        where = f"links[{idx}]"
        if not isinstance(link, dict):
            errors.append(f"invalid_link: {where} must be an object")
            continue
        kind = link.get("kind") or "access"
        url = link.get("url")
        entitlement_id = link.get("entitlement_id")
        if not url or not isinstance(url, str):
            errors.append(f"missing_destination: {where} has no URL")
            continue
        parsed = urlparse(url)
        is_access = kind in ACCESS_KINDS or entitlement_id is not None

        # --- URL must never carry identity / entitlement claims ----------
        for key, _value in parse_qsl(parsed.query, keep_blank_values=True):
            if _normalize_param_key(key) in CLAIM_PARAM_KEYS:
                errors.append(
                    f"claim_in_url: {where} URL carries query parameter "
                    f"{key!r}; identity and entitlement claims in a URL "
                    "are never authority for access"
                )

        if parsed.scheme == "mailto":
            if is_access and entitlement_id is not None:
                errors.append(
                    f"invalid_destination: {where} is a mailto: link "
                    "carrying an entitlement; mailto is a support "
                    "channel, never an access block"
                )
            continue  # support mailto: exempt from https + auth-flag rules

        # --- Access destinations must be https ---------------------------
        if parsed.scheme != "https":
            if is_access:
                errors.append(
                    f"insecure_destination: {where} access destination "
                    f"{url!r} is not https"
                )
            else:
                errors.append(
                    f"insecure_destination: {where} destination {url!r} "
                    "is not https"
                )
            continue

        if not is_access:
            continue

        # --- Destination must independently authorize the buyer ---------
        if link.get("destination_independently_authorizes") is not True:
            errors.append(
                f"missing_independent_authorization: {where} access "
                f"destination for entitlement {entitlement_id!r} does "
                "not declare that it independently authorizes the "
                "buyer; a page-render condition is not a security "
                "boundary"
            )

        # --- Access block must belong to this view -----------------------
        if entitlement_id is None:
            errors.append(
                f"access_without_entitlement: {where} is an access "
                "link with no entitlement_id; access blocks are keyed "
                "to purchased entitlements"
            )
        elif entitlement_id not in view_entitlements:
            errors.append(
                f"access_for_unviewed_entitlement: {where} grants an "
                f"access path for entitlement {entitlement_id!r}, "
                "which is not in the verified order view"
            )
    return errors


def _load(path):
    import json
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--view", required=True)
    parser.add_argument("--links", required=True)
    args = parser.parse_args(argv)
    errors = validate_access(_load(args.view), _load(args.links))
    for err in errors:
        print(f"FAIL: {err}")
    if errors:
        return 1
    print("PASS: every access destination is https, claim-free, "
          "independently authorizing, and keyed to a viewed entitlement")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
