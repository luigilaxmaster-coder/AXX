"""Unit and visual QA tests for Phase 2 (PR-03 & PR-04): SceneDocument v2, CAS Patches, and Diagram Studio."""
from __future__ import annotations

import unittest

from backend.spatial.diagram_studio import (
    auto_layout_diagram,
    check_diagram_qa,
    export_diagram_png,
    export_diagram_svg,
    export_diagram_to_mermaid,
    parse_mermaid_to_diagram,
    update_scene_diagram_node,
)
from backend.spatial.patches import (
    apply_scene_patch,
    redo_scene_patch,
    undo_scene_patch,
)
from backend.spatial.scene_document import (
    SceneDocumentError,
    SceneDocumentStore,
    StaleSceneRevisionError,
    import_presentation_plan_v1,
    validate_scene_document_v2,
)


class SceneDocumentAndDiagramStudioTests(unittest.TestCase):
    def test_mp_02_scene_document_v2_cas_patch_undo_redo_and_immutable_asset_hash(self):
        store = SceneDocumentStore(':memory:')
        self.addCleanup(store.close)

        plan_v1 = {
            'schema_version': '1.0',
            'kind': 'presentation',
            'title': 'Motor conceptual',
            'summary': 'Ensamblaje de prueba',
            'fidelity': 'conceptual',
            'steps': [{'id': 's1', 'title': 'Base', 'body': 'Cuerpo', 'narration': 'Paso uno', 'basis': 'observed'}],
            'scene': {
                'fidelity': 'conceptual',
                'objects': [
                    {'id': 'o1', 'label': 'Cilindro', 'shape': 'cylinder', 'size': [2, 3, 2], 'position': [0, 0, 0], 'color': '#438ee8'},
                ],
            },
            'diagram': {
                'nodes': [{'id': 'd1', 'label': 'Entrada principal', 'step_id': 's1', 'bounds': [0.1, 0.1, 0.25, 0.12]}],
                'edges': [],
            },
        }
        doc_v2 = import_presentation_plan_v1(
            plan_v1,
            document_id='scene-mp02',
            source_id='cap-001',
            source_revision=1,
        )
        created = store.create_document(doc_v2, operation_id='op-create-1')
        self.assertEqual(created['revision'], 1)

        # Apply incremental patch to o1 position and register a binary asset
        sha_v1 = '1' * 64
        patch_1 = {
            'document_id': 'scene-mp02',
            'base_revision': 1,
            'operation_id': 'op-patch-1',
            'target_object_ids': ['o1'],
            'allowed_paths': ['transform', 'name', 'assets'],
            'changes': [
                {
                    'op': 'asset.register',
                    'asset': {
                        'asset_id': 'asset-glb-1',
                        'sha256': sha_v1,
                        'mime_type': 'model/gltf-binary',
                        'size_bytes': 8192,
                        'license': 'CC-BY-4.0',
                    },
                },
                {
                    'op': 'object.update',
                    'object_id': 'o1',
                    'fields': {
                        'name': 'Cilindro principal',
                        'transform': {'position': [1.5, 2.0, -0.5], 'rotation': [0, 0, 0], 'scale': [1, 1, 1]},
                    },
                },
            ],
        }
        res_1 = apply_scene_patch(store, patch_1)
        self.assertEqual(res_1['revision'], 2)
        self.assertFalse(res_1['render_invalidation']['full_rebuild'])
        self.assertEqual(res_1['render_invalidation']['invalidated_object_ids'], ['o1'])

        # A retry replays its receipt. A different operation with the same stale revision conflicts.
        self.assertEqual(apply_scene_patch(store, patch_1), res_1)
        with self.assertRaises(StaleSceneRevisionError):
            apply_scene_patch(store, {**patch_1, 'operation_id': 'op-concurrent'})

        # Attempting to overwrite asset-glb-1 with a different sha256 must fail (MP-02)
        bad_asset_patch = {
            'document_id': 'scene-mp02',
            'base_revision': 2,
            'operation_id': 'op-bad-asset',
            'target_object_ids': [],
            'allowed_paths': ['assets'],
            'changes': [
                {
                    'op': 'asset.register',
                    'asset': {
                        'asset_id': 'asset-glb-1',
                        'sha256': '2' * 64,
                        'mime_type': 'model/gltf-binary',
                        'size_bytes': 4096,
                    },
                }
            ],
        }
        with self.assertRaises(SceneDocumentError):
            apply_scene_patch(store, bad_asset_patch)

        # Undo restores object o1 name and position deterministically
        undone = undo_scene_patch(store, 'scene-mp02', operation_id='op-undo-1')
        self.assertEqual(undone['revision'], 3)
        o1_undone = next(o for o in undone['document']['objects'] if o['id'] == 'o1')
        self.assertEqual(o1_undone['name'], 'Cilindro')
        self.assertEqual(o1_undone['transform']['position'], [0.0, 0.0, 0.0])

        # Redo reapplies the change
        redone = redo_scene_patch(store, 'scene-mp02', operation_id='op-redo-1')
        self.assertEqual(redone['revision'], 4)
        o1_redone = next(o for o in redone['document']['objects'] if o['id'] == 'o1')
        self.assertEqual(o1_redone['name'], 'Cilindro principal')
        self.assertEqual(o1_redone['transform']['position'], [1.5, 2.0, -0.5])

    def test_invariant_i07_blocks_unverified_cad_claims(self):
        # Image capture without verified BRep solid cannot claim cad_verified
        invalid_doc = {
            'schema_version': '2.0',
            'document_id': 'scene-fake-cad',
            'revision': 1,
            'mode': 'cad',
            'units': 'mm',
            'fidelity': 'cad_verified',
            'coordinate_system': {'up_axis': 'Z', 'handedness': 'right', 'origin': [0, 0, 0]},
            'source': {'kind': 'magic_pen_capture', 'source_id': 'cap-1', 'revision': 1},
            'objects': [
                {
                    'id': 'part-1',
                    'name': 'Pieza inferida',
                    'representation': 'primitive',
                    'fidelity': 'conceptual',
                    'measured_source': 'inferred',
                }
            ],
            'assets': [],
            'timeline': {'duration_seconds': 0, 'tracks': []},
        }
        with self.assertRaises(SceneDocumentError):
            validate_scene_document_v2(invalid_doc)

    def test_mp_04_diagram_studio_mermaid_edit_qa_and_export_without_clip_or_scripts(self):
        mermaid_src = """
        flowchart TD
            n1["Sensor Óptico de Precisión"] --> n2["Controlador PID Industrial"]
            n2 -->|señal PWM| n3["Actuador Hidráulico Principal"]
            custom_directive :: unsupported_feature
        """
        diagram = parse_mermaid_to_diagram(mermaid_src, style_template='architecture_c4')
        self.assertEqual(len(diagram['nodes']), 3)
        self.assertEqual(len(diagram['edges']), 2)
        self.assertEqual(diagram['unsupported_elements'], ['custom_directive :: unsupported_feature'])

        qa = check_diagram_qa(diagram)
        self.assertTrue(qa['passed'], f'Expected QA pass, got: {qa}')
        self.assertEqual(qa['overlaps'], [])
        self.assertEqual(qa['clipped_labels'], [])

        # Block XSS / foreignObject / remote URL injection in node labels
        with self.assertRaises(SceneDocumentError):
            auto_layout_diagram({
                'nodes': [{'id': 'bad', 'label': '<script>alert(1)</script>'}],
                'edges': [],
            })
        with self.assertRaises(SceneDocumentError):
            auto_layout_diagram({
                'nodes': [{'id': 'bad2', 'label': '<foreignObject>http://evil.tld</foreignObject>'}],
                'edges': [],
            })

        # Export SVG & PNG and verify labels are present and unclipped
        svg = export_diagram_svg(diagram)
        self.assertIn('<svg xmlns="http://www.w3.org/2000/svg"', svg)
        self.assertIn('Sensor Óptico de Precisión', svg)
        self.assertNotIn('<script', svg.lower())
        self.assertNotIn('foreignobject', svg.lower())

        png_bytes = export_diagram_png(diagram)
        self.assertTrue(png_bytes.startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertGreater(len(png_bytes), 1000)

        mermaid_out = export_diagram_to_mermaid(diagram)
        self.assertIn('n1["Sensor Óptico de Precisión"]', mermaid_out)
        self.assertIn('%% UNSUPPORTED: custom_directive :: unsupported_feature', mermaid_out)

        # Persist node edit in SceneDocumentStore
        store = SceneDocumentStore(':memory:')
        self.addCleanup(store.close)
        doc = store.create_document({
            'schema_version': '2.0',
            'document_id': 'diag-doc-1',
            'revision': 1,
            'mode': 'diagram',
            'units': 'unitless',
            'fidelity': 'conceptual',
            'coordinate_system': {'up_axis': 'Y', 'handedness': 'right', 'origin': [0, 0, 0]},
            'source': {'kind': 'user_spec', 'source_id': 'spec-1', 'revision': 1},
            'objects': [],
            'assets': [],
            'timeline': {'duration_seconds': 0, 'tracks': []},
            'diagram': diagram,
        })
        updated = update_scene_diagram_node(
            store,
            document_id='diag-doc-1',
            base_revision=doc['revision'],
            operation_id='op-edit-node-1',
            node_id='n2',
            label='Controlador PID Verificado',
        )
        self.assertEqual(updated['revision'], 2)
        n2 = next(n for n in updated['document']['diagram']['nodes'] if n['id'] == 'n2')
        self.assertEqual(n2['label'], 'Controlador PID Verificado')


if __name__ == '__main__':
    unittest.main()
