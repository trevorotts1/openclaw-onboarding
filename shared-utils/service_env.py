"""Single-line literal dotenv values shared by Next and process-manager callers.

This is deliberately not a shell evaluator. Unsupported/interpolated input fails
closed instead of guessing a different secret or installation path. JSON settings
can repair the previous writer's JSON-string wrapper before being rewritten.
"""
import json
import re
from pathlib import Path

_KEY = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')
_LINE_BREAKS = '\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029'


def _single_line(value):
    if '\x00' in value or any(char in value for char in _LINE_BREAKS):
        raise ValueError('Service environment values must be single-line literals')


def decode_value(raw, *, structured=False):
    """Decode our literal format, plus ordinary non-interpolated dotenv lines."""
    _single_line(raw)
    value = raw.strip()
    if structured and value.startswith('"') and value.endswith('"'):
        # Only JSON-valued keys establish that this is the old JSON wrapper.
        # json.loads on an ordinary double-quoted dotenv value would wrongly
        # interpret backslash-t, escaped backslashes and escaped quotes.
        try:
            decoded = json.loads(value)
            if isinstance(decoded, str) and isinstance(json.loads(decoded), (dict, list)):
                return decoded
        except (ValueError, TypeError):
            pass
    if value.startswith(("'", '"', '`')):
        quote = value[0]
        # Writer always chooses an absent delimiter. Also accept dotenv's
        # escaped delimiters on reads without treating them as shell escapes.
        end = next((i for i in range(1, len(value))
                    if value[i] == quote and value[i - 1] != '\\'), None)
        # A terminal backslash is literal in dotenv single/backtick quotes.
        if end is None and len(value) > 1 and value[-1] == quote:
            end = len(value) - 1
        if end is None or (value[end + 1:].strip() and not value[end + 1:].lstrip().startswith('#')):
            raise ValueError('Unsupported quoted service environment value')
        value = value[1:end]
        if quote == '"':
            value = value.replace('\\n', '\n').replace('\\r', '\r')
    else:
        value = value.split('#', 1)[0].rstrip()
    _single_line(value)
    if re.search(r'(?<!\\)\$\{?[A-Za-z0-9_]', value):
        raise ValueError('Interpolated service environment values require explicit literal configuration')
    return value.replace('\\$', '$')


def read_env(path):
    values = {}
    if Path(path).exists():
        # Split only actual newline records; Unicode separators inside values
        # must be rejected, never silently turned into another assignment.
        for line in Path(path).read_text().split('\n'):
            line = line.removesuffix('\r')
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            if '=' not in line:
                raise ValueError('Unsupported service environment line')
            key, raw = line.split('=', 1)
            key = key.strip()
            if not _KEY.fullmatch(key):
                raise ValueError('Invalid environment key')
            value = decode_value(raw, structured=key.endswith('_JSON'))
            if key in values and values[key] != value:
                raise ValueError('Conflicting duplicate service environment key')
            values[key] = value
    return values


def encode_value(value, *, structured=False):
    value = str(value)
    if structured:
        try:
            parsed = json.loads(value)
        except ValueError:
            raise ValueError('Invalid structured service environment value') from None
        if not isinstance(parsed, (dict, list)):
            raise ValueError('Structured service environment values must be objects or arrays')
        # Preserve JSON semantics, not formatting. Escapes keep comments,
        # interpolation, delimiters and Unicode line separators out of dotenv.
        value = json.dumps(parsed, ensure_ascii=True, separators=(',', ':'), allow_nan=False)
        for char in ("'", '`', '#', '$'):
            value = value.replace(char, '\\u%04x' % ord(char))
        return value
    _single_line(value)
    value = value.replace('$', '\\$')
    for quote in ("'", '`'):
        if quote not in value and not value.endswith('\\'):
            return quote + value + quote
    if '"' not in value and '\\n' not in value and '\\r' not in value and not value.endswith('\\'):
        return '"' + value + '"'
    if '#' not in value and not value.startswith(("'", '"', '`')) and value.strip() == value:
        return value
    raise ValueError('Value cannot be represented losslessly in a dotenv line')


def encode_assignment(key, value):
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        raise ValueError('Invalid environment key')
    return key + '=' + encode_value(value, structured=key.endswith('_JSON'))
