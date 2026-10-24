#!/usr/bin/env bash
# lib-hook-mapping-contract.sh — THE single authoritative contract for a valid
# inbound GHL `hooks.mappings` entry.
#
# WHY THIS FILE EXISTS (G-03 / G-04 / G-05, all demonstrated at HEAD):
#   24-self-test-hook.sh evaluated ONE parsed mapping and demanded `model`.
#   qc-backend-ready.sh grepped the WHOLE openclaw.json for `"model": "..."`,
#   so a model anywhere in the file made it PASS the exact mapping the self-test
#   refused. Two scripts, two definitions of "valid", one install that could
#   never pass its own gate. Both now source THIS file and cannot drift.
#
# PBB-017 GROUND TRUTH — `model` is NOT required (evidence, not preference):
#   * installed OpenClaw 2026.10.5, dist/zod-schema-BVpLKnmq.mjs:
#     `HookMappingSchema = strictObject({ ... model: string().optional() ... })`
#     — every mapping field is `.optional()`. `.strict()` only rejects unknown keys.
#   * `openclaw config validate` (this box's own build): a mapping WITHOUT `model`
#     reports "Config valid"; the same mapping with `fallbacks` reports
#     "Unrecognized key: fallbacks".
#   * docs/gateway/config-hooks.md "Mapping details": `model` | default
#     "agent/model defaults" | contract "Templated model override."
#   * dist/hooks-STZ6dZJ5.mjs `buildActionFromMapping` -> `renderOptional(...)`
#     -> undefined when absent, and `mergeAction` -> `override.model ?? baseAgent?.model`,
#     i.e. the run falls back to the AGENT's configured model.
#   * live ~/.openclaw/openclaw.json on this host: 5 of 7 mappings carry no `model`.
#   `agentId` is sufficient to route. The old `missing-key:model` rule was invented
#   by this skill, not derived from OpenClaw, and it is what made a fresh install
#   fail its own readiness gate.
#
# CONTRACT (evaluated per mapping id — never a whole-file grep):
#   required keys  : id, match, action, agentId, deliver, messageTemplate
#   optional keys  : model, wakeMode, name, sessionKey, timeoutSeconds
#                    (`model` is an OPTIONAL override — see PBB-017 above)
#   exact key set  : any other key fails, reported by name. The OpenClaw schema
#                    is .strict() and rejects `fallbacks` outright.
#   action         : exactly "agent"
#   agentId        : non-empty AND listed in hooks.allowedAgentIds (the binding)
#   messageTemplate: present AND non-empty. OpenClaw's own `validateAction`
#                    refuses an agent action with no message
#                    ("hook mapping requires message"), so this one IS load-bearing.
#   model          : OPTIONAL. If the key IS present it must be a non-empty string.
#                    A blank override is a wiring mistake and never meaningful:
#                    OpenClaw's `normalizeAgentPayload` rejects a present-but-blank
#                    model with "model required". This is a SKILL-level strictness,
#                    named as such — not an OpenClaw requirement.
#   deliver        : present and exactly false
#   match          : an object carrying a non-empty "path"
#   directives     : every HOOK_MAPPING_DIRECTIVE_NEEDLE present in
#                    messageTemplate (send-directive + conversation-memory)
#
# PURE BASH + POSIX awk. No jq, no python3 — jq can be absent on a fleet box, and
# this keeps qc-backend-ready.sh's "no python" claim true. bash -n clean.
#
# Public surface (read-only; nothing here writes):
#   hook_mapping_contract_eval <config-file>
#       one verdict line per hooks.mappings element:
#         MAPCONTRACT|<id>|OK|
#         MAPCONTRACT|<id>|ERR|<reason>[,<reason>...]
#       then the config-level fact both gates used to check separately:
#         MAPENABLED|<true|false|unset>
#       then the mapping the self-test should evaluate for a route:
#         MAPSELECT|<id>|<1-based index>
#       then the single verdict BOTH gates act on (all mappings + hooks.enabled):
#         GATEVERDICT|OK|
#         GATEVERDICT|ERR|<reason>[,<reason>...]
#       exit 0 always — the verdict lines are the result; callers set the exit code.
#   hook_mapping_contract_reasons
#       all possible failure reasons, one per line (documentation + fixture audit).
#   HOOK_MAPPING_SEND_DIRECTIVE_NEEDLES / HOOK_MAPPING_CONVERSATION_MEMORY_NEEDLES
#       THE single home of the directive needles. scripts/lib-docker-tenant.sh
#       sources this file and prints these; the writer's fail-closed guard and
#       the Layer-3 QC scripts read them from here. Nothing duplicates them.
#   HOOK_MAPPING_DIRECTIVE_NEEDLES
#       both lists concatenated (what the messageTemplate check below consumes).

