"""ready_post_kit package: the READY-TO-POST KIT PDF for a delivered ad.

Deliverable in the delivery folder: ``07 - Ready-to-Post Kit.pdf`` (the
client-facing kit: which version to post where, the link, a caption and a
hashtag set per platform, and the YouTube title/description/tags). The same
kit as data, ``07 - Ready-to-Post Kit.json``, is QC / manifest material, so
it goes to the run's QC folder (``<run>/qc``) and never beside the PDF.
Nothing on the page is under 12 pt, and no tool name, model name, dollar
amount or income promise can reach it (fail closed: KIT_BANNED_TEXT).
"""
from .ready_post_kit import (  # noqa: F401
    JSON_NAME,
    KIT_NUMBER,
    MIN_PT,
    PDF_NAME,
    QC_NAME,
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
