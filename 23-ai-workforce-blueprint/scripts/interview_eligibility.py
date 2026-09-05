"""One eligibility policy: advisory review permits building, errors never do."""
def eligible_status(status):
    return status in ('pass','needs-review')

def eligible_returncode(code):
    try:return int(code) in (0,2)
    except (TypeError,ValueError):return False

if __name__=='__main__':
    import json,sys
    mode,value=sys.argv[1:]
    eligible=eligible_returncode(value) if mode=='rc' else eligible_status(value)
    print(json.dumps({'eligible':eligible,'advisory':value in ('needs-review','2'),'policyVersion':1}))
    raise SystemExit(0 if eligible else 1)
