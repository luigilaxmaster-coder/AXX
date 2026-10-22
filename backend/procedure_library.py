"""Read-only access to imported instructions. No document field grants execution."""
import json
from pathlib import Path
import re
import zipfile


class ProcedureLibrary:
    def __init__(self, path):
        self.path = Path(path)
        self.records = {}
        self.error = None
        try:
            with zipfile.ZipFile(self.path) as archive:
                info = archive.getinfo('index.json')
                if info.file_size > 24 * 1024 * 1024:
                    raise ValueError('Índice demasiado grande')
                index = json.loads(archive.read(info))
                if index.get('version') != 1 or not isinstance(index.get('records'), list) or len(index['records']) > 20000:
                    raise ValueError('Índice inválido')
                records = {}
                for row in index['records']:
                    key = row['id']
                    if not isinstance(key, str) or not re.fullmatch(r'AXX-[A-Za-z0-9_.-]{1,120}', key) or key in records:
                        raise ValueError('ID inválido o duplicado')
                    if archive.getinfo('recipes/' + key + '.json').file_size > 1024 * 1024:
                        raise ValueError('Procedimiento demasiado grande')
                    records[key] = {k: str(row.get(k, ''))[:3000] for k in
                                    ('id', 'title', 'description', 'category', 'source_member', 'record_sha256')}
                self.records = records
        except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
            self.error = 'Procedimientos no disponibles: ' + type(exc).__name__

    def get(self, key):
        if key not in self.records:
            return None
        with zipfile.ZipFile(self.path) as archive:
            value = json.loads(archive.read('recipes/' + key + '.json'))
        recipe = value.get('recipe')
        if value.get('id') != key or not isinstance(recipe, dict) or not isinstance(recipe.get('steps'), list):
            raise ValueError('Contenido del procedimiento inválido')
        return {'id': key, 'recipe': recipe, 'source_member': self.records[key]['source_member'],
                'source_status': 'DOCUMENTED_NOT_EXECUTED', 'execution_enabled': False}
