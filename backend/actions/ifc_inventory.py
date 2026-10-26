"""Read IFC identity and declared length units; export a new, verifiable inventory CSV."""
import csv
import io
import math
from pathlib import Path
import threading

from .file_inspection import hash_file, validate_path
from .process_runner import _artifact_path


def inspect_ifc(raw):
    import ifcopenshell
    from ifcopenshell.util.unit import get_project_unit, get_full_unit_name, calculate_unit_scale
    path = validate_path(raw)
    if path.suffix.lower() != '.ifc' or path.stat().st_size > 40 * 1024 * 1024:
        raise ValueError('Selecciona un IFC STEP local de hasta 40 MiB')
    before = hash_file(str(path), threading.Event())
    model = ifcopenshell.open(str(path))
    if len(model.by_type('IfcProject')) != 1: raise ValueError('El IFC requiere exactamente un proyecto')
    unit = get_project_unit(model, 'LENGTHUNIT')
    if unit is None: raise ValueError('El proyecto IFC no declara unidad de longitud')
    scale = calculate_unit_scale(model)
    if not math.isfinite(scale) or scale <= 0: raise ValueError('Escala de longitud inválida')
    rows, identifiers = [], set()
    for item in model:
        if not item.is_a('IfcElement'): continue
        guid = item.GlobalId
        if not guid or guid in identifiers: raise ValueError('GUID IFC ausente o duplicado')
        ifcopenshell.guid.expand(guid)
        identifiers.add(guid)
        name = item.Name or ''
        if len(name) > 200: raise ValueError('Nombre IFC mayor de 200 caracteres; no se trunca')
        rows.append({'GlobalId': guid, 'IfcClass': item.is_a(), 'Name': name, 'Count': 1})
        if len(rows) > 500: raise ValueError('El inventario admite hasta 500 elementos; selecciona un IFC acotado')
    if not rows: raise ValueError('No hay elementos IFC para inventariar')
    if hash_file(str(path), threading.Event()) != before: raise ValueError('El IFC cambió durante la lectura')
    return {**before, 'schema': model.schema, 'length_unit': get_full_unit_name(unit), 'length_scale_to_metre': scale,
            'elements': sorted(rows, key=lambda row: row['GlobalId']), 'verification': 'ifc_identity_and_declared_units',
            'geometry_verified': False}


class IfcInventoryTool:
    name, version = 'ifc_inventory_csv', '1.0.0'
    description = 'IFC inventory preserving element GUIDs and declared units; no geometric quantity inference'

    def verify_preconditions(self, inputs):
        try:
            if not isinstance(inputs, dict) or set(inputs) != {'source', 'destination'}: raise ValueError('Parámetros IFC inválidos')
            source = validate_path(inputs['source'])
            if source.suffix.lower() != '.ifc' or source.stat().st_size > 40 * 1024 * 1024: raise ValueError('Se requiere IFC de hasta 40 MiB')
            if not isinstance(inputs['destination'], str) or Path(inputs['destination']).suffix.lower() != '.csv':
                raise ValueError('El destino debe ser un CSV nuevo')
            return True, 'Origen y destino tipados'
        except (OSError, ValueError, TypeError) as exc: return False, str(exc)

    def execute_cancellable(self, inputs, workspace_root, cancelled):
        from .artifact_verification import run_inspector
        from .tools import ToolResult
        created = False
        try:
            valid, reason = self.verify_preconditions(inputs)
            if not valid: raise ValueError(reason)
            output = _artifact_path(inputs['destination'], workspace_root)
            if output.exists(): raise ValueError('El destino ya existe; no se sobrescribe')
            data = run_inspector('ifc', inputs['source'], cancelled)
            text = io.StringIO(newline='')
            fields = ['GlobalId', 'IfcClass', 'Name', 'Count', 'LengthUnit', 'LengthScaleToMetre']
            writer = csv.DictWriter(text, fieldnames=fields)
            writer.writeheader()
            for row in data['elements']:
                writer.writerow(row | {'LengthUnit': data['length_unit'], 'LengthScaleToMetre': data['length_scale_to_metre']})
            payload = text.getvalue().encode('utf-8-sig')
            if cancelled.is_set(): raise ValueError('Exportación IFC cancelada')
            output.parent.mkdir(parents=True, exist_ok=True)
            output = _artifact_path(inputs['destination'], workspace_root)
            with output.open('xb') as stream:
                created = True
                stream.write(payload)
            if output.read_bytes() != payload: raise ValueError('El CSV no coincide con el inventario IFC')
            if hash_file(inputs['source'], cancelled)['sha256'] != data['sha256']: raise ValueError('El origen cambió')
            return ToolResult(True, output={**hash_file(str(output), cancelled), 'elements': len(data['elements']),
                'source_sha256': data['sha256'], 'schema': data['schema'], 'length_unit': data['length_unit'],
                'numeric_column': 'Count', 'delimiter': ',', 'geometry_verified': False},
                evidence={'verification': 'ifc_guids_units_and_csv_readback'})
        except Exception as exc:
            return ToolResult(False, error=str(exc)[:600], evidence={'effect_uncertain': created, 'cancelled': cancelled.is_set()})

    def verify_postconditions(self, inputs, result):
        try:
            valid = (result.success and hash_file(result.output['path'], threading.Event())['sha256'] == result.output['sha256']
                     and hash_file(inputs['source'], threading.Event())['sha256'] == result.output['source_sha256'])
            return bool(valid), 'Inventario y origen comprobados'
        except (ValueError, OSError, KeyError): return False, 'No se verificó el inventario'
