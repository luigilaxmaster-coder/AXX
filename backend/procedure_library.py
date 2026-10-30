"""Read-only access to imported instructions. No document field grants execution."""
from datetime import date
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

MAX_INDEX_BYTES = 24 * 1024 * 1024
MAX_MEMBER_BYTES = 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_REFERENCES = 24


class ProcedureLibrary:
    def __init__(self, path):
        self.path = Path(path)
        self.records = {}
        self.error = None
        try:
            with zipfile.ZipFile(self.path) as archive:
                self.records = {key: {field: str(row.get(field, ''))[:3000] for field in
                    ('id', 'title', 'description', 'category', 'source_member', 'record_sha256')}
                    for key, row in self._index(archive).items()}
        except (OSError, ValueError, KeyError, TypeError, UnicodeError, RecursionError, zipfile.BadZipFile) as exc:
            self.error = 'Procedimientos no disponibles: ' + type(exc).__name__

    @staticmethod
    def _read(archive, name, maximum=MAX_MEMBER_BYTES):
        info = archive.getinfo(name)
        if info.file_size > maximum or info.flag_bits & 1 or (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError('Miembro documental inválido o demasiado grande')
        return archive.read(info)

    @classmethod
    def _index(cls, archive):
        infos = archive.infolist()
        if (len(infos) > 20500 or len({info.filename for info in infos}) != len(infos)
                or sum(info.file_size for info in infos) > MAX_ARCHIVE_BYTES):
            raise ValueError('Biblioteca duplicada o demasiado grande')
        index = json.loads(cls._read(archive, 'index.json', MAX_INDEX_BYTES))
        if (not isinstance(index, dict) or type(index.get('version')) is not int or index['version'] != 1
                or not isinstance(index.get('records'), list) or len(index['records']) > 20000):
            raise ValueError('Índice inválido')
        records = {}
        for row in index['records']:
            if not isinstance(row, dict): raise ValueError('Registro del índice inválido')
            key = row.get('id')
            if not isinstance(key, str) or not re.fullmatch(r'AXX-[A-Za-z0-9_.-]{1,120}', key) or key in records:
                raise ValueError('ID inválido o duplicado')
            if archive.getinfo('recipes/' + key + '.json').file_size > MAX_MEMBER_BYTES:
                raise ValueError('Procedimiento demasiado grande')
            records[key] = row
        return records

    @staticmethod
    def _reference(reference):
        fields = {'document_id', 'record_sha256', 'member_sha256', 'revision'}
        if not isinstance(reference, dict) or set(reference) != fields:
            raise ValueError('Referencia documental inválida')
        key = reference['document_id']
        if not isinstance(key, str) or not re.fullmatch(r'AXX-REF-(?:REASONING-[a-f0-9]{12}-[DS][0-9]{2}|HISTORY-[a-f0-9]{12})', key):
            raise ValueError('ID documental inválido')
        for field in ('record_sha256', 'member_sha256'):
            if not isinstance(reference[field], str) or not re.fullmatch(r'[a-f0-9]{64}', reference[field]):
                raise ValueError('Hash documental inválido')
        revision = reference['revision']
        if not isinstance(revision, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', revision) or date.fromisoformat(revision).isoformat() != revision:
            raise ValueError('Revisión documental inválida')
        return {field: reference[field] for field in ('document_id', 'record_sha256', 'member_sha256', 'revision')}

    @classmethod
    def _get(cls, archive, records, key, expected_reference):
        if key not in records:
            if expected_reference is not None: raise ValueError('La referencia documental ya no está disponible')
            return None
        value = json.loads(cls._read(archive, 'recipes/' + key + '.json'))
        if not isinstance(value, dict): raise ValueError('Contenido del procedimiento inválido')
        recipe = value.get('recipe')
        if value.get('id') != key or not isinstance(recipe, dict) or not isinstance(recipe.get('steps'), list):
            raise ValueError('Contenido del procedimiento inválido')
        result = {'id': key, 'recipe': recipe, 'source_member': records[key].get('source_member', ''),
                  'source_status': 'DOCUMENTED_NOT_EXECUTED', 'execution_enabled': False}
        if not key.startswith('AXX-REF-'): return result
        provenance = recipe.get('provenance')
        if not isinstance(provenance, dict): raise ValueError('Procedencia documental inválida')
        reference = cls._reference({'document_id': key, 'record_sha256': records[key].get('record_sha256'),
            'member_sha256': provenance.get('member_sha256'), 'revision': provenance.get('revision')})
        member = provenance.get('reference_member')
        if (not isinstance(member, str) or len(member) > 3000 or '\\' in member
                or PurePosixPath(member).is_absolute() or any(part in ('.', '..') for part in member.split('/'))
                or member != result['source_member'] or member != value.get('source_member')):
            raise ValueError('Miembro documental incoherente')
        if key.startswith('AXX-REF-REASONING-'):
            package_hash, source = provenance.get('archive_sha256'), provenance.get('member')
            if (not isinstance(package_hash, str) or not re.fullmatch(r'[a-f0-9]{64}', package_hash)
                    or not isinstance(source, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,255}', source)
                    or member != 'references/reasoning/' + package_hash + '/' + source
                    or not key.startswith('AXX-REF-REASONING-' + package_hash[:12] + '-')
                    or provenance.get('revision_scope') != 'package_claim_not_external_verification'):
                raise ValueError('Procedencia del paquete incoherente')
        else:
            source = provenance.get('source_filename')
            if (not isinstance(source, str) or not 1 <= len(source) <= 255 or '/' in source or '\\' in source
                    or provenance.get('document_sha256') != reference['member_sha256']
                    or key != 'AXX-REF-HISTORY-' + reference['member_sha256'][:12]
                    or member != 'references/history/' + reference['member_sha256'] + '/' + source
                    or provenance.get('revision_scope') != 'historical_snapshot_not_current_runtime'):
                raise ValueError('Procedencia histórica incoherente')
        if (any(item.get('source_status') != 'DOCUMENTED_NOT_EXECUTED' or item.get('execution_enabled') is not False
                for item in (records[key], value, recipe))
                or recipe.get('knowledge_type') != provenance.get('knowledge_type')
                or not recipe['steps'] or any(not isinstance(step, dict) or step.get('action') != 'reference_only' for step in recipe['steps'])):
            raise ValueError('La referencia documental no concede ejecución')
        # Legacy catalog hashes cover original JSONL lines; canonical hashing applies only to imported AXX-REF records.
        digest = hashlib.sha256(json.dumps(recipe, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        document = cls._read(archive, member)
        if (digest != reference['record_sha256'] or digest != value.get('record_sha256')
                or hashlib.sha256(document).hexdigest() != reference['member_sha256']):
            raise ValueError('La integridad documental cambió')
        if expected_reference is not None and reference != expected_reference:
            raise ValueError('La identidad documental cambió; vuelve a revisar la fuente')
        result.update(document_reference=reference, reference_text=document.decode('utf-8-sig'))
        return result

    def get(self, key, *, expected_reference=None):
        if expected_reference is not None:
            expected_reference = self._reference(expected_reference)
            if expected_reference['document_id'] != key: raise ValueError('La referencia pertenece a otro documento')
        if not isinstance(key, str) or key not in self.records and not key.startswith('AXX-REF-'): return None
        try:
            with zipfile.ZipFile(self.path) as archive:
                return self._get(archive, self._index(archive), key, expected_reference)
        except (OSError, KeyError, TypeError, UnicodeError, RecursionError, zipfile.BadZipFile) as exc:
            raise ValueError('Referencia documental no disponible o inválida') from exc

    def resolve_references(self, references):
        if references is None: return []
        if not isinstance(references, list) or len(references) > MAX_REFERENCES:
            raise ValueError('Se admiten hasta 24 referencias documentales')
        unique = {}
        for reference in references:
            reference = self._reference(reference)
            key = reference['document_id']
            if key in unique and unique[key] != reference: raise ValueError('Referencias documentales contradictorias')
            unique[key] = reference
        if not unique: return []
        try:
            with zipfile.ZipFile(self.path) as archive:
                records = self._index(archive)
                return [self._get(archive, records, key, reference)['document_reference'] for key, reference in unique.items()]
        except (OSError, KeyError, TypeError, UnicodeError, RecursionError, zipfile.BadZipFile) as exc:
            raise ValueError('Referencia documental no disponible o inválida') from exc
