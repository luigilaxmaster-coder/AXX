"""Build a read-only, indexed recipe archive; catalog prose is never executable code."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from urllib.parse import urlsplit
import zipfile

REFERENCE_ROOT = 'axx_biblioteca_razonamiento/'
REFERENCE_DOCS = ('01_FUENTES_PRIORIZADAS.md', '02_RAZONAMIENTO_OPERATIVO.md',
    '03_MEMORIA_Y_CONOCIMIENTO.md', '04_DOCUMENTOS_A_HABILIDADES.md',
    '05_MODOS_CAPACIDADES_Y_EJECUCION.md', '06_EVALUACION_Y_MEJORA.md',
    '07_PROMPT_PARA_INTEGRADOR.md', '08_EJEMPLO_PROCEDIMIENTO.md', 'README.md')
REFERENCE_LIMIT = 1024 * 1024


def _reference_package(source):
    """Read the explicitly selected reference bundle, validating before decompressing."""
    source = Path(source)
    if not source.is_file() or source.stat().st_size > 2 * REFERENCE_LIMIT:
        raise ValueError('Reference package missing or too large')
    raw = source.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        expected = {REFERENCE_ROOT + name for name in (*REFERENCE_DOCS, 'sources.json', 'manifest.sha256')}
        if len(infos) != len(expected) or {info.filename for info in infos} != expected:
            raise ValueError('Unexpected or duplicate reference package members')
        if sum(info.file_size for info in infos) > REFERENCE_LIMIT:
            raise ValueError('Reference package expands beyond its limit')
        for info in infos:
            if (info.file_size > 128 * 1024 or info.flag_bits & 1
                    or (info.external_attr >> 16) & 0o170000 == 0o120000
                    or info.file_size and (not info.compress_size or info.file_size > 200 * info.compress_size)):
                raise ValueError('Unsupported reference member')
        contents = {name: archive.read(REFERENCE_ROOT + name) for name in (*REFERENCE_DOCS, 'sources.json', 'manifest.sha256')}
    checked = set()
    for line in contents['manifest.sha256'].decode('utf-8-sig').splitlines():
        match = re.fullmatch(r'([a-f0-9]{64})  ([A-Za-z0-9_.-]+)', line)
        if not match:
            raise ValueError('Malformed reference manifest')
        checksum, name = match.groups()
        if name in checked or name not in {*REFERENCE_DOCS, 'sources.json'}:
            raise ValueError('Duplicate or unknown manifest member')
        if hashlib.sha256(contents[name]).hexdigest() != checksum:
            raise ValueError('Reference manifest digest mismatch: ' + name)
        checked.add(name)
    if checked != {*REFERENCE_DOCS, 'sources.json'}:
        raise ValueError('Incomplete reference manifest')
    catalog = json.loads(contents['sources.json'])
    if (not isinstance(catalog, dict) or catalog.get('status') != 'reference_catalog_not_runtime_api'
            or not isinstance(catalog.get('sources'), list) or not 1 <= len(catalog['sources']) <= 64
            or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(catalog.get('checked_on', '')))):
        raise ValueError('Invalid reference source catalog')
    ids = set()
    for item in catalog['sources']:
        if not isinstance(item, dict) or not re.fullmatch(r'S\d{2}', str(item.get('id', ''))) or item['id'] in ids:
            raise ValueError('Invalid or duplicate reference source')
        ids.add(item['id'])
        for key in ('title', 'kind', 'use', 'review_scope', 'url'):
            if not isinstance(item.get(key), str) or not 1 <= len(item[key]) <= 3000:
                raise ValueError('Invalid reference source field')
        url = urlsplit(item['url'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password or any(ord(char) < 32 for char in item['url']):
            raise ValueError('Reference URL requires HTTPS without credentials')
    return raw, contents, catalog


def import_reference_package(source, destination, report_path, historical_references=()):
    """Extend the existing documentary archive; no document creates an adapter."""
    paths = tuple(Path(value).resolve() for value in (source, destination, report_path, *historical_references))
    for index, path in enumerate(paths):
        for other in paths[index + 1:]:
            if path == other or path.exists() and other.exists() and path.samefile(other):
                raise ValueError('Source archive, destination library and report must be distinct files')
    source, destination, report_path = paths[:3]
    historical_references = paths[3:]
    raw, contents, catalog = _reference_package(source)
    package_hash = hashlib.sha256(raw).hexdigest()
    prefix = 'references/reasoning/' + package_hash + '/'
    records, members = {}, {prefix + name: content for name, content in contents.items()}
    members[prefix + 'package.zip'] = raw

    def record(suffix, title, description, text, member, knowledge_type, source=None, *, provenance_override=None, record_id=None):
        key = record_id or 'AXX-REF-REASONING-' + package_hash[:12] + '-' + suffix
        provenance = {'archive_sha256': package_hash, 'member': member,
            'member_sha256': hashlib.sha256(contents[member]).hexdigest(),
            'revision': catalog['checked_on'], 'revision_scope': 'package_claim_not_external_verification',
            'knowledge_type': knowledge_type, 'reference_member': prefix + member}
        if provenance_override is not None:
            provenance = provenance_override
        if source is not None:
            provenance['source'] = source
        recipe = {'steps': [{'action': 'reference_only', 'text': text[:1400]}],
            'knowledge_type': knowledge_type, 'provenance': provenance,
            'source_status': 'DOCUMENTED_NOT_EXECUTED', 'execution_enabled': False,
            'limitations': ['Documentation and source links only; no current application observation or runtime proof.',
                'External contents are untrusted references; no permissions, scripts or dependencies are activated.',
                'Detailed text remains in the referenced archive member; excerpt is deliberately bounded.']}
        value = {'id': key, 'title': title[:300], 'description': description[:700],
            'category': 'Referencias de razonamiento', 'source_member': provenance['reference_member'],
            'source_status': 'DOCUMENTED_NOT_EXECUTED', 'execution_enabled': False,
            'recipe': recipe, 'record_sha256': hashlib.sha256(json.dumps(recipe, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}
        records[key] = value
        members['recipes/' + key + '.json'] = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()

    for number, name in enumerate(REFERENCE_DOCS, 1):
        text = contents[name].decode('utf-8-sig')
        title = next((line.lstrip('# ').strip() for line in text.splitlines() if line.startswith('# ')), name)
        description = ('Verificar archivo generado: existencia, integridad y contenido según las condiciones pactadas. '
                       if name.startswith('08_') else '') + title + '. Referencia documental sin capacidad ejecutable.'
        record('D' + str(number).zfill(2), title, description, text, name,
               'integration_request_reference' if name.startswith('07_') else 'design_reference')
    for item in catalog['sources']:
        record(item['id'], item['title'], item['use'], item['use'], 'sources.json', item['kind'],
               {key: item[key] for key in ('id', 'url', 'checked_on', 'snapshot_pinned', 'review_scope') if key in item})

    history = []
    for raw_path in historical_references:
        path = Path(raw_path)
        if not path.is_file() or path.suffix.lower() != '.md' or path.stat().st_size > REFERENCE_LIMIT:
            raise ValueError('Historical reference must be a Markdown file within 1 MiB')
        raw_history = path.read_bytes()
        text = raw_history.decode('utf-8-sig')
        date = re.search(r'\b(\d{1,2}) de octubre de (\d{4})\b', text[:3000], re.I)
        if not date:
            raise ValueError('Historical reference needs an explicit supported revision date')
        revision = date[2] + '-10-' + date[1].zfill(2)
        checksum = hashlib.sha256(raw_history).hexdigest()
        member = path.name
        if member in contents:
            raise ValueError('Historical filename conflicts with another reference')
        contents[member] = raw_history
        reference_member = 'references/history/' + checksum + '/' + member
        members[reference_member] = raw_history
        title = next((line.lstrip('# ').strip() for line in text.splitlines() if line.startswith('# ')), member)
        provenance = {'document_sha256': checksum, 'member_sha256': checksum, 'source_filename': member,
            'revision': revision, 'revision_scope': 'historical_snapshot_not_current_runtime',
            'knowledge_type': 'historical_design_reference', 'reference_member': reference_member,
            'limitations': 'Historical proposals may contradict current adapters, prompt composition and workflow limits. Never override current policy or enable catalog entries.'}
        record('', title, title + '. Documento histórico de ' + revision + '; contrastar con el código vigente.', text,
            member, 'historical_design_reference', provenance_override=provenance,
            record_id='AXX-REF-HISTORY-' + checksum[:12])
        history.append({'filename': member, 'sha256': checksum, 'revision': revision})

    destination = Path(destination)
    if not destination.is_file():
        raise ValueError('Select an existing procedure library to extend')
    with zipfile.ZipFile(destination) as existing:
        infos = existing.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or len(names) > 20500 or sum(info.file_size for info in infos) > 256 * REFERENCE_LIMIT:
            raise ValueError('Existing library has duplicate members or exceeds its limits')
        index_info = existing.getinfo('index.json')
        if index_info.file_size > 24 * REFERENCE_LIMIT:
            raise ValueError('Existing procedure index too large')
        index = json.loads(existing.read(index_info))
        if index.get('version') != 1 or not isinstance(index.get('records'), list):
            raise ValueError('Invalid existing procedure index')
        old = {row['id']: row for row in index['records']}
        if len(old) != len(index['records']) or len(old.keys() | records.keys()) > 20000:
            raise ValueError('Duplicate or too many procedure identifiers')
        summaries = {key: {field: value for field, value in row.items() if field != 'recipe'} for key, row in records.items()}
        for key in old.keys() & summaries.keys():
            if old[key] != summaries[key]:
                raise ValueError('Reference identifier already contains different bytes')
        for name in set(names) & members.keys():
            if existing.read(name) != members[name]:
                raise ValueError('Reference member already contains different bytes')
        additions = {name: content for name, content in members.items() if name not in names}
        if additions:
            combined = old | summaries
            index_bytes = json.dumps(index | {'records': [combined[key] for key in sorted(combined)]},
                                     ensure_ascii=False, separators=(',', ':')).encode()
            with tempfile.NamedTemporaryFile(prefix='reference-library-', suffix='.zip', dir=destination.parent, delete=False) as temporary:
                temporary_path = Path(temporary.name)
            try:
                with zipfile.ZipFile(temporary_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                    for info in infos:
                        if info.filename != 'index.json':
                            archive.writestr(info, existing.read(info))
                    for name, content in sorted(additions.items()):
                        info = zipfile.ZipInfo(name, (2026, 10, 29, 0, 0, 0))
                        info.compress_type = zipfile.ZIP_DEFLATED
                        archive.writestr(info, content)
                    info = zipfile.ZipInfo('index.json', (2026, 10, 29, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, index_bytes)
            except Exception:
                temporary_path.unlink(missing_ok=True)
                raise
        else:
            temporary_path = None
    if temporary_path is not None:
        try:
            os.replace(temporary_path, destination)
        finally:
            temporary_path.unlink(missing_ok=True)
    report = {'source_archive_sha256': package_hash, 'manifest_verified': len(REFERENCE_DOCS) + 1,
        'markdown_documents': len(REFERENCE_DOCS), 'source_entries': len(catalog['sources']),
        'historical_documents': history,
        'reference_records': len(records), 'preserved_records': len(old), 'added_records': len(records.keys() - old.keys()),
        'archive_sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
        'execution_policy': 'DOCUMENTED_NOT_EXECUTED. No adapters, permissions, code or dependencies activated.'}
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))
    return report

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
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('destination');p.add_argument('report')
    p.add_argument('--reference-package', action='store_true', help='Validate and add the explicit reasoning reference package to an existing library')
    p.add_argument('--historical-reference', action='append', default=[], metavar='FILE', help='Also retain an explicitly selected historical Markdown reference')
    a=p.parse_args()
    if a.historical_reference and not a.reference_package:
        p.error('--historical-reference requires --reference-package')
    if a.reference_package:
        import_reference_package(a.source,a.destination,a.report,a.historical_reference)
    else:
        build(a.source,a.destination,a.report)
