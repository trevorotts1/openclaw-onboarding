#!/usr/bin/env python3
"""S71-03 no-offer-pricing gate tests (packet doc 07 section 3; A06 L1).

The gate is an extension of scripts/validate_public_copy.py, enabled with
--no-offer-pricing for the signature_launch_landing profile. It fails on
offer pricing on any public surface (visible copy, image alt text, title
attributes, accessibility labels, page title, meta content, structured
data) and passes on legitimate numbers (dates, phone numbers, seat/session
counts, non-price percentages, deadline countdowns). Every pricing signal
class is exercised on every surface class with a named reason.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
SCRIPT = SKILL_ROOT / "scripts" / "validate_public_copy.py"
FIXTURES = HERE / "fixtures"

sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import validate_public_copy as vpc  # noqa: E402


def run_cli(files, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, *[str(f) for f in files]],
        capture_output=True, text=True)


def price_labels(text):
    errors, _warnings = vpc.scan(text, [], no_offer_pricing=True)
    return [label for kind, (_line, label, _sample) in errors if kind == "price"]


SIGNALS = {
    "currency amount": "Enroll today for $497 and keep the momentum",
    "bare price figure": "The tuition is 1500 for the full program",
    "per-period price": "Get every session for 199 per month",
    "installment amount": "Split it into 3 payments of $199",
    "discount amount": "Save $500 when you join this week",
    "discount percentage": "Get 50% off the regular enrollment",
    "price anchor amount": "A $2,000 value, yours when you register",
    "spelled-out price": "Get started for five hundred dollars",
}

SURFACES = {
    "visible copy": lambda s: f"<html><body><p>{s}</p></body></html>",
    "image alt text": lambda s: f'<img src="hero.png" alt="{s}">',
    "accessibility label": lambda s: f'<button aria-label="{s}">Join</button>',
    "title attribute": lambda s: f'<span title="{s}">i</span>',
    "page title (structured content)":
        lambda s: f"<html><head><title>{s}</title></head><body>Welcome</body></html>",
    "meta content (structured content)":
        lambda s: (f'<html><head><meta name="description" content="{s}">'
                   f"</head><body>Welcome</body></html>"),
    "structured data (JSON-LD)":
        lambda s: ('<script type="application/ld+json">{"@type": "Product", '
                   f'"name": "{s}"}}</script>'),
}

CLEAN_TEXTS = [
    "Call us at (404) 545-4552 or +1 917-415-2338 any weekday.",
    "The next cohort begins October 15, 2026; doors close March 3.",
    "Only 48 hours left - enrollment closes in 3 days.",
    "We meet 3 times per week for live working sessions.",
    "12 live sessions, 8 modules, and 200 seats for founders.",
    "92% of our graduates report new revenue within 90 days.",
    "Save 20% of your time every week with the planning system.",
    "Join a total of 500 founders inside the room.",
    "A community worth joining, at your own pace.",
    "The countdown shows 02:14:59 until the doors close.",
]


def test_signal_on_every_surface():
    for surface, wrap in SURFACES.items():
        for signal, example in SIGNALS.items():
            want = f"offer price in {surface}: {signal}"
            got = price_labels(wrap(example))
            assert want in got, f"{surface} / {signal}: wanted {want!r}, got {got}"


def test_structured_price_key_fires():
    doc = ('<script type="application/ld+json">'
           '{"@type": "Offer", "price": 497}</script>')
    assert "offer price in structured data (JSON-LD): bare price figure" in price_labels(doc)


def test_markdown_visible_copy_fires():
    for signal, example in SIGNALS.items():
        want = f"offer price in visible copy: {signal}"
        assert want in price_labels(example), (signal, example)


def test_clean_texts_pass():
    for text in CLEAN_TEXTS:
        got = price_labels(text)
        assert got == [], f"clean text flagged: {text!r} -> {got}"


def test_gate_off_by_default():
    errors, _warnings = vpc.scan("Enroll today for $497", [])
    assert [e for e in errors if e[0] == "price"] == []


def test_valid_fixtures_pass_with_flag():
    result = run_cli([FIXTURES / "public-copy-noprice-valid.html",
                      FIXTURES / "public-copy-noprice-valid.md"],
                     "--no-offer-pricing")
    assert result.returncode == 0, result.stdout + result.stderr


def test_invalid_fixture_fails_with_flag_and_named_reasons():
    result = run_cli([FIXTURES / "public-copy-noprice-invalid.html"],
                     "--no-offer-pricing")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "offer pricing detected" in result.stdout
    for want in (
        "offer price in page title (structured content)",
        "offer price in meta content (structured content): per-period price",
        "offer price in meta content (structured content): discount amount",
        "offer price in structured data (JSON-LD)",
        "offer price in image alt text: price anchor amount",
        "offer price in accessibility label: installment amount",
        "offer price in visible copy: price anchor amount",
        "offer price in visible copy: bare price figure",
    ):
        assert want in result.stdout, (want, result.stdout)


def test_invalid_fixture_passes_without_flag():
    # The rule is profile-scoped: without --no-offer-pricing the legacy
    # behavior is unchanged, so this fixture (pricing, no private markers)
    # still passes.
    result = run_cli([FIXTURES / "public-copy-noprice-invalid.html"])
    assert result.returncode == 0, result.stdout + result.stderr


def test_flag_works_via_cli_on_temp_file():
    with tempfile.TemporaryDirectory() as tmp:
        clean = Path(tmp) / "clean.md"
        clean.write_text("Cohort starts October 15, 2026. Only 200 seats.", encoding="utf-8")
        result = run_cli([clean], "--no-offer-pricing")
        assert result.returncode == 0, result.stdout + result.stderr


def test_aria_description_surface_fires():
    # Review observation O2: aria-description is a named accessibility
    # surface (the implementation maps it to "accessibility label", like
    # aria-label), but only aria-label had author coverage. Exercise every
    # signal class on it so a refactor cannot silently lose the surface.
    for signal, example in SIGNALS.items():
        doc = f'<button aria-description="{example}">Join</button>'
        want = f"offer price in accessibility label: {signal}"
        got = price_labels(doc)
        assert want in got, f"aria-description / {signal}: wanted {want!r}, got {got}"


def test_star_rating_is_not_pricing():
    # Review defect D1: a star rating is a statistic denominated in stars,
    # not a rate price; the bare-figure finding must not fire on it.
    for text in (
        "Members give us a satisfaction rate of 5 stars.",
        "Members give us a satisfaction rate of 1 star.",
    ):
        got = price_labels(text)
        assert got == [], f"star rating flagged: {text!r} -> {got}"


def test_star_rating_with_real_price_still_flags():
    # D1 guardrail: the rating suppresses only itself. A real price anchor
    # in the same sentence still fails, with exactly that one finding.
    got = price_labels("A satisfaction rate of 5 stars, normally $500.")
    assert got == ["offer price in visible copy: price anchor amount"], got


def test_spelled_out_percent_is_not_pricing():
    # Review defect D2: spelled-out "percent" / "per cent" suppress exactly
    # like the "%" symbol; the same sentence must not pass or fail on
    # typography alone.
    for text in (
        "Our completion rate of 98 percent speaks for itself.",
        "Our completion rate of 98 per cent speaks for itself.",
        "Our completion rate of 98% speaks for itself.",
        "Save 20 percent of your time every week with the planning system.",
        "92 percent of our graduates report new revenue within 90 days.",
    ):
        got = price_labels(text)
        assert got == [], f"spelled-out percent flagged: {text!r} -> {got}"


def test_spelled_out_percent_discount_still_flags():
    # D2 guardrail: suppression covers statistics, never discounts. A
    # spelled-out "percent off" is a discount percentage, exactly like
    # the symbol form.
    for text in (
        "Get 98 percent off today only.",
        "Get 50 per cent off this week.",
        "Get 50% off the regular enrollment.",
    ):
        got = price_labels(text)
        assert "offer price in visible copy: discount percentage" in got, (text, got)


def test_currency_marked_rate_still_flags():
    # D1/D2 guardrail: suppression applies only to bare figures with no
    # currency mark, so a currency-marked rate is still a price.
    got = price_labels("The rate of $98 per month applies.")
    assert "offer price in visible copy: bare price figure" in got, got


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("[OK]", t.__name__)
    print(f"\n{len(tests)} checks passed")
