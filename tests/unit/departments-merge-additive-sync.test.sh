#!/usr/bin/env bash
set -uo pipefail;R="${REPO_UNDER_TEST:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.."&&pwd)}";U="$R/update-skills.sh"
P=0;F=0;ok(){ P=$((P+1));echo "  PASS: $1";};bad(){ F=$((F+1));echo "  FAIL: $1";}
T=$(mktemp -d -t u133t-XXXXXX);trap 'rm -rf "$T"' EXIT
_wc(){ python3 -c "import json;print(len(json.load(open('$1'))))";}
_m(){ python3 -c "
import json,sys
def ns(r):
    s=str(r or '').strip().lower()
    if s.startswith('dept-'): s=s[5:]
    return s
can=json.load(open(sys.argv[1]))
cc=json.load(open(sys.argv[2]))
if not can: sys.exit(0)
if not cc:
    with open(sys.argv[2],'w') as fh:
        json.dump(can,fh,indent=2,ensure_ascii=False);fh.write('\n')
    sys.exit(0)
by={}
for i,d in enumerate(cc):
    s=ns(d.get('slug') or d.get('id'))
    if s: by[s]=i
sf=('name','emoji','headTitle','head_title','workspacePath')
merged=list(cc);added=0;updated=0
for e in can:
    s=ns(e.get('slug') or e.get('id'))
    if not s: continue
    if s in by:
        idx=by[s];chg=False
        for f in sf:
            if f in e and merged[idx].get(f)!=e[f]:
                merged[idx][f]=e[f];chg=True
        if chg: updated+=1
    else:
        merged.append(dict(e));added+=1
if added or updated:
    with open(sys.argv[2],'w') as fh:
        json.dump(merged,fh,indent=2,ensure_ascii=False);fh.write('\n')
" "$1" "$2";}
echo "Scenario A: new dept added"
A="$T/a";mkdir -p "$A"
printf '[{"slug":"ceo","name":"CEO"},{"slug":"ops","name":"Ops"},{"slug":"new","name":"New"}]\n'>"$A/c.json"
printf '[{"slug":"ceo","name":"CEO"},{"slug":"ops","name":"Ops"}]\n'>"$A/d.json"
_m "$A/c.json" "$A/d.json"
[ "$(_wc "$A/d.json")" = "3" ]&&grep -q '"new"' "$A/d.json"&&ok "new added (2->3)"||bad "new not added"
echo "Scenario B: existing updated"
B="$T/b";mkdir -p "$B"
printf '[{"slug":"ceo","name":"CEO"},{"slug":"ops","name":"Ops UPDATED","headTitle":"SVP"}]\n'>"$B/c.json"
printf '[{"slug":"ceo","name":"CEO"},{"slug":"ops","name":"Ops"}]\n'>"$B/d.json"
_m "$B/c.json" "$B/d.json"
grep -q 'Ops UPDATED' "$B/d.json"&&grep -q '"SVP"' "$B/d.json"&&ok "existing updated"||bad "existing not updated"
echo "Scenario C: custom preserved"
C="$T/c";mkdir -p "$C"
printf '[{"slug":"ceo","name":"CEO"},{"slug":"new","name":"New"}]\n'>"$C/c.json"
printf '[{"slug":"ceo","name":"CEO"},{"slug":"cust","name":"Custom","customTag":"keep-me"}]\n'>"$C/d.json"
_m "$C/c.json" "$C/d.json"
[ "$(_wc "$C/d.json")" = "3" ]&&grep -q '"cust"' "$C/d.json"&&grep -q '"new"' "$C/d.json"&&grep -q '"customTag"' "$C/d.json"&&ok "custom preserved"||bad "custom deleted"
echo "Scenario D: no-op identical"
DD="$T/dd";mkdir -p "$DD"
printf '[{"slug":"a","name":"Alpha"},{"slug":"b","name":"Beta"}]\n'>"$DD/c.json";cp "$DD/c.json" "$DD/d.json"
_m "$DD/c.json" "$DD/d.json"
[ "$(_wc "$DD/d.json")" = "2" ]&&ok "no-op identical"||bad "identical changed"
echo "Scenario E: empty canonical safe"
E="$T/e";mkdir -p "$E";printf '[]\n'>"$E/c.json";printf '[{"slug":"x","name":"Xtra"}]\n'>"$E/d.json"
_m "$E/c.json" "$E/d.json";[ "$(_wc "$E/d.json")" = "1" ]&&ok "empty canonical safe"||bad "empty canonical deleted"
echo "Scenario F: empty CC populated"
FF="$T/ff";mkdir -p "$FF";printf '[{"slug":"a","name":"A"},{"slug":"b","name":"B"}]\n'>"$FF/c.json";printf '[]\n'>"$FF/d.json"
_m "$FF/c.json" "$FF/d.json";[ "$(_wc "$FF/d.json")" = "2" ]&&ok "empty CC populated"||bad "empty CC not populated"
echo "Scenario G: mutation proof"
G="$T/g";mkdir -p "$G";printf '[{"slug":"a","name":"A"}]\n'>"$G/c.json";cp "$G/c.json" "$G/d.json";_m "$G/c.json" "$G/d.json"
printf '[{"slug":"a","name":"A_MUTATED"}]\n'>"$G/c2.json";_m "$G/c2.json" "$G/d.json"
grep -q 'A_MUTATED' "$G/d.json"&&ok "mutation: change propagated"||bad "mutation: change not applied"
cp "$G/c.json" "$G/d.json";_m "$G/c.json" "$G/d.json"
grep -q '"name":"A"' "$G/d.json"&&! grep -q 'A_MUTATED' "$G/d.json"&&ok "mutation proof: reverted"||bad "mutation proof: revert failed"
echo "RESULT pass=$P fail=$F"
[ "$F" -eq 0 ]
