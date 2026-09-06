#!/usr/bin/env bash
# Legacy test entry point, retained by CI/install checks. The old expected
# successful agency Tier2 fallback contradicted client-only ownership. The
# strict full-caller suite now asserts agency denial plus local staging, exact
# parent verification, scoped resume/refresh, and publication failure recovery.
set -euo pipefail
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test-notion-client-ownership.py"
