#!/usr/bin/env bash
# legacy = no '### Phase N' + no 'declares' + no 'model-tier:'.
# New-style marks are declares/model-tier, so a file with those but no phases
# is BROKEN and is refused here; content decides legacy, never mtime (mtime lies after a copy).

set -euo pipefail

usage() {
    printf 'Usage: bash scripts/33-migrate-legacy-playbooks.sh <dir> [--write]\n' >&2
    exit 2
}

[[ $# -ge 1 ]] || usage

directory=$1
shift
write=false

while (($#)); do
    case "$1" in
        --write)
            [[ "$write" == false ]] || {
                printf 'ERROR: unsupported option: %s\n' "$1" >&2
                usage
            }
            write=true
            ;;
        *)
            printf 'ERROR: unsupported option: %s\n' "$1" >&2
            usage
            ;;
    esac
    shift
done

[[ -d "$directory" ]] || {
    printf 'ERROR: not an existing directory: %s\n' "$directory" >&2
    exit 1
}

directory=$(cd -- "$directory" && pwd -P)

exec python3 - "$directory" "$write" <<'PYTHON'
import difflib
import re
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
write = sys.argv[2] == "true"

SKIP_NAMES = {"registry.md"}
SKIP_SUFFIXES = (
    "--build-with-ai-prompt.md",
    "--workflow-ai-prompt.md",
    "--verification-checklist.md",
    "--ghl-side.md",
)

PHASE_RE = re.compile(r"^\s{0,3}#{2,4}\s*Phase\s*\d", re.IGNORECASE)
SECTION_RE = re.compile(r"^##\s+(\d+)\.\s+(.+?)\s*$")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}(?:\s|$)")
DECLARES_RE = re.compile(r"^\s*declares\s*$")
MODEL_TIER_RE = re.compile(r"^\s*model-tier\s*:")

SKELETON = [
    "declares",
    "tools-used:",
    "exits-used:",
    "fields-used:",
    "tags-used:",
    "calendars:",
    "pipeline:",
    "stage-map:",
]

WARN_EMPTY = (
    "  [WARN] declares fields left EMPTY "
    "(tools-used, exits-used, fields-used, tags-used, calendars, pipeline, stage-map) "
    "— fill from the playbook's real content; never invent tags, fields, calendars, ids or stages."
)


def inside_root(path):
    try:
        return path.resolve().is_relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return False


def safe_read(path):
    if not inside_root(path):
        raise ValueError(f"path escape refused: {path}")
    return path.read_bytes()


def remove_fences(lines):
    return [
        line for line in lines
        if not line.lstrip().startswith("```")
    ]


def classify(lines):
    visible = remove_fences(lines)
    if any(PHASE_RE.search(line.rstrip("\r\n")) for line in visible):
        return "NEW"
    if any(
        DECLARES_RE.match(line.rstrip("\r\n"))
        or MODEL_TIER_RE.match(line.rstrip("\r\n"))
        for line in visible
    ):
        return "BROKEN"
    return "LEGACY"


def newline_for(text):
    match = re.search(r"\r\n|\n|\r", text)
    return match.group(0) if match else "\n"


def line_content(line):
    return line.rstrip("\r\n")


def convert(original):
    lines = original.splitlines(keepends=True)
    newline = newline_for(original)

    section_positions = []
    in_fence = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = SECTION_RE.match(line_content(line))
        if match:
            section_positions.append((index, match.group(1), match.group(2)))

    phases = []
    for index, number, title in section_positions:
        body_has_content = False
        in_fence = False

        for line in lines[index + 1:]:
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue

            content = line_content(line)
            if HEADING_RE.match(content):
                break
            if content.strip():
                body_has_content = True
                break

        if body_has_content:
            phases.append((index, title))

    phase_insertions = {
        index: f"### Phase {sequence} - {title}{newline}"
        for sequence, (index, title) in enumerate(phases, start=1)
    }

    first_heading = None
    in_fence = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if re.match(r"^## ", line_content(line)):
            first_heading = index
            break

    skeleton_lines = [item + newline for item in SKELETON]
    if first_heading is not None:
        skeleton_block = [newline] + skeleton_lines + [newline]
        insertion_index = first_heading
    else:
        skeleton_block = []
        if lines:
            if not lines[-1].endswith(("\n", "\r")):
                lines[-1] += newline
            if line_content(lines[-1]).strip():
                skeleton_block.append(newline)
        skeleton_block.extend(skeleton_lines)
        skeleton_block.append(newline)
        insertion_index = len(lines)

    output = []
    for index, line in enumerate(lines):
        if index == insertion_index:
            output.extend(skeleton_block)
        output.append(line)
        if index in phase_insertions:
            output.append(phase_insertions[index])

    if insertion_index == len(lines):
        output.extend(skeleton_block)

    return "".join(output), len(phases), not section_positions


def display_diff(name, old, new):
    for line in difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{name}",
        tofile=f"b/{name}",
        lineterm="",
    ):
        print(line)


def main():
    errors = 0
    needing_migration = 0

    try:
        candidates = sorted(root.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        print(f"ERROR: cannot list directory {root}: {exc}", file=sys.stderr)
        return 1

    for path in candidates:
        if path.suffix != ".md" or not path.is_file():
            continue
        if path.name in SKIP_NAMES or path.name.endswith(SKIP_SUFFIXES):
            continue

        try:
            if not inside_root(path):
                raise ValueError(f"path escape refused: {path}")

            raw = safe_read(path)
            try:
                original = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                print(f"ERROR: {path.name}: not valid UTF-8: {exc}", file=sys.stderr)
                errors += 1
                continue

            status = classify(original.splitlines(keepends=True))

            if status == "NEW":
                print(f"SKIP {path.name} (already new-style)")
                continue
            if status == "BROKEN":
                print(
                    f"SKIP {path.name} "
                    "(new-style but broken — fix its missing Phase blocks manually)"
                )
                continue

            converted, phase_count, no_sections = convert(original)
            if converted == original:
                continue

            needing_migration += 1
            print(f"=== {path.name}: LEGACY -> migrating ===")

            if not write:
                display_diff(path.name, original, converted)
            else:
                destination = path.with_name(path.stem + ".migrated.md")
                if not inside_root(destination):
                    raise ValueError(f"path escape refused: {destination}")
                try:
                    with destination.open("xb") as handle:
                        handle.write(converted.encode("utf-8"))
                except FileExistsError:
                    print(
                        f"ERROR: {path.name}: output already exists: {destination}",
                        file=sys.stderr,
                    )
                    errors += 1
                    continue
                print(f"  Written: {destination}")

            print(WARN_EMPTY)
            print(
                f"  [WARN] {phase_count} phase(s) derived from existing section headings; "
                "review names and order before relying on them."
            )
            if no_sections:
                print(
                    '  [WARN] no numbered "## N. <section>" headings found — '
                    "phases were not derived; add them manually"
                )

        except Exception as exc:
            print(f"ERROR: {path.name}: {exc}", file=sys.stderr)
            errors += 1
            continue

    print(f"files needing migration: {needing_migration}")
    return 1 if errors else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
PYTHON
