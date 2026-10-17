"""Check the public file selection and frozen source integrity, without APIs."""
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={'runs','build','dist','__pycache__','.git','.venv'}
PATTERNS={
    'provider_key':re.compile(r'(?:sk-ant-api\d+-[A-Za-z0-9_-]{25,}|sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{35,}|AIza[A-Za-z0-9_-]{30,})'),
    'private_key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'personal_local_path':re.compile(r'(?:C:[/\\]Users[/\\]|/Users/)[A-Za-z0-9_.-]+[/\\]')}

def selected_files():
    for file in sorted(ROOT.rglob('*')):
        if not file.is_file():continue
        relative=file.relative_to(ROOT)
        if set(relative.parts)&EXCLUDED or any(p.endswith('.egg-info') for p in relative.parts):continue
        if file.suffix in ('.pyc','.pyo','.log') or file.name in ('.env','.run.lock'):
            continue
        yield file

def main():
    hits=[];files=list(selected_files())
    for file in files:
        try:text=file.read_text('utf-8')
        except (UnicodeDecodeError,ValueError):continue
        for kind,pattern in PATTERNS.items():
            if pattern.search(text):hits.append({'file':file.relative_to(ROOT).as_posix(),'kind':kind})
    manifest=json.loads((ROOT/'redcommerce/data/FILES.json').read_text('utf-8'))
    mismatches=[name for name,digest in manifest.items() if hashlib.sha256((ROOT/'redcommerce/data'/name).read_bytes()).hexdigest()!=digest]
    selection={p.relative_to(ROOT).as_posix() for p in files}
    missing=[name for name in manifest if 'redcommerce/data/'+name not in selection]
    provenance=json.loads((ROOT/'SOURCE_PROVENANCE.json').read_text('utf-8'))
    ledger=ROOT/'redcommerce/data/benchmark/parallel/20260913-live-migration/provider.py'
    if hashlib.sha256(ledger.read_bytes()).hexdigest()!=provenance['runtime_extension']['provider.py']:
        mismatches.append('added persistent-ledger module')
    result={'pass':not hits and not mismatches and not missing,'selected_files':len(files),'frozen_files':len(manifest),
        'privacy_hits':hits,'frozen_source_mismatches':mismatches,'missing_frozen_files':missing,'network_calls':0}
    print(json.dumps(result,indent=2))
    return 0 if result['pass'] else 1

if __name__=='__main__':raise SystemExit(main())
