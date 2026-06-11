#!/usr/bin/env python3
# _qc_get.py — extracted getter from qc-completeness.sh.
#
# Externalized v11.18.4 for stock-macOS bash 3.2.57 compatibility (python-in-$()
# parse hazard). Reads a JSON object from stdin and prints the string value of
# the key named in argv[1], or empty string if absent/null. Byte-equivalent to
# the former inline:  python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('KEY') or '')"
import json
import sys

key = sys.argv[1] if len(sys.argv) > 1 else ""
d = json.load(sys.stdin)
print(d.get(key) or "")
