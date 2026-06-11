#!/usr/bin/env python3
# _wire_rules_15_16.py — extracted from wire.sh MEMORY.md Rules 15/16 rewrite.
#
# Externalized for stock-macOS bash 3.2.57 compatibility: bash 3.2 mis-parses a
# `python3 - "$X" <<PYEOF ... PYEOF` heredoc nested inside a $() command
# substitution (counts the quotes in the Python and aborts the whole script with
# `unexpected EOF while looking for matching "` at PARSE time). Logic is
# byte-equivalent to the former inline heredoc. Target MEMORY.md path = argv[1];
# prints machine-readable "n15=.. n16=.. n_old_wiped=.." for the shell to parse.
import sys, pathlib, re

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding='utf-8')

# Rule 15: match on "15." + any header text ending the line, then the rule body
# which may be indented with any amount of whitespace (not just 4 spaces).
# Also matches the forbidding phrase to catch variant indent styles.
r15_old = re.compile(
    r'15\. (?:Terminology Rule|Build-Routing Rule)[^\n]*\n'
    r'(?:[ \t]+[^\n]*\n)*',
    re.MULTILINE
)
r15_new = (
    '15. Build-Routing Rule — when the operator says "build me a workflow / playbook /\n'
    '    funnel," route by node type. A workflow WITH a conversational node -> skill 44\n'
    '    builds the structure and AUTO-INVOKES skill 38 for the brain in the SAME run\n'
    '    (THE TRINITY: GHL automation + communications playbook + workflow-AI prompt\n'
    '    ship together or it is NOT registered). A PURELY MECHANICAL workflow (no\n'
    '    conversational node) builds standalone via skill 41\'s structure + 12-point\n'
    '    checklist. (Supersedes the legacy "always Step 9.20" routing.)\n'
)
text, n15 = re.subn(r15_old, r15_new, text, count=1)

# Rule 16: match on "16." + any header text ending the line, then body lines
r16_old = re.compile(
    r'16\. (?:No-GHL-API Rule|Convert-and-Flow Build-Path Rule)[^\n]*\n'
    r'(?:[ \t]+[^\n]*\n)*',
    re.MULTILINE
)
r16_new = (
    '16. Convert-and-Flow Build-Path Rule — GHL Automations have no PUBLIC API or MCP.\n'
    '    The Build with AI button is the public path. Skill 44 provides an internal-API\n'
    '    build path when the client\'s Firebase token is present; when absent, Build with\n'
    '    AI remains the only path. (Never claim a PUBLIC GHL Automations API exists.)\n'
)
text, n16 = re.subn(r16_old, r16_new, text, count=1)

# Also wipe any surviving old wording lines (belt + suspenders, within the
# builder-design-rules block only — avoid touching CHANGELOG).
old_wording_re = re.compile(
    r'^([ \t]*)(?:NO API and NO MCP|NEVER write or claim code that ["“]calls the GHL Automations API["”])[^\n]*\n',
    re.MULTILINE
)
text, n_old = re.subn(old_wording_re, '', text)

path.write_text(text, encoding='utf-8')
# Print machine-readable counts for the shell to parse
print(f"n15={n15} n16={n16} n_old_wiped={n_old}")
