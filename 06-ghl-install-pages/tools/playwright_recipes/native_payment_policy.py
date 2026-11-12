"""Lane-independent constraints for GHL page and payment work.

A policy is an instruction to the executing host, not evidence that a native
component was installed or that a payment succeeded.
"""
from collections.abc import Mapping
import re

_PREFIXES = ('funnel', 'website', 'site', 'page', 'checkout', 'payment', 'orderform', 'order_form', 'upsell', 'downsell', 'form')
_POLICY = {
    'required': True,
    'implementation': 'ghl_native_payment_components',
    'instruction': ('Use native GHL checkout, order forms, one-click upsells, downsells and payment buttons. '
                    'Arrange surrounding design around native components; never replace them with custom, '
                    'synthetic, externally hosted or embedded payment implementations. Links to native GHL checkout are allowed.'),
    'verification': ('Independent native component preservation/readback evidence and an independent payment test are required where applicable; '
                     'an editor save is not a payment test.'),
}


def payment_policy(operation):
    """Return the native-payment policy for a relevant operation, else None."""
    if isinstance(operation, str) and operation.lower().split('.')[0].startswith(_PREFIXES):
        return dict(_POLICY)
    return None


def apply_payment_policy(operation, route):
    """Attach the same policy to every selected or recovery route."""
    result = dict(route)
    policy = payment_policy(operation)
    if policy:
        result['native_payment_policy'] = policy
    return result


# Match explicit implementations, not ordinary HTML/CSS or a link to a checkout.
_REPLACEMENT = re.compile(
    r'\b(?:custom|synthetic|external|externally hosted|third[- ]party|embedded|embed)\s+'
    r'(?:payment|checkout|order\s*form|orderform|upsell|downsell|payment\s+button)s?\b'
    r'|\b(?:payment|checkout|order\s*form|orderform|upsell|downsell)\s+'
    r'(?:implementation|component|form|widget|processor)?\s*(?:built|implemented|hosted|embedded)\s+'
    r'(?:externally|outside|from scratch|with custom code)\b'
    r'|\b(?:stripe elements|paypal buttons?|stripe checkout|payment iframe)\b'
    r'|\b(?:js\.stripe\.com|checkout\.stripe\.com|paypal\.com/sdk/js)\b'
    r'|<(?:input|iframe)\b[^>]*(?:card[-_ ]?number|cardnumber|cc-number|payment|checkout)[^>]*>', re.I)
_KEY = re.compile(r'(?:payment|checkout|order.?form|upsell|downsell)', re.I)
_IMPLEMENTATION_KEY = re.compile(r'(?:implementation|provider|processor|component|integration|method|mode|type|source)', re.I)
_EXECUTABLE = re.compile(r'\b(?:js\.stripe\.com|checkout\.stripe\.com|paypal\.com/sdk/js)\b|<(?:input|iframe)\b[^>]*(?:card[-_ ]?number|cardnumber|cc-number|payment|checkout)[^>]*>', re.I)
_REQUEST = re.compile(r'\b(?:build|create|implement|install|use|replace\s+with)\s+(?:an?\s+)?(?:custom|synthetic|external|embedded|third[- ]party)\s+(?:payment|checkout|order\s*form|orderform)', re.I)
_BAD_VALUE = re.compile(r'^(?:custom|synthetic|external|externally.hosted|third.party|embedded|embed|iframe|stripe.elements)$', re.I)


def validate_payment_inputs(operation, inputs):
    """Return a refusal reason for explicit non-native payment requests, else None."""
    if not payment_policy(operation) or not isinstance(inputs, Mapping):
        return None
    def invalid(value, key=''):
        if isinstance(value, Mapping):
            return any(invalid(v, str(k)) for k, v in value.items())
        if isinstance(value, (list, tuple)):
            return any(invalid(v, key) for v in value)
        if isinstance(value, str):
            return bool(_EXECUTABLE.search(value) or _REQUEST.search(value) or
                        (_KEY.search(key) and (_BAD_VALUE.fullmatch(value.strip()) or
                         (_IMPLEMENTATION_KEY.search(key) and _REPLACEMENT.search(value)))))
        return False
    if invalid(inputs):
        return 'Payment components must be native GHL components; custom, external, synthetic or embedded replacements are not permitted.'
    return None
