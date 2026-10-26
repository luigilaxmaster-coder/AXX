import csv
import tempfile
import threading
import unittest
from pathlib import Path
import ifcopenshell

from backend.actions.executor import ActionExecutor
from backend.actions.ifc_inventory import inspect_ifc


class IfcInventoryTests(unittest.TestCase):
    def fixture(self, path, unit=True, duplicate=False):
        model = ifcopenshell.file(schema='IFC4')
        units = model.create_entity('IfcUnitAssignment', Units=[model.create_entity('IfcSIUnit', UnitType='LENGTHUNIT', Prefix='MILLI', Name='METRE')]) if unit else None
        model.create_entity('IfcProject', GlobalId=ifcopenshell.guid.new(), Name='Fixture', UnitsInContext=units)
        guid = ifcopenshell.guid.new()
        model.create_entity('IfcWall', GlobalId=guid, Name='Muro ñ')
        if duplicate: model.create_entity('IfcWall', GlobalId=guid, Name='Duplicado')
        model.write(str(path))
        return guid

    def test_real_worker_csv_guid_units_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root/'model.ifc'
            guid = self.fixture(source)
            original = source.read_bytes()
            with ActionExecutor(root/'state.db', root) as executor:
                result = executor.execute_action('ifc_inventory_csv', {'source':str(source), 'destination':'inventory.csv'}, 'ifc-export')
                self.assertEqual(result['state'], 'succeeded', result)
                rows = list(csv.DictReader((root/'inventory.csv').read_text(encoding='utf-8-sig').splitlines()))
                self.assertEqual(rows[0]['GlobalId'], guid)
                self.assertEqual(rows[0]['Name'], 'Muro ñ')
                self.assertEqual(float(rows[0]['LengthScaleToMetre']), .001)
                self.assertFalse(result['output']['geometry_verified'])
                again = executor.execute_action('ifc_inventory_csv', {'source':str(source), 'destination':'inventory.csv'}, 'another')
                self.assertEqual(again['state'], 'failed')
                self.assertEqual(source.read_bytes(), original)

    def test_missing_units_and_duplicate_guid_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'model.ifc'
            self.fixture(source, unit=False)
            with self.assertRaises(ValueError): inspect_ifc(str(source))
            self.fixture(source, duplicate=True)
            with self.assertRaises(ValueError): inspect_ifc(str(source))
