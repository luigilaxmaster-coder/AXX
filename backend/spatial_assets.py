"""Deterministic, conceptual assemblies. No generated code, remote assets or physics.

Each generator is plain data: parts built from the renderer's allowlisted primitives, so
every provider (Codex or Claude) only chooses a `kind` and a `scale`; Axx builds the geometry.
Part tuple: (label, shape, size, position, color, explode[, rotation_degrees]).
"""
import math

# shortcut: primitives only (no lofted/curved surfaces); upgrade when a generator needs real meshes.
SPECS = {
    'single_cylinder_engine': {
        'about': 'motor didáctico de un cilindro (cilindro, pistón, biela, cigüeñal)',
        'parts': [
            ('Cilindro', 'engine_cylinder', [2.4, 2.8, 2.4], [0, 1.7, 0], '#617b99', [3, 0, 0]),
            ('Pistón', 'piston', [1.8, .8, 1.8], [0, 1.7, 0], '#438ee8', [0, 2, 0]),
            ('Biela', 'connecting_rod', [.45, 2.2, .4], [0, .2, 0], '#df786d', [-2, 0, 0]),
            ('Cigüeñal', 'crankshaft', [2.8, .8, .8], [0, -1.2, 0], '#e2ad52', [0, -2, 0]),
        ],
        'arrows': [],
    },
    'gothic_church': {
        'about': 'iglesia gótica (nave, cubierta, naves laterales, torres con agujas, rosetón, portal, ábside)',
        'parts': [
            ('Nave central', 'box', [2.2, 2, 4.8], [0, 1, 0], '#c9bba4', [0, 0, 0]),
            ('Cubierta de la nave', 'box', [1.5, 1.5, 4.9], [0, 2.3, 0], '#6f7f8f', [0, 2, 0], [0, 0, 45]),
            ('Nave lateral izquierda', 'box', [1.1, 1.2, 4], [-1.65, .6, .2], '#b8aa93', [-2.5, 0, 0]),
            ('Nave lateral derecha', 'box', [1.1, 1.2, 4], [1.65, .6, .2], '#b8aa93', [2.5, 0, 0]),
            ('Torre izquierda', 'box', [1, 3.2, 1], [-.85, 1.6, -2.6], '#d4c7b0', [-2.5, 0, -1]),
            ('Torre derecha', 'box', [1, 3.2, 1], [.85, 1.6, -2.6], '#d4c7b0', [2.5, 0, -1]),
            ('Aguja izquierda', 'cone', [1, 1.5, 1], [-.85, 3.95, -2.6], '#58697a', [-2.5, 2, -1]),
            ('Aguja derecha', 'cone', [1, 1.5, 1], [.85, 3.95, -2.6], '#58697a', [2.5, 2, -1]),
            ('Rosetón', 'torus', [.8, .8, .2], [0, 1.8, -3.1], '#4d7fb8', [0, 0, -2]),
            ('Portal', 'box', [.7, 1.1, .2], [0, .55, -2.5], '#7a5a3c', [0, 0, -2.5]),
            ('Ábside', 'cylinder', [1.8, 1.6, 1.8], [0, .8, 2.9], '#bfae94', [0, 0, 2.5]),
        ],
        'arrows': [],
    },
    'single_board_computer': {
        'about': 'placa electrónica tipo ordenador de placa única (SoC, memoria, GPIO, puertos USB/Ethernet/HDMI, alimentación, microSD)',
        'parts': [
            ('Placa PCB', 'box', [5, .12, 3.2], [0, 0, 0], '#1f7a4d', [0, 0, 0]),
            ('Procesador', 'box', [.9, .12, .9], [-.5, .12, .1], '#9aa3ad', [0, 2, 0]),
            ('Memoria RAM', 'box', [.7, .1, .5], [-.5, .1, 1.05], '#2b2b30', [0, 1.5, 0]),
            ('Chip inalámbrico', 'box', [.5, .1, .5], [.7, .1, .9], '#c8ced6', [0, 1.5, 0]),
            ('Cabecera GPIO', 'box', [3.4, .28, .3], [-.2, .2, -1.4], '#222226', [0, 1.5, -1]),
            ('Puerto USB 1', 'box', [.9, .55, .7], [2.1, .3, -.9], '#b9c0c8', [2, 0, 0]),
            ('Puerto USB 2', 'box', [.9, .55, .7], [2.1, .3, -.1], '#b9c0c8', [2, 0, 0]),
            ('Puerto Ethernet', 'box', [.9, .65, .8], [2.1, .35, .95], '#a7afb8', [2, 0, 0]),
            ('HDMI 1', 'box', [.5, .25, .4], [-1.2, .18, 1.45], '#8e959d', [0, 0, 1.5]),
            ('HDMI 2', 'box', [.5, .25, .4], [-.6, .18, 1.45], '#8e959d', [0, 0, 1.5]),
            ('Alimentación USB-C', 'box', [.55, .22, .45], [-2.1, .17, 1.4], '#8e959d', [-1.5, 0, 0]),
            ('Ranura microSD', 'box', [.7, .1, .6], [-2.05, .1, -.2], '#d0a640', [-1.5, 0, 0]),
            ('Controlador de energía', 'box', [.35, .1, .35], [-1.6, .1, .7], '#3a3a42', [0, 1.5, 0]),
        ],
        'arrows': [],
    },
    'gear_train': {
        'about': 'tren de engranajes de tres etapas con ejes y bancada',
        'parts': [
            ('Bancada', 'box', [4.9, .25, 2], [0, -1.5, 0], '#59636e', [0, -1.5, 0]),
            ('Engranaje motriz', 'cylinder', [1.6, .4, 1.6], [-1.7, 0, 0], '#e2ad52', [0, 0, 2], [90, 0, 0]),
            ('Engranaje intermedio', 'cylinder', [2.2, .4, 2.2], [.2, 0, 0], '#438ee8', [0, 0, 2.5], [90, 0, 0]),
            ('Engranaje conducido', 'cylinder', [1.2, .4, 1.2], [1.9, 0, 0], '#df786d', [0, 0, 3], [90, 0, 0]),
            ('Eje motriz', 'cylinder', [.22, 1.4, .22], [-1.7, 0, 0], '#9aa3ad', [0, 0, -2], [90, 0, 0]),
            ('Eje intermedio', 'cylinder', [.22, 1.4, .22], [.2, 0, 0], '#9aa3ad', [0, 0, -2], [90, 0, 0]),
            ('Eje conducido', 'cylinder', [.22, 1.4, .22], [1.9, 0, 0], '#9aa3ad', [0, 0, -2], [90, 0, 0]),
        ],
        'arrows': [(1, 2, 'Transmite giro'), (2, 3, 'Transmite giro')],
    },
    'distributed_service': {
        'about': 'arquitectura de software distribuida (cliente, balanceador, servicios, caché, cola, base de datos)',
        'parts': [
            ('Cliente', 'sphere', [1, 1, 1], [-4, 0, 0], '#438ee8', [-1, 0, 0]),
            ('Balanceador', 'box', [.8, .8, .8], [-2.4, 0, 0], '#e2ad52', [0, 1, 0]),
            ('Servicio A', 'box', [1, 1, 1], [-.6, 0, -1.3], '#617b99', [0, 0, -1]),
            ('Servicio B', 'box', [1, 1, 1], [-.6, 0, 1.3], '#617b99', [0, 0, 1]),
            ('Caché', 'cylinder', [.8, .6, .8], [1.4, .9, -1.3], '#df786d', [0, 1, 0]),
            ('Cola de mensajes', 'torus', [.9, .9, .3], [1.4, 0, 1.3], '#9a6fd1', [0, 0, 1]),
            ('Base de datos', 'cylinder', [1.2, 1.4, 1.2], [3.4, 0, 0], '#4e9f6a', [1, 0, 0]),
        ],
        'arrows': [(1, 2, 'Solicitud'), (2, 3, 'Solicitud'), (2, 4, 'Reenvía'), (3, 5, 'Reenvía'), (4, 5, 'Consulta'), (5, 6, 'Persiste'), (4, 6, 'Consulta')],
    },
}
KINDS = tuple(SPECS)
SCALE_RANGE = (.2, 2)


