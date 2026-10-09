"""delivery_variants package: text/product checks, aspect variants, deliverable writers.

Directive 17.8 (acceptance) + 20.4 (deliverables: campaign-manifest.json,
cost-report.json, provenance.json). Stdlib only.
"""
from .caption_srt import (
    check_captions_srt,
    export_captions_srt,
    parse_srt,
    srt_file_name,
)
from .checks import (
    CTA_HOLD_MIN_SECONDS,
    MOBILE_RENDITION_WIDTH_PX,
    check_captions,
    check_cta_hold,
    check_exact_copy,
    check_mobile_readability,
    text_product_check,
)
from .manifests import (
    ManifestError,
    sha256_file,
    verify_binding,
    write_campaign_manifest,
    write_cost_report,
    write_provenance,
)
from .song_files import (
    build_song_files,
    check_song_files,
    write_song_docs,
)
from .variants import (
    ASPECTS,
    VariantError,
    build_variant_plan,
    expected_dimensions,
    safe_area,
)

SCHEMA_VERSION = "1.0.0"
TOOL_VERSION = "1.0.0"

__all__ = [
    "check_captions_srt",
    "export_captions_srt",
    "parse_srt",
    "srt_file_name",
    "CTA_HOLD_MIN_SECONDS",
    "MOBILE_RENDITION_WIDTH_PX",
    "check_captions",
    "check_cta_hold",
    "check_exact_copy",
    "check_mobile_readability",
    "text_product_check",
    "ManifestError",
    "sha256_file",
    "verify_binding",
    "write_campaign_manifest",
    "write_cost_report",
    "write_provenance",
    "build_song_files",
    "check_song_files",
    "write_song_docs",
    "ASPECTS",
    "VariantError",
    "build_variant_plan",
    "expected_dimensions",
    "safe_area",
]
