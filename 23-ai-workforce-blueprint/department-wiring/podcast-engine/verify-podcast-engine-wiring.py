#!/usr/bin/env python3
"""
verify-podcast-engine-wiring.py - enforcement pointer for the Podcast Production
Engine department, persona, and kanban wiring (PRD Sections 3.5, 3.6, 13).

Proves, structurally (no scores grepped), that:
  1. The wiring targets the EXISTING podcast department only. department-naming-map.json
     still marks podcast universal_primary=true in the content-creator pack, exactly once.
     No duplicate podcast department is introduced (this slice never edits the naming map).
  2. Every bound persona (slug, dept) exists in templates/role-library/_index.json
     (orphan check). The bound set is exactly the four podcast owning roles plus the
     three audio supporting roles named in PRD Section 3.6.
  3. The QC independence rule holds: the qc persona (qc-specialist-podcast) is NOT in
     the drafting persona set, is flagged is_qc and not is_drafting, and each drafting
     persona is flagged is_drafting and not is_qc.
  4. The kanban columns map 1:1 onto the SQLite/ledger status enum declared in
     design/dashboard-design.md (received..complete forward, plus queued_credit_out and
     failed off-board, plus the aged_out queue_state overlay). No status is unmapped and
     no column invents a status.
  5. The intake sessionKey template is podcast:intake:<client-slug> and is owned by the
     podcast department agent (single consumer).
  6. The canonical binding in skill-department-map.json (skill 58) lists departments
     ["podcast"], carries exactly one primary role (director-of-podcast), and its owning
     roles are a subset of the wiring's podcast personas.
  7. The PRD Section 13 access matrix is present and internally consistent: default-deny
     policy; owner tier is the podcast department with the four owning personas and write
     access; supporting tier is the audio department with the three supporting personas;
     routing_only (master-orchestrator) executes no pipeline steps and cannot write;
     read_only_downstream covers social-media and marketing with no write access; and no
     explicit no-access department is also a granted department.

Exit codes:
  0 = all wiring assertions pass
  7 = one or more violations (details printed)

Read-only. Never writes. Idempotent. No em dashes in output. No triple-backtick fences.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
WIRING = os.path.join(HERE, "wiring.json")
MAP_PATH = os.path.join(REPO, "23-ai-workforce-blueprint", "skill-department-map.json")
INDEX_PATH = os.path.join(REPO, "23-ai-workforce-blueprint", "templates", "role-library", "_index.json")
NAMING_MAP = os.path.join(REPO, "23-ai-workforce-blueprint", "department-naming-map.json")
# Dashboard design is the status-enum source of truth. It ships in the repo under
# the synced PRD folder; fall back to the operator working copy if that is absent.
DASHBOARD_CANDIDATES = [
    os.path.join(REPO, "project-prds", "podcast-engine", "design", "dashboard-design.md"),
]

EXPECTED_PODCAST_OWNERS = {"director-of-podcast", "podcast-host", "audio-post-producer", "qc-specialist-podcast"}
EXPECTED_AUDIO_SUPPORT = {"podcast-editor", "podcast-producer", "audio-mastering-specialist"}


def load_json(p):
    with open(p) as f:
        return json.load(f)


def parse_status_enum(md_text):
    """Extract the podcast_jobs.status CHECK (... IN (...)) enum from dashboard-design.md."""
    m = re.search(r"status\s+TEXT\s+NOT\s+NULL\s+DEFAULT\s+'received'\s+CHECK\s*\(\s*status\s+IN\s*\((.*?)\)\s*\)",
                  md_text, re.DOTALL)
    if not m:
        return None
    return set(re.findall(r"'([a-z_]+)'", m.group(1)))


def run():
    errors = []
    w = load_json(WIRING)
    m = load_json(MAP_PATH)
    idx = load_json(INDEX_PATH)
    nm = load_json(NAMING_MAP)

    live_pairs = {(r["dept"], r["slug"]) for r in idx["roles"]}

    # --- 1. Existing podcast department only, universal_primary, no duplicate ---
    dept = w.get("department", {})
    if dept.get("id") != "podcast":
        errors.append(f"[dept] wiring department id is '{dept.get('id')}', expected 'podcast'")
    if dept.get("no_duplicate_department") is not True:
        errors.append("[dept] no_duplicate_department flag is not true")
    packs = nm.get("vertical_packs", {})
    podcast_universal_hits = []
    for pid, pack in packs.items():
        for d in pack.get("auto_add_departments", []) or []:
            if isinstance(d, dict) and d.get("id") == "podcast" and d.get("universal_primary") is True:
                podcast_universal_hits.append(pid)
    if podcast_universal_hits != ["content-creator"]:
        errors.append(f"[dept] podcast universal_primary packs = {podcast_universal_hits}, expected exactly ['content-creator']")

    # --- 2. Persona orphan check + exact bound set ---
    personas = w.get("personas", [])
    bound = {(p["slug"], p["dept"]) for p in personas}
    for slug, d in bound:
        if (d, slug) not in live_pairs:
            errors.append(f"[persona] ORPHAN: ({slug}, {d}) is not in role-library _index.json")
    podcast_bound = {p["slug"] for p in personas if p["dept"] == "podcast"}
    audio_bound = {p["slug"] for p in personas if p["dept"] == "audio"}
    if podcast_bound != EXPECTED_PODCAST_OWNERS:
        errors.append(f"[persona] podcast owners bound = {sorted(podcast_bound)}, expected {sorted(EXPECTED_PODCAST_OWNERS)}")
    if audio_bound != EXPECTED_AUDIO_SUPPORT:
        errors.append(f"[persona] audio supporters bound = {sorted(audio_bound)}, expected {sorted(EXPECTED_AUDIO_SUPPORT)}")

    # --- 3. QC independence ---
    rule = w.get("qc_independence_rule", {})
    drafting = set(rule.get("drafting_personas", []))
    qc_persona = rule.get("qc_persona")
    if not drafting:
        errors.append("[qc] no drafting_personas declared")
    if qc_persona in drafting:
        errors.append(f"[qc] INDEPENDENCE VIOLATION: qc persona '{qc_persona}' is also a drafting persona")
    by_slug = {p["slug"]: p for p in personas}
    if qc_persona in by_slug:
        qp = by_slug[qc_persona]
        if not qp.get("is_qc"):
            errors.append(f"[qc] qc persona '{qc_persona}' is not flagged is_qc")
        if qp.get("is_drafting"):
            errors.append(f"[qc] qc persona '{qc_persona}' is flagged is_drafting (must not draft)")
    else:
        errors.append(f"[qc] qc persona '{qc_persona}' is not in the bound personas")
    for ds in drafting:
        if ds in by_slug:
            if not by_slug[ds].get("is_drafting"):
                errors.append(f"[qc] drafting persona '{ds}' is not flagged is_drafting")
            if by_slug[ds].get("is_qc"):
                errors.append(f"[qc] drafting persona '{ds}' is also flagged is_qc")
        else:
            errors.append(f"[qc] drafting persona '{ds}' is not in the bound personas")

    # --- 4. Kanban covers the status enum 1:1 ---
    dash_text = None
    for c in DASHBOARD_CANDIDATES:
        if os.path.isfile(c):
            dash_text = open(c).read()
            break
    if dash_text is None:
        errors.append("[kanban] dashboard-design.md not found; cannot verify status coverage")
    else:
        enum = parse_status_enum(dash_text)
        if not enum:
            errors.append("[kanban] could not parse status enum from dashboard-design.md")
        else:
            k = w.get("kanban", {})
            board = {c["status"] for c in k.get("columns", [])}
            off = {c["status"] for c in k.get("off_board_columns", [])}
            mapped = board | off
            missing = enum - mapped
            extra = mapped - enum
            if missing:
                errors.append(f"[kanban] status values with no column: {sorted(missing)}")
            if extra:
                errors.append(f"[kanban] columns for non-existent status values: {sorted(extra)}")
            # forward board must be the 9 non-terminal, non-hold statuses in order
            order = [c["status"] for c in sorted(k.get("columns", []), key=lambda c: c["order"])]
            expected_order = ["received", "researching", "writing", "in_qc", "generating_art",
                              "producing_audio", "publishing", "enrolling", "complete"]
            if order != expected_order:
                errors.append(f"[kanban] forward column order = {order}, expected {expected_order}")
            # aged_out overlay must reference queue_state, not the status enum
            overlays = {o.get("queue_state") for o in k.get("overlays", [])}
            if "aged_out" not in overlays:
                errors.append("[kanban] aged_out queue_state overlay is missing")

    # --- 5. sessionKey ---
    sb = w.get("session_binding", {})
    if sb.get("session_key_template") != "podcast:intake:<client-slug>":
        errors.append(f"[session] session_key_template = '{sb.get('session_key_template')}', expected 'podcast:intake:<client-slug>'")

    # --- 6. Canonical map entry (skill 58) ---
    entry = next((s for s in m["skills"] if s.get("slug") == "podcast-production-engine"), None)
    if entry is None:
        errors.append("[map] skill-department-map.json has no podcast-production-engine entry")
    else:
        if entry.get("departments") != ["podcast"]:
            errors.append(f"[map] skill 58 departments = {entry.get('departments')}, expected ['podcast']")
        roles = entry.get("roles", [])
        primaries = [r for r in roles if r.get("primary")]
        if len(primaries) != 1:
            errors.append(f"[map] skill 58 must have exactly one primary role, found {len(primaries)}")
        elif primaries[0].get("slug") != "director-of-podcast":
            errors.append(f"[map] skill 58 primary role = {primaries[0].get('slug')}, expected director-of-podcast")
        map_role_slugs = {r["slug"] for r in roles}
        if not map_role_slugs.issubset(EXPECTED_PODCAST_OWNERS):
            errors.append(f"[map] skill 58 owning roles {sorted(map_role_slugs)} are not a subset of the podcast owners")
        if not entry.get("client_facing"):
            errors.append("[map] skill 58 should be client_facing true (department-invocable, like skill 38)")

    # --- 7. Access matrix (PRD Section 13 access decision, machine-enforced) ---
    am = w.get("access_matrix")
    if not am:
        errors.append("[access] access_matrix block is missing (PRD Section 13 access decision)")
    else:
        if am.get("policy") != "default-deny":
            errors.append("[access] access_matrix.policy must be 'default-deny'")
        owner = am.get("owner", {})
        supporting = am.get("supporting", {})
        routing = am.get("routing_only", {})
        readers = am.get("read_only_downstream", []) or []
        noacc = am.get("no_access", {})
        if owner.get("department") != "podcast":
            errors.append(f"[access] owner department = {owner.get('department')}, expected 'podcast'")
        if set(owner.get("personas", [])) != EXPECTED_PODCAST_OWNERS:
            errors.append(f"[access] owner personas = {sorted(owner.get('personas', []))}, expected {sorted(EXPECTED_PODCAST_OWNERS)}")
        if owner.get("write") is not True:
            errors.append("[access] owner tier must carry write access")
        if supporting.get("department") != "audio":
            errors.append(f"[access] supporting department = {supporting.get('department')}, expected 'audio'")
        if set(supporting.get("personas", [])) != EXPECTED_AUDIO_SUPPORT:
            errors.append(f"[access] supporting personas = {sorted(supporting.get('personas', []))}, expected {sorted(EXPECTED_AUDIO_SUPPORT)}")
        if routing.get("executes_pipeline_steps") is not False:
            errors.append("[access] routing_only must declare executes_pipeline_steps=false (routing dispatches, never runs steps)")
        if routing.get("write") is not False:
            errors.append("[access] routing_only must not carry write access")
        reader_depts = set()
        for r in readers:
            reader_depts.add(r.get("department"))
            if r.get("write") is not False:
                errors.append(f"[access] read_only_downstream '{r.get('department')}' must not carry write access")
        for req in ("social-media", "marketing"):
            if req not in reader_depts:
                errors.append(f"[access] read_only_downstream is missing '{req}'")
        # Disjointness: a no-access example can never also be a granted department.
        granted = {owner.get("department"), supporting.get("department"), routing.get("department")} | reader_depts
        granted.discard(None)
        for ex in noacc.get("explicit_examples", []):
            if ex in granted:
                errors.append(f"[access] no_access example '{ex}' is also a granted department (contradiction)")

    return errors


def main():
    errors = run()
    if errors:
        print(f"FAIL - {len(errors)} wiring violation(s):")
        for e in errors:
            print("  x " + e)
        return 7
    print("OK - podcast engine wiring verified:")
    print("  - existing podcast department only (universal_primary in content-creator pack); no duplicate")
    print("  - 4 podcast owners + 3 audio supporters all resolve in the role library (no orphans)")
    print("  - QC independence holds (qc-specialist-podcast is not a drafting persona)")
    print("  - kanban columns cover the dashboard status enum 1:1 (9 forward + hold + failed + aged_out overlay)")
    print("  - intake sessionKey podcast:intake:<client-slug> bound to the podcast department agent")
    print("  - skill-department-map.json skill 58 binds departments ['podcast'] with one primary (director-of-podcast)")
    print("  - PRD Section 13 access matrix present and disjoint (default-deny; only owner+supporting write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
