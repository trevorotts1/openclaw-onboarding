# presentation_job — the process engine for the Presentation Department.
#
# PRES-039 engine provenance (authoritative-source preflight lives in
# engine_origin.py; cmd_new/cmd dispatch record + verify it per run):
# the canonical distributable engine is owned by ONB at
# 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/
# until the PRES package cutover (PRES-049/WF16). THIS tree is that
# canonical source: the authoritative copy every other copy is generated
# or vendored from. The CC-root copy is a non-authoritative vendored
# duplicate of this package: it must never be edited independently
# (generate vendor output from one source with manifest hashes + parity
# CI), must record its origin in every run, and dispatch must fail closed
# on a stale PYTHONPATH copy rather than silently importing it. Do NOT
# delete the CC duplicate until every caller/installer is migrated and
# rollback is tested.
#
# These constants are import-free data ONLY: this module must never grow
# an import, because engine_origin reads these values to identify the
# package without executing it.
ENGINE_DISTRIBUTOR = "ONB"
ENGINE_SOURCE_PATH = (
    "23-ai-workforce-blueprint/templates/role-library/presentations/"
    "scripts/presentation_job"
)
ENGINE_COPY_ROLE = "canonical-source-authoritative"
ENGINE_CUTOVER_OWNER = "PRES"
ENGINE_CUTOVER_TASK = "PRES-049"
ENGINE_DEDUP_TASK = "PRES-039"
