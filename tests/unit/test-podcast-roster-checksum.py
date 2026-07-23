#!/usr/bin/env python3
"""U035: Unit tests for roster/ledger checksum integrity."""
import hashlib,hmac,json,unittest
K="_checksum"
def v(raw):
    try:d=json.loads(raw)
    except json.JSONDecodeError:raise ValueError("not valid JSON")
    if not isinstance(d,dict):raise ValueError("not a JSON object")
    s=d.get(K)
    if s is None:return
    o={k:v for k,v in d.items() if k!=K}
    c=json.dumps(o,sort_keys=True,ensure_ascii=False,separators=(",",":"))
    a=hashlib.sha256(c.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(str(s),a):
        raise ValueError("checksum MISMATCH")
def c(r):
    r.pop(K,None)
    raw=json.dumps(r,sort_keys=True,ensure_ascii=False,separators=(",",":"))
    r[K]=hashlib.sha256(raw.encode("utf-8")).hexdigest();return r
def b(**kw):
    r=dict(state=kw.get("state","received"),job_id=kw.get("job_id","t"),updated_at=kw.get("updated_at","t"),sqlite_job_id=kw.get("sqlite_job_id","t"))
    for k,v in kw.items():
        if k not in("state","job_id","updated_at","sqlite_job_id"):r[k]=v
    return r
class TV(unittest.TestCase):
    def test_valid(self):r=b(state="p");c(r);v(json.dumps(r,indent=2))
    def test_corrupt(self):
        r=b(state="x");c(r);r["state"]="y"
        with self.assertRaises(ValueError)as e:v(json.dumps(r,indent=2))
        self.assertIn("checksum MISMATCH",str(e.exception))
    def test_trunc(self):
        r=b();c(r);raw=json.dumps(r,indent=2)
        with self.assertRaises(ValueError):v(raw[:-30])
    def test_missing(self):r=b();v(json.dumps(r,indent=2))
    def test_badjson(self):
        with self.assertRaises(ValueError)as e:v("not json")
        self.assertIn("not valid JSON",str(e.exception))
    def test_notdict(self):
        with self.assertRaises(ValueError)as e:v("[1]")
        self.assertIn("not a JSON object",str(e.exception))
    def test_inject(self):
        r=b();c(r);r["bad"]="x"
        with self.assertRaises(ValueError)as e:v(json.dumps(r,indent=2))
        self.assertIn("checksum MISMATCH",str(e.exception))
    def test_reprod(self):self.assertEqual(c(b(state="a",p="x"))[K],c(b(state="a",p="x"))[K])
    def test_diff(self):self.assertNotEqual(c(b(state="a"))[K],c(b(state="b"))[K])
    def test_stable(self):self.assertEqual(c(dict(sqlite_job_id="x",state="p",job_id="x",updated_at="t"))[K],c(dict(updated_at="t",state="p",sqlite_job_id="x",job_id="x"))[K])
class TC(unittest.TestCase):
    def test_embed(self):self.assertEqual(len(c(b())[K]),64)
    def test_replace(self):r=b();o=c(r)[K];r["state"]="p";self.assertNotEqual(o,c(r)[K])
    def test_self(self):r=b();c(r);v(json.dumps(r,indent=2))
if __name__=="__main__":unittest.main(verbosity=2)
