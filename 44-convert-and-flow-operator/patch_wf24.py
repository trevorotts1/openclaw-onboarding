import os
import sys

TARGET = "/Users/blackceomacmini/openclaw-onboarding/44-convert-and-flow-operator/qc-built-workflow.sh"

PATCHES = [
    (
        '''if [ "$TRIGGER_STATE" = "LINKED" ] && [ "$TRIGGER_TARGET" = "$TRIGGER_ROOT" ]; then''',
        '''if [ "$TRIGGER_STATE" = "LINKED" ] && [ "$TRIGGER_ROOT" != "none" ] && [ "$TRIGGER_TARGET" = "$TRIGGER_ROOT" ]; then''',
    ),
    (
        '''elif [ "$TRIGGER_STATE" = "ABSENT" ]; then''',
        '''elif [ "$TRIGGER_STATE" = "ABSENT" ] || [ "$TRIGGER_ROOT" = "none" ]; then''',
    ),
]


def main():
    if not os.path.isfile(TARGET):
        print("ERROR: target file not found: " + TARGET, file=sys.stderr)
        return 1

    with open(TARGET, "r", encoding="utf-8") as f:
        content = f.read()

    failures = []
    applied = 0

    for index, (old, new) in enumerate(PATCHES, 1):
        if new in content:
            continue
        if content.count(old) != 1:
            failures.append("PAIR %d: expected exactly one old match" % index)
            continue
        content = content.replace(old, new, 1)
        applied += 1

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        print("ERROR: no changes written", file=sys.stderr)
        return 1

    if applied:
        with open(TARGET, "w", encoding="utf-8", newline="") as f:
            f.write(content)

    print("APPLIED %d" % applied)
    return 0


if __name__ == "__main__":
    sys.exit(main())
