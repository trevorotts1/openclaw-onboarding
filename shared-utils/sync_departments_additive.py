#!/usr/bin/env python3
"""U133: Merge-additive departments sync for Command Center update flow."""
from __future__ import annotations
import json, os, sys, tempfile
from pathlib import Path
def _load(path, d=None):
 try: raw = path.read_text(encoding="utf-8")
 except OSError: return d
 if not raw.strip(): return d
 return json.loads(raw)
def _ns(raw):
 s = str(raw or "").strip().lower()
 if s.startswith("dept-"): s = s[5:]
 return s
def merge_additive(cc_depts, canon_depts):
 by_slug = {}
 for i, d in enumerate(cc_depts):
  s = _ns(d.get("slug") or d.get("id"))
  if s: by_slug[s] = i
 merged = list(cc_depts); added = updated = 0
 for entry in canon_depts:
  s = _ns(entry.get("slug") or entry.get("id"))
  if not s: continue
  if s in by_slug:
   idx = by_slug[s]
   for k, v in entry.items():
    if k not in ("slug", "id"): merged[idx][k] = v
   updated += 1
  else:
   merged.append(dict(entry)); added += 1
 return merged, added, updated
def _awrite(path, payload):
 path.parent.mkdir(parents=True, exist_ok=True)
 mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
 fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
 tmpp = Path(tmp)
 try:
  with os.fdopen(fd, "w", encoding="utf-8") as fh:
   json.dump(payload, fh, indent=2, ensure_ascii=False)
   fh.write("\n"); fh.flush(); os.fsync(fh.fileno())
  os.chmod(tmpp, mode); os.replace(tmpp, path)
 finally:
  if tmpp.exists(): tmpp.unlink()
def main():
 if len(sys.argv) < 3:
  print("Usage: sync_departments_additive.py <canon.json> <cc_depts.json>", file=sys.stderr)
  return 1
 can = _load(Path(sys.argv[1]), d=[])
 cc = _load(Path(sys.argv[2]), d=[])
 if not isinstance(can, list) or not isinstance(cc, list):
  print("[dept-sync] ERROR: inputs not JSON arrays", file=sys.stderr)
  return 1
 if not can:
  print("[dept-sync] canonical empty, nothing to sync", file=sys.stderr)
  return 0
 if not cc:
  _awrite(Path(sys.argv[2]), can)
  print(f"[dept-sync] {len(can)} added (populated from empty)", file=sys.stderr)
  return 0
 merged, added, updated = merge_additive(cc, can)
 if added or updated: _awrite(Path(sys.argv[2]), merged)
 preexisting = len(cc) - updated
 print(f"[dept-sync] {added} added, {updated} updated, custom depts preserved (total={len(merged)})", file=sys.stderr)
 return 0
if __name__ == "__main__": raise SystemExit(main())
