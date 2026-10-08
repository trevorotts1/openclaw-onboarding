"""catalog_calculator.extensions — price-card totals with lip-sync, voice
packs, both shapes and the D26 batch total (unit BO-PKG2-U1).

Extends unit V2-W0-U2's catalog calculator; all rates still come from Skill 74
``price`` only. See price_extension.py for the rules and README.md for the API.
"""
try:  # package import (core.catalog_calculator.extensions)
    from .price_extension import (BATCH_UNIT_NAME, LIPSYNC_ROSTER, RETAKE_RATE,
                                  UNIT_NAME, find_calculator,
                                  price_batch, price_card_ext,
                                  retake_allowance)
except ImportError:  # script import from inside this directory
    from price_extension import (BATCH_UNIT_NAME, LIPSYNC_ROSTER, RETAKE_RATE,
                                 UNIT_NAME, find_calculator, price_batch,
                                 price_card_ext, retake_allowance)

__all__ = ["price_card_ext", "price_batch", "find_calculator",
           "retake_allowance", "UNIT_NAME", "BATCH_UNIT_NAME",
           "LIPSYNC_ROSTER", "RETAKE_RATE"]
