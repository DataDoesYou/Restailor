import os, re, json
base='alembic/versions'
issues=[]
revs={}
deps={}
for fn in os.listdir(base):
    if not fn.endswith('.py'): continue
    path=os.path.join(base,fn)
    with open(path,'r',encoding='utf-8') as f: txt=f.read()
    m=re.search(r'^revision\s*=\s*"([^"]+)"',txt, re.MULTILINE)
    if not m:
        m=re.search(r'^revision\s*:\s*str\s*=\s*"([^"]+)"',txt, re.MULTILINE)
    if not m: continue
    rev=m.group(1)
    revs[rev]=fn
    if len(rev)>32:
        issues.append({'type':'LONG_ID','rev':rev,'len':len(rev),'file':fn})
    dm=re.search(r'^down_revision\s*=\s*(.+)$',txt, re.MULTILINE)
    if not dm:
        dm=re.search(r'^down_revision\s*:\s*[^=]*=\s*(.+)$',txt, re.MULTILINE)
    if dm:
        raw=dm.group(1).split('#')[0].strip()
        downs=[]
        if raw.startswith(('(', '[')):
            raw2=raw.strip('()[]')
            for part in raw2.split(','):
                part=part.strip().strip('"\'')
                if part: downs.append(part)
        elif raw in ('None','None,'): downs=[]
        else:
            downs=[raw.strip().strip('"\'')]
        deps[rev]=downs
for rev, downs in deps.items():
    for d in downs:
        if d and d not in revs:
            issues.append({'type':'MISSING_DOWN_REV','rev':rev,'missing':d})
print(json.dumps({'total_revisions':len(revs),'issues':issues}, indent=2))
