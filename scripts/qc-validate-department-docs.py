#!/usr/bin/env python3
"""qc-validate-department-docs.py -- Cross-reference DEPARTMENTS.md against department-naming-map.json"""
import json, os, re, sys
def rp(p):
    if os.path.isabs(p): return p
    d = os.path.dirname(os.path.abspath(__file__))
    while d != "/":
        if os.path.isfile(os.path.join(d,".git","HEAD")) or os.path.isfile(os.path.join(d,"version")): break
        d = os.path.dirname(d)
    return os.path.join(d,p)
def ei(mp):
    with open(mp) as f: c=f.read()
    m=re.search(r"\*\*Canonical department IDs\s*\(\d+\s*mandatory\):\*\*.*?\n```\n(.*?)```",c,re.DOTALL)
    if not m: print("ERROR: IDs block not found",file=sys.stderr); sys.exit(2)
    return [x.strip() for x in re.split(r"[,\n]+",m.group(1).strip()) if x.strip()]
def gi(mp):
    with open(mp) as f: d=json.load(f)
    return list(d.get("mandatory",{}).keys())
def main():
    dm,nm,q="23-ai-workforce-blueprint/DEPARTMENTS.md","23-ai-workforce-blueprint/department-naming-map.json",False
    a=sys.argv[1:]; i=0
    while i<len(a):
        if a[i]=="--departments-md" and i+1<len(a): dm=a[i+1]; i+=2
        elif a[i]=="--naming-map" and i+1<len(a): nm=a[i+1]; i+=2
        elif a[i]=="--quiet": q=True; i+=1
        else: print(f"Usage: {sys.argv[0]} [--departments-md PATH] [--naming-map PATH] [--quiet]",file=sys.stderr); sys.exit(2)
    dm,nm=rp(dm),rp(nm)
    di=ei(dm); mi=gi(nm)
    ds,ms=set(di),set(mi)
    idnm=ds-ms; imnd=ms-ds; err=False
    if not q: print(f"Validating DEPARTMENTS.md canonical IDs against department-naming-map.json\n  Doc IDs found:     {len(di)}\n  Map mandatory IDs: {len(mi)}")
    if idnm:
        err=True; print("\nFABRICATED IDs (in DEPARTMENTS.md but NOT in naming map):",file=sys.stderr)
        for x in sorted(idnm): print(f"  - {x}",file=sys.stderr)
    if imnd:
        err=True; print("\nMISSING IDs (in naming map but NOT in DEPARTMENTS.md):",file=sys.stderr)
        for x in sorted(imnd): print(f"  - {x}",file=sys.stderr)
    if len(di)!=len(mi):
        err=True; print(f"\nCOUNT MISMATCH: DEPARTMENTS.md lists {len(di)} IDs, naming map has {len(mi)}",file=sys.stderr)
    if err:
        print("\nVALIDATION FAILED: DEPARTMENTS.md does not match department-naming-map.json",file=sys.stderr); sys.exit(1)
    if not q: print(f"\nVALIDATION PASSED: All {len(di)} canonical IDs match the naming map.")
if __name__=="__main__": main()