# shellcheck shell=bash

# Mandatory send-directive elements. Matched case-insitively. Layer 1 of the
# 3-layer send enforcement (Layer 2 = AGENTS.md standing rule, Layer 3 =
# qc-send-directive.sh). The writer's guard refuses to write a template missing
# any of these — that is the hook that lets the agent draft-but-not-send.
HOOK_MAPPING_SEND_DIRECTIVE_NEEDLES='MANDATORY
SEND
GHL Conversations API
drafting
NOT sending
messageId
SAME channel
do NOT hardcode SMS
conversations/search'

# Mandatory conversation-memory elements (read-before / append-after). GHL inbound
# hook sessions are SINGLE-TURN / stateless, so the per-contact log is the agent's
# only memory. Missing these is the exact regression that left a live client
# mid-booking with "no memory".
HOOK_MAPPING_CONVERSATION_MEMORY_NEEDLES='conversational-logs
read
append'

# Every needle a valid messageTemplate must carry.
HOOK_MAPPING_DIRECTIVE_NEEDLES="$HOOK_MAPPING_SEND_DIRECTIVE_NEEDLES
$HOOK_MAPPING_CONVERSATION_MEMORY_NEEDLES"

# Every reason the predicate can emit. Keep in step with the awk below.
hook_mapping_contract_reasons() {
  printf '%s\n' \
    'missing-key:<key>' \
    'unexpected-key:<key>' \
    'action-not-agent' \
    'match-no-path' \
    'no-messageTemplate' \
    'no-agentId' \
    'allowedAgentIds-missing' \
    'agentId-not-allowed' \
    'blank-model-override' \
    'deliver-not-false' \
    'missing-directive:<needle>'
}
# hook_mapping_contract_eval <config-file>
hook_mapping_contract_eval() {
  _hmc_config="${1:-}"
  [ -n "$_hmc_config" ] && [ -f "$_hmc_config" ] || return 0

  HOOK_MAPPING_NEEDLES="$HOOK_MAPPING_DIRECTIVE_NEEDLES" HOOK_MAPPING_ID="${HOOK_MAPPING_ID:-}" \
    awk '
  # ---------- string-aware JSON reader (POSIX awk only) -------------------
  # T is the text being read, TN its length. Escapes are kept RAW so a
  # backslash-escaped quote can never terminate a string early.
  function skipws(i,   c) {
    while (i <= TN) {
      c = substr(T, i, 1)
      if (c == " " || c == "\t" || c == "\n" || c == "\r") i++; else break
    }
    return i
  }
  # JSON string whose opening quote is at i -> STR_VAL (raw, escapes intact), STR_END
  function readstr(i,   c, out) {
    out = ""; i++
    while (i <= TN) {
      c = substr(T, i, 1)
      if (c == "\\") { out = out substr(T, i, 2); i += 2; continue }
      if (c == "\"") { i++; break }
      out = out c; i++
    }
    STR_VAL = out; STR_END = i
  }
  # bare scalar (number / true / false / null) starting at i
  function readbare(i,   c, out) {
    out = ""
    while (i <= TN) {
      c = substr(T, i, 1)
      if (c == "," || c == "}" || c == "]" || c == " " || c == "\t" || c == "\n" || c == "\r") break
      out = out c; i++
    }
    STR_VAL = out; STR_END = i
  }

  # ---------- one mapping object -----------------------------------------
  # Fills KEY[1..NKEY] / VAL[1..NKEY] and MATCH_PATH.
  function parseobj(text,   i, c, key, v, d, start, savedT, savedTN, j) {
    for (j = 1; j <= NKEY; j++) { KEY[j] = ""; VAL[j] = "" }
    NKEY = 0; MATCH_PATH = ""
    savedT = T; savedTN = TN
    T = text; TN = length(text)
    i = skipws(1)
    if (substr(T, i, 1) != "{") { T = savedT; TN = savedTN; return }
    i = skipws(i + 1)
    if (substr(T, i, 1) == "}") { T = savedT; TN = savedTN; return }
    while (i <= TN) {
      i = skipws(i)
      if (substr(T, i, 1) != "\"") break
      readstr(i); key = STR_VAL; i = STR_END
      i = skipws(i)
      if (substr(T, i, 1) != ":") break
      i = skipws(i + 1)
      c = substr(T, i, 1)
      if (c == "\"") {
        readstr(i); v = STR_VAL; i = STR_END
      } else if (c == "{" || c == "[") {
        start = i; d = 0
        while (i <= TN) {
          c = substr(T, i, 1)
          if (c == "\"") { readstr(i); i = STR_END; continue }
          if (c == "{" || c == "[") d++
          else if (c == "}" || c == "]") { d--; if (d == 0) { i++; break } }
          i++
        }
        v = (substr(T, start, 1) == "{") ? "<object>" : "<array>"
        if (key == "match" && v == "<object>") matchpath(substr(T, start, i - start))
      } else {
        readbare(i); v = STR_VAL; i = STR_END
      }
      NKEY++; KEY[NKEY] = key; VAL[NKEY] = v
      i = skipws(i)
      if (substr(T, i, 1) == ",") { i++; continue }
      break
    }
    T = savedT; TN = savedTN
  }

  # pull "path" out of a match-object substring
  function matchpath(text,   i, c, key, savedT, savedTN) {
    savedT = T; savedTN = TN
    T = text; TN = length(text)
    i = skipws(1)
    if (substr(T, i, 1) == "{") i = skipws(i + 1)
    while (i <= TN) {
      if (substr(T, i, 1) != "\"") break
      readstr(i); key = STR_VAL; i = STR_END
      i = skipws(i)
      if (substr(T, i, 1) != ":") break
      i = skipws(i + 1)
      if (substr(T, i, 1) == "\"") { readstr(i); if (key == "path") MATCH_PATH = STR_VAL; i = STR_END }
      else { readbare(i); i = STR_END }
      i = skipws(i)
      if (substr(T, i, 1) == ",") i = skipws(i + 1); else break
    }
    T = savedT; TN = savedTN
  }

  function keyval(want,   j) {
    for (j = 1; j <= NKEY; j++) if (KEY[j] == want) return VAL[j]
    return ""
  }
  function haskey(want,   j) {
    for (j = 1; j <= NKEY; j++) if (KEY[j] == want) return 1
    return 0
  }

  BEGIN {
    T = ""
    want_id = ENVIRON["HOOK_MAPPING_ID"]
    n = split(ENVIRON["HOOK_MAPPING_NEEDLES"], NEEDLE, "\n")
    NNEEDLE = 0
    for (i = 1; i <= n; i++) if (length(NEEDLE[i]) > 0) { NNEEDLE++; NEEDLE[NNEEDLE] = NEEDLE[i] }
  }

  { T = T $0 "\n" }

  END {
    TN = length(T)

    # ---- locate hooks.enabled / hooks.allowedAgentIds / hooks.mappings ----
    # A real depth counter, so a "mappings" string inside a messageTemplate can
    # never be mistaken for the hooks.mappings key.
    depth = 0; i = 1; in_hooks = 0
    mapstart = 0; allowstart = 0; hooks_enabled = ""
    while (i <= TN) {
      c = substr(T, i, 1)
      if (c == "\"") {
        readstr(i); key = STR_VAL; j = STR_END
        k = skipws(j)
        if (substr(T, k, 1) == ":") {
          k = skipws(k + 1)
          nxt = substr(T, k, 1)
          if (depth == 1 && key == "hooks" && nxt == "{") in_hooks = 1
          else if (in_hooks && depth == 2) {
            if (key == "mappings" && nxt == "[") mapstart = k + 1
            else if (key == "allowedAgentIds" && nxt == "[") allowstart = k + 1
            else if (key == "enabled") { readbare(k); hooks_enabled = STR_VAL; i = STR_END }
          }
        }
        i = STR_END
        continue
      }
      if (c == "{" || c == "[") depth++
      else if (c == "}" || c == "]") { depth--; if (depth < 2) in_hooks = 0 }
      i++
    }

    # ---- allowedAgentIds values -------------------------------------------
    NALLOW = 0
    if (allowstart > 0) {
      i = allowstart
      while (i <= TN) {
        i = skipws(i)
        c = substr(T, i, 1)
        if (c == "]") break
        if (c == "\"") { readstr(i); NALLOW++; ALLOW[NALLOW] = STR_VAL; i = STR_END }
        else { readbare(i); i = STR_END }
        i = skipws(i)
        if (substr(T, i, 1) == ",") i = skipws(i + 1); else break
      }
    }

    # ---- mapping objects ---------------------------------------------------
    NMAP = 0
    if (mapstart > 0) {
      i = mapstart; d = 0; objstart = 0
      while (i <= TN) {
        c = substr(T, i, 1)
        if (c == "\"") { readstr(i); i = STR_END; continue }
        if (c == "{" || c == "[") {
          if (d == 0 && c == "{") objstart = i
          d++
        } else if (c == "}" || c == "]") {
          d--
          if (d <= 0) {
            if (c == "}" && objstart > 0) {
              NMAP++; MAPTEXT[NMAP] = substr(T, objstart, i - objstart + 1); objstart = 0
            }
            if (c == "]") break
          }
        }
        i++
      }
    }

    # ---- evaluate every mapping against THE contract -----------------------
    selidx = 0; fallback = 0
    for (m = 1; m <= NMAP; m++) {
      parseobj(MAPTEXT[m])
      id = keyval("id"); if (id == "") id = "<mapping #" m ">"
      aid = keyval("agentId"); act = keyval("action")
      r = ""

      # exact key set
      if (!haskey("id"))              r = r ",missing-key:id"
      if (!haskey("match"))           r = r ",missing-key:match"
      if (!haskey("action"))          r = r ",missing-key:action"
      if (!haskey("agentId"))         r = r ",missing-key:agentId"
      if (!haskey("deliver"))         r = r ",missing-key:deliver"
      if (!haskey("messageTemplate")) r = r ",missing-key:messageTemplate"
      for (q = 1; q <= NKEY; q++) {
        kk = KEY[q]
        if (kk == "id" || kk == "match" || kk == "action" || kk == "agentId" ||
            kk == "model" || kk == "deliver" || kk == "messageTemplate" ||
            kk == "wakeMode" || kk == "name" || kk == "sessionKey" || kk == "timeoutSeconds") continue
        r = r ",unexpected-key:" kk
      }

      if (act != "agent")        r = r ",action-not-agent"
      if (MATCH_PATH == "")      r = r ",match-no-path"

      if (aid == "") r = r ",no-agentId"
      if (NALLOW == 0) r = r ",allowedAgentIds-missing"
      else {
        bound = 0
        for (q = 1; q <= NALLOW; q++) if (ALLOW[q] == aid) bound = 1
        if (bound == 0) r = r ",agentId-not-allowed"
      }

      # `model` is OPTIONAL (PBB-017). Refuse only a present-but-BLANK override:
      # renderOptional() would silently drop it, and the OpenClaw
      # normalizeAgentPayload rejects a blank model with "model required".
      if (haskey("model") && keyval("model") == "") r = r ",blank-model-override"
      if (keyval("deliver") != "false") r = r ",deliver-not-false"

      # messageTemplate must render non-empty: the OpenClaw validateAction refuses
      # an agent action with no message ("hook mapping requires message").
      mt = keyval("messageTemplate")
      if (mt == "") r = r ",no-messageTemplate"
      mt = tolower(mt)
      for (q = 1; q <= NNEEDLE; q++)
        if (index(mt, tolower(NEEDLE[q])) == 0) r = r ",missing-directive:" NEEDLE[q]

      if (r == "") { print "MAPCONTRACT|" id "|OK|"; MAPVERDICT[m] = "OK" }
      else         { print "MAPCONTRACT|" id "|ERR|" substr(r, 2); MAPVERDICT[m] = substr(r, 2) }
      MAPID[m] = id

      # self-test selector: exact id match wins; otherwise the first mapping
      # bound to an agent (the pre-existing 24-self-test-hook.sh rule).
      if (want_id != "" && id == want_id && selidx == 0) selidx = m
      if (fallback == 0 && (act == "agent" || aid != "")) fallback = m
    }
    if (selidx == 0) selidx = fallback
    if (selidx == 0 && NMAP > 0) selidx = 1
    print "MAPENABLED|" (hooks_enabled == "" ? "unset" : hooks_enabled)
    if (selidx > 0) print "MAPSELECT|" MAPID[selidx] "|" selidx
    else print "MAPSELECT||0"

    # GATEVERDICT — the one verdict both gates act on. Deliberately computed over
    # EVERY mapping plus hooks.enabled, so the two scripts cannot reach different
    # verdicts on the same file (G-04/G-05). Per-mapping detail stays above.
    gr = ""
    if (hooks_enabled == "false") gr = gr ",hooks-disabled"
    if (NMAP == 0) gr = gr ",no-live-hooks-mapping"
    for (m = 1; m <= NMAP; m++) if (MAPVERDICT[m] != "OK") gr = gr ",mapping-not-ready:" MAPID[m]
    if (gr == "") print "GATEVERDICT|OK|"
    else print "GATEVERDICT|ERR|" substr(gr, 2)
  }
  ' "$_hmc_config"
  _hmc_rc=$?
  # Fail CLOSED, never silently. A predicate that errors to nothing would make
  # both gates report "nothing to check" and pass — the exact silent-success
  # class this repo has been burned by before.
  if [ "$_hmc_rc" -ne 0 ]; then
    printf 'GATEVERDICT|ERR|contract-eval-failed-rc%s\n' "$_hmc_rc"
    printf 'MAPENABLED|unset\n'
    printf 'MAPSELECT||0\n'
    return 0
  fi
  return 0
}
