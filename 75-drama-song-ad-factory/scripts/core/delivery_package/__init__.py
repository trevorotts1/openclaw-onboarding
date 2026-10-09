"""delivery_package: the delivery-folder contract for a client run (DEL-12).

The canonical numbered file-name list of all 12 package items
(``package_items``) and the one-page client welcome sheet rendered from it
(``welcome_sheet``). ``core/delivery_checklist`` imports the same constant,
so the delivery gate and the printed page can never name a file differently.

stdlib only, no network, no provider call, no spend, no absolute operator
path. Both distributions carry this package byte-identically.
"""
from .package_items import (
    DELIVERY_FOLDER,
    MIN_PDF_POINT_SIZE,
    PACKAGE_FILES,
    PACKAGE_ITEM_COUNT,
    PACKAGE_ITEMS,
    WELCOME_SHEET_FILE,
    files_for,
)
from .welcome_sheet import (  # noqa: F401
    WelcomeSheetError,
    build_welcome_sheet,
    pdf_bytes,
    text_width,
    wrap,
)

__all__ = [
    "DELIVERY_FOLDER",
    "MIN_PDF_POINT_SIZE",
    "PACKAGE_FILES",
    "PACKAGE_ITEM_COUNT",
    "PACKAGE_ITEMS",
    "WELCOME_SHEET_FILE",
    "files_for",
    "WelcomeSheetError",
    "build_welcome_sheet",
    "pdf_bytes",
    "text_width",
    "wrap",
]
