#!/usr/bin/env python3
# PRD 1.8 wrapper (impl in shared-utils/embedding_engine.py); a71f6bbd: multi-candidate sys.path resolve + fail-loud
import sys, os; _h=os.path.dirname(os.path.abspath(__file__)); _c=[os.path.join(_h,r) for r in ("shared-utils","../skills/shared-utils","../../shared-utils","../../../shared-utils","../shared-utils")]+[os.path.expanduser("~/.openclaw/skills/shared-utils"),"/data/.openclaw/skills/shared-utils",os.path.expanduser("~/.openclaw/onboarding/shared-utils")]
_r=next((os.path.realpath(p) for p in _c if os.path.isfile(os.path.join(p,"embedding_engine.py"))),None)
sys.exit(sys.stderr.write("[gemini-search] FATAL: embedding_engine.py not found in %r\n" % _c) or 2) if _r is None else sys.path.insert(0,_r)
from embedding_engine import _search_main as main; main()
