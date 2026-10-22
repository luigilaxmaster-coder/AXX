"""Build a read-only, indexed recipe archive; catalog prose is never executable code."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

def build(source, destination, report_path):
    source=Path(source).resolve(); records={}; priorities={}; inventory=[]; rejected=[]; stats=Counter()
    def ingest(raw, origin, draft=False):
        stats['jsonl_files']+=1
        for number,line in enumerate(raw.decode('utf-8-sig').splitlines(),1):
            if not line.strip():continue
            try:r=json.loads(line)
            except (ValueError,RecursionError):rejected.append({'source':origin,'line':number,'reason':'invalid_json'});continue
            if not isinstance(r,dict):continue
            key=r.get('id',r.get('recipe_id',''))
            if not isinstance(key,str) or not re.fullmatch(r'AXX-[A-Za-z0-9_.-]{1,120}',key):continue
            stats['record_versions']+=1
            if draft:stats['draft_versions_excluded']+=1;continue
            if not isinstance(r.get('steps'),list) or not r['steps']:continue
            if len(line.encode('utf-8'))>512*1024:rejected.append({'source':origin,'line':number,'reason':'record_too_large'});continue
            # Reviewed revisions outrank the base delivery. Dated paths sort chronologically.
            score=(('REVISADO' in origin.upper()), origin)
            if key in priorities and score<=priorities[key]:continue
            priorities[key]=score
            records[key]={'id':key,'title':str(r.get('title',r.get('titulo',key))),
                'description':str(r.get('objective',r.get('intent',r.get('description','')))),
                'category':str(r.get('category','Procedimientos')),'source_member':origin,
                'source_status':'DOCUMENTED_NOT_EXECUTED','execution_enabled':False,
                'recipe':r,'record_sha256':hashlib.sha256(line.encode()).hexdigest()}
    files=[p for p in sorted(source.rglob('*')) if p.is_file() and p.suffix.lower() in ('.md','.json','.jsonl','.zip','.txt')]
    def read(file):
        return file, file.read_bytes()
    # The authorized Drive folder may hydrate each small file on demand.
    # Read independently, then process in deterministic path order.
    with ThreadPoolExecutor(max_workers=8) as pool:
      for number,(file,raw) in enumerate(pool.map(read,files),1):
        rel=file.relative_to(source).as_posix()
        if number % 50 == 0:print(f'Inventariados {number}/{len(files)} archivos',flush=True)
        inventory.append({'path':rel,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
        draft=any(tag in rel.upper() for tag in ('BORRADOR','NO_APROBADO'))
        if file.suffix.lower()=='.jsonl':ingest(raw,rel,draft)
        elif file.suffix.lower()=='.zip':
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    members=archive.infolist()
                    if sum(m.file_size for m in members)>256*1024*1024:raise ValueError('archive_size')
                    for member in members:
                        name=PurePosixPath(member.filename)
                        if name.is_absolute() or '..' in name.parts or member.file_size>64*1024*1024:raise ValueError('unsafe_member')
                        if name.suffix=='.jsonl':ingest(archive.read(member),rel+'!'+member.filename,draft or 'BORRADOR' in member.filename.upper())
            except (ValueError,zipfile.BadZipFile) as exc:rejected.append({'source':rel,'reason':str(exc)})
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    summaries=[{k:v for k,v in records[key].items() if k!='recipe'} for key in sorted(records)]
    with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        def write(name,content):
            info=zipfile.ZipInfo(name,(2026,10,22,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,json.dumps(content,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
        write('index.json',{'version':1,'records':summaries})
        for key in sorted(records):write('recipes/'+key+'.json',records[key])
    report={'source':'Instrucciones Axx','source_url':'https://drive.google.com/drive/folders/15eBbqsdPagfqWto0ULvsx9gjpLme4dgJ',
        'files':len(inventory),'full_recipes':len(records),'stats':dict(stats),'rejected':rejected,'inventory':inventory,
        'archive_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
        'execution_policy':'Documentation only. Only separately implemented typed adapters can execute.'}
    Path(report_path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='inventory'},ensure_ascii=True))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('destination');p.add_argument('report');a=p.parse_args();build(a.source,a.destination,a.report)
