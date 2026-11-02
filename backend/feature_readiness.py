"""Local capability registry for user-visible Axx features."""
from pathlib import Path


FEATURES = {
    'spatial_intelligence': {
        'title': 'Spatial Intelligence',
        'requirements': (
            ('magic_pen_capture', 'Captura y selección de Magic Pen', 'ready', 'Captura y revisiones locales están disponibles.', None),
            ('validated_plan', 'Contrato visual validado', 'ready', 'SpatialPresentationPlan v1 valida el plan antes de mostrarlo.', None),
            ('local_renderer', 'Three.js empaquetado localmente', 'ready', 'El renderer se carga desde assets locales.', None),
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
        requirements[-1].update(status='setup_required', evidence='No se encontró el módulo Three.js local.',
                                action={'type': 'install_desktop_bundle'})
    provider_rows = []
    for provider in providers:
        cached = magic_pen.spatial_verified.get((provider['name'], provider['model']))
        provider_rows.append({**provider, 'status': 'ready' if cached else 'not_verified',
                              'evidence': 'Prueba local de imagen y JSON estructurado completada.' if cached else
                                          'Aún no se ha probado imagen y salida estructurada para esta conexión.',
                              'action': {'type': 'verify', 'provider': provider['name'], 'model': provider['model']}})
    verified = any(row['status'] == 'ready' for row in provider_rows)
    if verified:
        status = 'ready'
    elif provider_rows:
        status = 'not_verified'
    else:
        status = 'setup_required'
        requirements.append({'id': 'visual_provider', 'label': 'Proveedor visual autorizado', 'status': status,
                             'evidence': 'No hay un proveedor con visión y autorización de coste existente.',
                             'action': {'type': 'open_provider_settings'}})
    return {'feature_id': feature_id, 'title': manifest['title'], 'status': status,
            'requirements': requirements, 'providers': provider_rows,
            'verification_policy': 'Solo se ejecuta una prueba externa al solicitar verify; GET no consulta proveedores.'}