def asset_scene(asset):
    """Build the scene of a closed {'kind','scale'} asset reference; raises ValueError otherwise."""
    if (not isinstance(asset, dict) or set(asset) != {'kind', 'scale'}
            or asset['kind'] not in SPECS or type(asset['scale']) not in (int, float)
            or not math.isfinite(asset['scale']) or not SCALE_RANGE[0] <= asset['scale'] <= SCALE_RANGE[1]):
        raise ValueError(f'El ensamblaje requiere kind en {list(KINDS)} y escala entre {SCALE_RANGE[0]} y {SCALE_RANGE[1]}.')
    spec, scale = SPECS[asset['kind']], asset['scale']
    objects = []
    for index, (label, shape, size, position, color, explode, *rotation) in enumerate(spec['parts'], 1):
        item = {'id': f'o{index}', 'label': label, 'shape': shape, 'size': [max(v * scale, .05) for v in size],  # renderer minimum keeps thin parts (PCB, shafts) valid at small scale
                'position': [v * scale for v in position], 'color': color, 'explode': [v * scale for v in explode]}
        if rotation:
            item['rotation'] = list(rotation[0])
        objects.append(item)
    arrows = [{'from': f'o{a}', 'to': f'o{b}', 'label': label} for a, b, label in spec['arrows']]
    return {'fidelity': 'conceptual', 'objects': objects, 'arrows': arrows}


def catalog_text():
    return '; '.join(f'"{kind}" = {spec["about"]}' for kind, spec in SPECS.items())
