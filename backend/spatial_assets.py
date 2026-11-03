"""Deterministic, conceptual assemblies. No generated code, remote assets or physics."""
import math


def engine_asset(asset):
    if (not isinstance(asset, dict) or set(asset) != {'kind', 'scale'}
            or asset['kind'] != 'single_cylinder_engine' or type(asset['scale']) not in (int, float)
            or not math.isfinite(asset['scale']) or not .2 <= asset['scale'] <= 2):
        raise ValueError('El ensamblaje requiere kind=single_cylinder_engine y escala entre 0.2 y 2.')
    scale = asset['scale']
    parts = [
        ('o1', 'Cilindro', 'engine_cylinder', [2.4, 2.8, 2.4], [0, 1.7, 0], '#617b99', [3, 0, 0]),
        ('o2', 'Pistón', 'piston', [1.8, .8, 1.8], [0, 1.7, 0], '#438ee8', [0, 2, 0]),
        ('o3', 'Biela', 'connecting_rod', [.45, 2.2, .4], [0, .2, 0], '#df786d', [-2, 0, 0]),
        ('o4', 'Cigüeñal', 'crankshaft', [2.8, .8, .8], [0, -1.2, 0], '#e2ad52', [0, -2, 0]),
    ]
    return {'fidelity': 'conceptual', 'objects': [
        {'id': ident, 'label': label, 'shape': shape, 'size': [v * scale for v in size],
         'position': [v * scale for v in position], 'color': color, 'explode': [v * scale for v in explode]}
        for ident, label, shape, size, position, color, explode in parts], 'arrows': []}
