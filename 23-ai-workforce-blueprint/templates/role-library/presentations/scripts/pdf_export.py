#!/usr/bin/env python3
"""pdf_export.py - Convert *-FINAL.pptx to PDF for phase P8.1-PDF-EXPORT."""
import argparse, os, shutil, subprocess, sys, tempfile
from pathlib import Path
def _find_pptx(run_dir):
    c=sorted(Path(run_dir).glob("*-FINAL.pptx")); c=[p for p in c if not p.name.startswith("~$")]; return c[0] if c else None
def _find_lo():
    for cmd in ("libreoffice","soffice"):
        if shutil.which(cmd): return cmd
    return None
def main():
    ap=argparse.ArgumentParser(description="Convert *-FINAL.pptx to PDF")
    ap.add_argument("--run-dir",required=True); args=ap.parse_args()
    MB=51200; rd=Path(args.run_dir)
    if not rd.is_dir(): print(f"[pdf_export] ERROR: {rd} not a directory",file=sys.stderr); sys.exit(1)
    pp=_find_pptx(rd)
    if pp is None: print(f"[pdf_export] ERROR: no *-FINAL.pptx in {rd}",file=sys.stderr); sys.exit(4)
    ds=pp.name.replace("-FINAL.pptx",""); od=rd/"working"/"deliverables"; od.mkdir(parents=True,exist_ok=True)
    op=od/f"{ds}-FINAL.pdf"
    print(f"[pdf_export] Converting {pp.name}",file=sys.stderr)
    lo=_find_lo()
    if lo is None: print("[pdf_export] ERROR: LibreOffice not found",file=sys.stderr); sys.exit(3)
    with tempfile.TemporaryDirectory(prefix="pdf_export_") as td:
        tp=Path(td)/pp.name; shutil.copy2(pp,tp)
        r=subprocess.run([lo,"--headless","--convert-to","pdf","--outdir",td,str(tp)],capture_output=True,text=True,timeout=300)
        if r.returncode!=0: print(f"[pdf_export] ERROR: conversion failed",file=sys.stderr); sys.exit(1)
        tpdf=Path(td)/pp.name.replace(".pptx",".pdf")
        if not tpdf.exists(): print("[pdf_export] ERROR: no PDF produced",file=sys.stderr); sys.exit(1)
        shutil.copy2(tpdf,op)
    sz=op.stat().st_size
    if sz<MB: print(f"[pdf_export] ERROR: {op.name} {sz}B < {MB}B floor",file=sys.stderr); sys.exit(2)
    print(f"[pdf_export] OK: {op} ({sz:,} bytes)",file=sys.stderr)
if __name__=="__main__": main()
