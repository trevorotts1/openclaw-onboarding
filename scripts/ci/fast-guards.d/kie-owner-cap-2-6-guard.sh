#!/usr/bin/env bash
# G-7 (fix plan A2): the owner prompt cap must be present for every GPT Image 2.6 route.
# The 20,000 ruling lived only as prose while owner_prompt_cap_chars was absent from the
# data, so Skill 74 fell through to the vendor schema and resolved 32,000. This guard
# fails the build when the cap is missing, disagreeing, or duplicated as a literal.
set -e
cd "${GITHUB_WORKSPACE:-.}"
python3 tests/unit/kie-owner-cap-2-6.test.py
# The guard must be ABLE to fail: a negative fixture with the cap removed must be caught.
python3 tests/unit/kie-owner-cap-2-6.test.py --self-test
