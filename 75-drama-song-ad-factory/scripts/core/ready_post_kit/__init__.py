"""ready_post_kit package: the READY-TO-POST KIT PDF for a delivered ad.

Deliverables in the delivery folder: ``07 - Ready-to-Post Kit.pdf`` (the
client-facing kit: which version to post where, the link, a caption and a
hashtag set per platform, and the YouTube title/description/tags) plus the
same kit as ``07 - Ready-to-Post Kit.json``. Nothing on the page is under
12 pt, and no tool name, model name, dollar amount or income promise can
reach it (fail closed: KIT_BANNED_TEXT).
"""
from .ready_post_kit import (  # noqa: F401
    JSON_NAME,
    KIT_NUMBER,
    MIN_PT,
    PDF_NAME,
    KitError,
    audit_kit,
    audit_text,
    build_kit,
    checklist_summary,
    layout,
    load_delivery,
    load_run,
    main,
    placement_rows,
    prepare,
    render_pdf,
    resolve_link,
    write_kit,
)
