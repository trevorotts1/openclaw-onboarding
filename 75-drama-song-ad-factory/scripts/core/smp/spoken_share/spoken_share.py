#!/usr/bin/env python3
"""Thin re-export of core spoken_share (D15) for scripts/core/smp/. Skill 74 only; stdlib only."""
from __future__ import annotations
import importlib.util as _ilu, os as _os, sys as _sys
_n, _s, _p = "_smp_core_spoken_share", None, None
if _n in _sys.modules:
    _m = _sys.modules[_n]
else:
    _p = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "spoken_share", "spoken_share.py"))
    _s = _ilu.spec_from_file_location(_n, _p)
    _m = _ilu.module_from_spec(_s)
    _s.loader.exec_module(_m)
    _sys.modules[_n] = _m
globals().update({k: v for k, v in vars(_m).items() if not k.startswith("_") or k == "__all__"})
del _m, _s, _p, _ilu, _os, _sys, _n