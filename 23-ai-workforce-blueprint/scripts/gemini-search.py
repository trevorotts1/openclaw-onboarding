#!/usr/bin/env python3
# PRD 1.8 wrapper — real implementation is in shared-utils/embedding_engine.py
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared-utils"))
from embedding_engine import _search_main as main; main()
