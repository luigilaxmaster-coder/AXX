"""Prepare reviewable hunks for another Axx stage without copying whole files."""
from __future__ import annotations
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'evidence/axx-connect/baseline-20261020-164023'
OUT = ROOT / 'evidence/axx-connect/overlay'


def main():
    paths = [ROOT/'backend/server.py', ROOT/'1.AXX/Axx.html', ROOT/'1.AXX/scripts/axx-connect.js',
             ROOT/'1.AXX/scripts/test-axx-connect.cjs', ROOT/'1.AXX/scripts/test-desktop-frontend.cjs', ROOT/'package.json',ROOT/'.gitignore',ROOT/'requirements-axx-connect.txt']
    paths.append(ROOT/'evidence/axx-connect/auth-decision.md')
    for directory in ('backend/connect','docs/axx-connect','plugins'):
        paths.extend(path for path in (ROOT/directory).rglob('*') if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc')
    paths.extend(path for path in (ROOT/'scripts').iterdir() if path.is_file() and ('axx-connect' in path.name or 'axx-plugin-host' in path.name))
    paths = sorted(set(paths))
    manifest, patches = [], []
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        before = BASE / relative
        data = path.read_bytes()
        previous = before.read_bytes() if before.exists() else b''
        note = None
        if relative == '.gitignore':
            previous = data
            for line in (b'.venv-axx-connect/\n', b'.venv-axx-connect-build/\n', b'**/endpoint.dpapi\n', b'**/endpoint.tmp\n'):
                previous = previous.replace(line, b'')
            note = 'Base reconstructed only by removing the four known added ignore entries; review this hunk manually.'
        if previous == data:
            continue
        record = {'path':relative,'change':'update' if previous else 'new',
                  'base_sha256':hashlib.sha256(previous).hexdigest() if previous else None,
                  'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
        if note: record['base_note'] = note
        manifest.append(record)
        old = previous.decode('utf-8-sig').splitlines(keepends=True)
        new = data.decode('utf-8-sig').splitlines(keepends=True)
        patches.append(''.join(difflib.unified_diff(old,new,fromfile='a/'+relative if previous else '/dev/null',tofile='b/'+relative)))
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'source.patch').write_text(''.join(patches),encoding='utf-8',newline='\n')
    (OUT/'manifest.json').write_text(json.dumps({'baseline':str(BASE),'git_repository':False,'files':manifest},indent=2),encoding='utf-8')
    (OUT/'README.md').write_text('''# Overlay de Axx Connect

Este parche se compara con la copia de fuentes previa a Connect. No es un commit ni certifica la instalación nativa.

El stage `build/phased-ux-20261020` tiene cambios propios. Revisar y combinar por hunks; no copiar `backend/server.py` ni `Axx.html` completos. `git apply --check source.patch` puede detectar diferencias antes de aplicar; no usar opciones de fuerza ni reset/clean. El manifiesto contiene hashes base/resultado y declara la excepción de `.gitignore`.

Archivos nuevos: proveedor, servicio y registro compartidos, servidor MCP, transporte HTTP, UI discreta, tests, plugin, scripts y documentación. El HTML cambia decoder, Nueva conversación, un script externo y tres hunks para que Escape no cancele tareas. No hay cambios de Rust, hotkeys OS, versión nativa ni instalador del otro stage.

El stage combinado C3 separa `axx-ui-escape` de `axx-cancel`: este último puede conservarse para Cancelar explícito con dueño. Esa variante nativa requiere revisión y pruebas propias; no copiar el retiro del listener HTML sobre un canal cuyo significado ya cambió. La raíz conserva Rust anterior, por lo que sus fuentes aisladas no acreditan el contrato nativo combinado de Escape.

Construcción posterior: `scripts/build-axx-connect.ps1` añade el SDK MCP a un entorno de build y delega al build existente. Instalar/probar desde el stage combinado con su propio contrato de foco/Esc y gate visual. La configuración y credenciales del usuario no forman parte del parche.
''',encoding='utf-8')
    print(json.dumps({'files':len(manifest),'patch':str(OUT/'source.patch')},indent=2))

if __name__ == '__main__':
    main()
