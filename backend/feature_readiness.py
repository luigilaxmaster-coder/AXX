"""Local capability registry for user-visible Axx features."""
from pathlib import Path


FEATURES = {
    'spatial_intelligence': {
        'title': 'Spatial Intelligence',
        'requirements': (
            ('magic_pen_capture', 'Captura y selección de Magic Pen', 'ready', 'Captura y revisiones locales están disponibles.', None),
            ('validated_plan', 'Contrato visual validado', 'ready', 'Plan, patch, referencias y presupuestos se validan en backend.', None),
            ('semantic_assets', 'Fábrica de ensamblajes semánticos', 'partial', 'Incluye un ensamblaje conceptual de motor monocilíndrico con cuatro piezas; no crea CAD arbitrario.', None),
            ('local_renderer', 'Canvas 2D/3D local', 'partial', 'Three.js y los diagramas se empaquetan localmente; WebGL y la superficie Windows se comprueban en ejecución.', {'type': 'open_magic_pen'}),
            ('teaching_timeline', 'Voz, subtítulos y pasos', 'partial', 'La narración y el subtítulo siguen cada paso; no hay alineación temporal por palabra.', None),
            ('guided_computer_use', 'Guía y verificación de interfaz', 'partial', 'La guía existente observa y verifica la ventana; una guía no ejecuta comandos por cuenta propia.', {'type': 'open_magic_pen'}),
            ('visual_qa', 'Control de escena', 'partial', 'El visor comprueba WebGL, conteo de piezas y valores finitos cuando se monta.', None),
        ),
    },
}


def readiness(feature_id, magic_pen, root):
    if feature_id not in FEATURES:
        raise ValueError('La función solicitada no está registrada.')
    manifest = FEATURES[feature_id]
    capabilities = magic_pen.capabilities()
    providers = [*capabilities.get('vision', []), *capabilities.get('codex_vision', [])]
    requirements = [{'id': key, 'label': label, 'status': state, 'evidence': evidence, 'action': action}
                    for key, label, state, evidence, action in manifest['requirements']]
    renderer = Path(root) / '1.AXX' / 'scripts' / 'three.module.min.js'
    if not renderer.is_file():
        next(item for item in requirements if item['id'] == 'local_renderer').update(status='setup_required', evidence='No se encontró el módulo Three.js local.',
                                action={'type': 'install_desktop_bundle'})
    provider_rows = []
    for provider in providers:
        cached = magic_pen.spatial_verified.get((provider['name'], provider['model']))
        provider_rows.append({**provider, 'status': 'ready' if cached else 'not_verified',
                              'text_diagram': bool(cached.get('text_diagram')) if cached else False,
                              'evidence': ('El modelo devolvió texto; Axx generó un diagrama 2D local. No se ha certificado la localización visual.'
                                           if cached and cached.get('text_diagram') else
                                           'Prueba de imagen y plan 3D validado completada.' if cached and provider.get('spatial_3d') else
                                           'Prueba de imagen y plan 2D validado completada.' if cached else
                                           'Aún no se ha probado imagen y plan visual para esta conexión.'),
                              'action': {'type': 'verify', 'provider': provider['name'], 'model': provider['model']}})
    verified = any(row['status'] == 'ready' for row in provider_rows)
    if not provider_rows:
        status = 'setup_required'
        requirements.append({'id': 'visual_provider', 'label': 'Proveedor visual autorizado', 'status': status,
                             'evidence': 'No hay un proveedor con visión y autorización de coste existente.',
                             'action': {'type': 'open_provider_settings'}})
    elif not verified:
        status = 'not_verified'
    elif any(row['status'] != 'ready' for row in requirements):
        status = 'partial'
    else:
        status = 'ready'
    return {'feature_id': feature_id, 'title': manifest['title'], 'status': status,
            'requirements': requirements, 'providers': provider_rows, 'provider_status': 'ready' if verified else 'not_verified',
            'verification_policy': 'Solo se ejecuta una prueba externa al solicitar verify; GET no consulta proveedores.'}
