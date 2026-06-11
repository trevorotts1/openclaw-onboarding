#!/usr/bin/env python3
# _wire_agents_ghl_note.py — extracted from wire.sh AGENTS.md GHL-note rewrite.
#
# Externalized for stock-macOS bash 3.2.57 compatibility (python-in-$() heredoc
# parse hazard). Logic byte-equivalent to the former inline heredoc. Target
# AGENTS.md path = argv[1]; prints machine-readable "n=.." for the shell to parse.
import sys, pathlib, re

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding='utf-8')

# Match the old GHL note (any variant) including multi-line quoted paste instruction
old_note = re.compile(
    r'GHL (?:note|build-path note): [^\n]*\n'
    r'(?:[ \t]*"?[^\n]*\n)*?'          # quoted body lines
    r'(?:[ \t]*[^\n]*paste[^\n]*\n)*',  # paste-instruction lines
    re.MULTILINE
)
new_note = (
    'GHL build-path note: GHL Automations have no PUBLIC API or MCP. The Build with AI\n'
    'button is the public path. Skill 44 (convert-and-flow-operator) provides an\n'
    'internal-API build path when the client\'s Firebase token is present; when absent,\n'
    'Build with AI remains the only path (the agent generates the prompt, the operator\n'
    'clicks + pastes; the prompt nails the SHAPE, the operator pastes tokens after —\n'
    'always ship the verification checklist).\n'
)
text, n = re.subn(old_note, new_note, text, count=1)
path.write_text(text, encoding='utf-8')
print(f"n={n}")
