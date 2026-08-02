#!/usr/bin/env bash
set -euo pipefail
# Verify SKILL.md frontmatter is strict-parseable YAML.
# FIX-10: description field uses block scalar (|) to avoid colon-space parse errors.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_MD="$(dirname "$SCRIPT_DIR")/SKILL.md"

python3 -c "
import yaml, re, sys
with open('$SKILL_MD') as f:
    content = f.read()
match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
if not match:
    print('FAIL: could not extract frontmatter from SKILL.md', file=sys.stderr)
    sys.exit(1)
parsed = yaml.safe_load(match.group(1))
print('PASS: frontmatter parses as valid YAML:', list(parsed.keys()))
"
