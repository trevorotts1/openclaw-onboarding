#!/usr/bin/env python3
"""aa_handoff_adapter.py - Skill 38 import adapter for Skill 52 handoff."""
import argparse, hashlib, json, sys
from pathlib import Path
REQUIRED = ["AI_Booking_Bot_Intelligence", "AI_Post_Booking_Bot_Intelligence", "Rescheduling_Booking_Bot_Intelligence"]
SUPPORTING = ["AI_Bot_Prep_Doc_Intelligence"]
VERSION = "1.0.0"
def _sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def _load_handoff(hd):
    p = hd / "HANDOFF.json"
    if not p.is_file(): return None, [("AF-CONV-ADAPTER-NO-HANDOFF", f"no handoff in {hd}")]
    try: ho = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e: return None, [("AF-CONV-ADAPTER-PARSE", f"parse error: {e}")]
    if ho.get("handoff") != "avatar-alchemist-downstream": return None, [("AF-CONV-ADAPTER-NOT-HANDOFF", "not a handoff")]
    if ho.get("skill") != "52-avatar-alchemist": return None, [("AF-CONV-ADAPTER-WRONG-SKILL", "wrong source")]
    return ho, []
def _find_target(ho):
    for t in (ho.get("targets", []) or []):
        if isinstance(t, dict) and t.get("skill_number") == 38: return t, []
    return None, [("AF-CONV-ADAPTER-NO-TARGET", "no target for skill 38")]
def _verify_checksums(hd, tgt):
    vs = []
    for inp in (tgt.get("inputs", []) or []) + (tgt.get("supporting", []) or []):
        if not isinstance(inp, dict): continue
        fn, es = inp.get("file", ""), inp.get("sha256", "")
        fp = hd / fn
        if not fp.is_file(): vs.append(("AF-CONV-ADAPTER-MISSING", f"file {fn!r} missing"))
        elif _sha(fp) != es: vs.append(("AF-CONV-ADAPTER-CHECKSUM", f"checksum mismatch {fn!r}"))
    return vs
def _parse_doc(fp, name):
    raw = fp.read_text(encoding="utf-8")
    lines = raw.splitlines()
    title = name.replace("_", " ")
    sections, cur = {}, "preamble"
    for ln in lines:
        s = ln.strip()
        if not s:
            if cur in sections: sections[cur].append("")
            continue
        if s.startswith("## "): cur = s[3:].strip().lower().replace(" ", "_"); sections.setdefault(cur, [])
        elif s.startswith("# "): title = s[2:].strip(); cur = "preamble"
        else: sections.setdefault(cur, []); sections[cur].append(s)
    def _st(key): return "\n".join(sections.get(key, [])).strip()
    return {"source": "aa-handoff", "version": VERSION, "deliverable": name, "title": title,
        "persona": _st("persona") or "AI booking assistant",
        "goal": _st("goal") or _st("objective") or "Handle booking conversation",
        "channel": _st("channel") or "SMS",
        "phases": [
            {"name": "greeting", "prompt": _st("greeting") or _st("opening") or _st("introduction") or "Greet and qualify"},
            {"name": "qualification", "prompt": _st("qualification") or _st("discovery") or "Understand the customer's needs"},
            {"name": "booking", "prompt": _st("booking") or _st("scheduling") or "Book the appointment"},
            {"name": "confirmation", "prompt": _st("confirmation") or _st("close") or "Confirm and close"}],
        "exit_rules": [{"condition": "booked", "action": "mark_converted"},
                       {"condition": "escalation_needed", "action": "escalate_to_human"},
                       {"condition": "opt_out", "action": "stop"}],
        "win_action": _st("win_action") or _st("success") or "appointment_booked",
        "raw_content": raw[:2000]}
def import_handoff(hd, out):
    ho, hv = _load_handoff(hd)
    if ho is None: return hv, None
    tgt, tv = _find_target(ho)
    if tgt is None: return tv, None
    cv = _verify_checksums(hd, tgt)
    if cv: return cv, None
    imap, smap = {}, {}
    for inp in (tgt.get("inputs", []) or []):
        if isinstance(inp, dict): imap[inp.get("deliverable", "")] = inp.get("file", "")
    for sup in (tgt.get("supporting", []) or []):
        if isinstance(sup, dict): smap[sup.get("deliverable", "")] = sup.get("file", "")
    errors, pbs = [], []
    for b in REQUIRED:
        fn = imap.get(b, "")
        if not fn: errors.append(("AF-CONV-ADAPTER-MISSING", f"Required {b!r} missing"))
        else:
            try: pbs.append(_parse_doc(hd / fn, b))
            except Exception as e: errors.append(("AF-CONV-ADAPTER-PARSE", f"{b}: {e}"))
    spbs = []
    for b in SUPPORTING:
        fn = smap.get(b, "")
        if fn:
            try: spbs.append(_parse_doc(hd / fn, b))
            except Exception as e: print(f"WARN: supporting {b} parse fail (non-blocking): {e}", file=sys.stderr)
    if errors: return errors, None
    cl = ho.get("client_label", "unknown")
    cp = {"source": "aa-handoff", "adapter_version": VERSION, "skill": "38-conversational-ai-system",
          "client_label": cl, "playbook_count": len(pbs), "playbooks": pbs,
          "supporting": spbs if spbs else None, "workflow_type": "appointment-booking",
          "trinity": {"automation_type": "Customer Replied", "channel": "SMS",
                       "implements": "appointment-booking initial playbook per Skill 23 handoff"}}
    bi = {"source": "aa-handoff", "adapter_version": VERSION, "client_label": cl,
          "intake_type": "conversation-workflow-input",
          "required_docs": {b: {"deliverable": b, "file": imap.get(b, ""), "parsed_as_playbook": True} for b in REQUIRED},
          "supporting_docs": {b: {"deliverable": b, "file": smap.get(b, ""), "parsed_as_playbook": len(spbs) > 0}
                              for b in SUPPORTING if b in smap}}
    out.mkdir(parents=True, exist_ok=True)
    (out / "conversation-playbooks.json").write_text(json.dumps(cp, indent=2) + "\n", encoding="utf-8")
    (out / "booking-bot-intake.json").write_text(json.dumps(bi, indent=2) + "\n", encoding="utf-8")
    return [], {"conversation-playbooks": cp, "booking-bot-intake": bi}
def _report(vs, mapped, out):
    if not vs and mapped is not None: print(f"PASS: 2 files -> {out}")
    else:
        print(f"FAIL: {len(vs)} violations")
        for c, m in vs: print(f"  [{c}] {m}")
def main(argv):
    ap = argparse.ArgumentParser(description="Import AA handoff into Skill 38")
    ap.add_argument("--handoff-dir", required=True); ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    hd, od = Path(args.handoff_dir), Path(args.out_dir)
    if not hd.is_dir(): print(f"ERROR: not dir {hd}"); return 3
    try: vs, mapped = import_handoff(hd, od)
    except Exception as e: print(f"ERROR: {e}"); return 3
    _report(vs, mapped, od)
    return 0 if not vs else 2
if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
