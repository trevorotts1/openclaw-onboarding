import sys, time, runpy, os, traceback, collections
o=time.monotonic; os_=time.sleep; o0=o(); log=collections.Counter()
off=[0.0]
time.monotonic=lambda: o()-o0+540+off[0]
def sl(x):
    st=traceback.extract_stack(); fr=st[-2]
    if fr.filename.endswith("load_governor.py") and fr.lineno==365:
        log[tuple(f"{os.path.basename(s.filename)}:{s.lineno}" for s in st[-4:-2])]+=x; off[0]+=x; return  # account, skip
    os_(x)
time.sleep=sl
p=sys.argv[1]; sys.path.insert(0,os.path.dirname(os.path.abspath(p)))
try: runpy.run_path(p,run_name="__main__")
except SystemExit as e: print("exit",e.code)
print("poll-limiter sleep total %.1f"%sum(log.values()))
for k,v in log.most_common(5): print(k,round(v,1))
