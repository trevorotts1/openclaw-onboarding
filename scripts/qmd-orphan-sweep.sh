#!/usr/bin/env bash
# Retired 2026-09-17: .qmd filename extension is not evidence of an obsolete
# QMD memory index. The former sweep could delete unrelated Quarto documents.
printf '%s\n' 'RETIRED: qmd-orphan-sweep performs no cleanup. Preserve source documents; use reviewed memory-store migration.' >&2
exit 75
