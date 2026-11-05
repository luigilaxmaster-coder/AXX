"""Technical Shape & Component Registry for Axx Spatial Intelligence.

Provides a reusable library of 24+ parametric engineering components and shapes,
an instantiation engine that scales and reorients pieces at will, and an intelligent
analyzer that identifies needed parts, reuses stored shapes to save processing, and
automatically persists newly discovered shapes into a local dynamic registry.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Tuple, Union

LOCK = threading.RLock()

# Built-in technical component catalog (24+ detailed parametric shapes)
TECHNICAL_COMPONENTS: Dict[str, Dict[str, Any]] = {
    'hex_bolt': {
        'label': 'Tornillo de cabeza hexagonal',
        'category': 'fastener',
        'aliases': ['tornillo', 'bolt', 'perno', 'tornillo_hexagonal', 'screw'],
        'default_material': 'metal_polished',
        'default_color': '#cfd4da',
        'size': [0.7, 1.75, 0.7],
        'parts': [
            {'label': 'Cabeza hexagonal', 'shape': 'hexprism', 'size': [0.7, 0.35, 0.7], 'position': [0, 0.7, 0], 'material': 'metal_polished', 'color': '#cfd4da'},
            {'label': 'Espiga roscada', 'shape': 'cylinder', 'size': [0.38, 1.4, 0.38], 'position': [0, -0.175, 0], 'material': 'metal_brushed', 'color': '#a8b0b8'},
        ],
        'ports': {'head': [0, 0.875, 0], 'tip': [0, -0.875, 0], 'axis': [0, 1, 0]},
    },
    'hex_nut': {
        'label': 'Tuerca hexagonal métrica',
        'category': 'fastener',
        'aliases': ['tuerca', 'nut', 'hex_nut', 'tuerca_hexagonal'],
        'default_material': 'metal_polished',
        'default_color': '#cfd4da',
        'size': [0.75, 0.36, 0.75],
        'parts': [
            {'label': 'Cuerpo hexagonal roscado', 'shape': 'hexprism', 'size': [0.75, 0.36, 0.75], 'position': [0, 0, 0], 'material': 'metal_polished', 'color': '#cfd4da', 'param': 0.2},
        ],
        'ports': {'center': [0, 0, 0], 'axis': [0, 1, 0]},
    },
    'washer': {
        'label': 'Arandela plana métrica',
        'category': 'fastener',
        'aliases': ['arandela', 'washer', 'rondana', 'gasket_washer'],
        'default_material': 'metal_brushed',
        'default_color': '#b4bcc4',
        'size': [0.85, 0.08, 0.85],
        'parts': [
            {'label': 'Anillo plano', 'shape': 'tube', 'size': [0.85, 0.08, 0.85], 'position': [0, 0, 0], 'material': 'metal_brushed', 'color': '#b4bcc4', 'param': 0.45},
        ],
        'ports': {'center': [0, 0, 0], 'axis': [0, 1, 0]},
    },
    'spur_gear': {
        'label': 'Engranaje recto con cubo y chavetero',
        'category': 'motion',
        'aliases': ['engranaje', 'gear', 'rueda_dentada', 'pinion', 'spur_gear', 'cog'],
        'default_material': 'metal_anodized',
        'default_color': '#c68630',
        'size': [2.2, 0.5, 2.2],
        'parts': [
            {'label': 'Corona dentada exterior', 'shape': 'gear', 'size': [2.2, 0.4, 2.2], 'position': [0, 0, 0], 'material': 'metal_anodized', 'color': '#c68630', 'param': 16},
            {'label': 'Cubo de acoplamiento central', 'shape': 'cylinder', 'size': [0.65, 0.5, 0.65], 'position': [0, 0, 0], 'material': 'metal_brushed', 'color': '#9aa0a6'},
        ],
        'ports': {'axis_center': [0, 0, 0], 'axis': [0, 1, 0]},
    },
    'ball_bearing': {
        'label': 'Rodamiento rígido de bolas',
        'category': 'motion',
        'aliases': ['rodamiento', 'bearing', 'ruleman', 'balero', 'cojinete'],
        'default_material': 'metal_polished',
        'default_color': '#c5cdd6',
        'size': [2.2, 0.52, 2.2],
        'parts': [
            {'label': 'Pista exterior', 'shape': 'tube', 'size': [2.2, 0.5, 2.2], 'position': [0, 0, 0], 'material': 'metal_polished', 'color': '#c5cdd6', 'param': 0.16},
            {'label': 'Pista interior', 'shape': 'tube', 'size': [1.2, 0.52, 1.2], 'position': [0, 0, 0], 'material': 'metal_polished', 'color': '#b0b8c2', 'param': 0.22},
            {'label': 'Jaula con bolas', 'shape': 'torus', 'size': [1.7, 0.26, 1.7], 'position': [0, 0, 0], 'material': 'metal_brushed', 'color': '#dca638'},
        ],
        'ports': {'bore': [0, 0, 0], 'axis': [0, 1, 0]},
    },
    'keyed_shaft': {
        'label': 'Eje cilíndrico de transmisión con chaveta',
        'category': 'motion',
        'aliases': ['eje', 'shaft', 'arbol_transmision', 'keyed_shaft', 'eje_motor'],
        'default_material': 'metal_polished',
        'default_color': '#c2cacf',
        'size': [0.6, 3.2, 0.6],
        'parts': [
            {'label': 'Eje rectificado', 'shape': 'cylinder', 'size': [0.6, 3.2, 0.6], 'position': [0, 0, 0], 'material': 'metal_polished', 'color': '#c2cacf'},
            {'label': 'Chaveta longitudinal', 'shape': 'box', 'size': [0.12, 0.8, 0.14], 'position': [0.26, 0.4, 0], 'material': 'metal_brushed', 'color': '#828c96'},
        ],
        'ports': {'drive_end': [0, 1.6, 0], 'driven_end': [0, -1.6, 0], 'axis': [0, 1, 0]},
    },
    'v_pulley': {
        'label': 'Polea acanalada para correa trapezoidal',
        'category': 'motion',
        'aliases': ['polea', 'pulley', 'v_pulley', 'polea_correa'],
        'default_material': 'metal_anodized',
        'default_color': '#364050',
        'size': [2.4, 0.6, 2.4],
        'parts': [
            {'label': 'Disco con llanta exterior', 'shape': 'cylinder', 'size': [2.4, 0.45, 2.4], 'position': [0, 0, 0], 'material': 'metal_anodized', 'color': '#364050'},
            {'label': 'Garganta en V', 'shape': 'frustum', 'size': [2.4, 0.2, 2.4], 'position': [0, 0, 0], 'material': 'metal_polished', 'color': '#242c38', 'param': 0.72},
            {'label': 'Cubo de amarre al eje', 'shape': 'cylinder', 'size': [0.72, 0.6, 0.72], 'position': [0, 0, 0], 'material': 'metal_brushed', 'color': '#505b6c'},
        ],
        'ports': {'bore': [0, 0, 0], 'axis': [0, 1, 0]},
    },
    'coil_spring': {
        'label': 'Muelle / resorte helicoidal de compresión',
        'category': 'motion',
        'aliases': ['muelle', 'resorte', 'spring', 'coil', 'coil_spring'],
        'default_material': 'metal_polished',
        'default_color': '#4287f5',
        'size': [0.85, 2.2, 0.85],
        'parts': [
            {'label': 'Hélice helicoidal de acero', 'shape': 'coil', 'size': [0.85, 2.2, 0.85], 'position': [0, 0, 0], 'material': 'metal_polished', 'color': '#4287f5', 'param': 5.0},
        ],
        'ports': {'top_seat': [0, 1.1, 0], 'bottom_seat': [0, -1.1, 0], 'axis': [0, 1, 0]},
    },
    'l_bracket': {
        'label': 'Escuadra de montaje angular en L',
        'category': 'structural',
        'aliases': ['escuadra', 'bracket', 'soporte_l', 'l_bracket', 'angle_bracket'],
        'default_material': 'metal_brushed',
        'default_color': '#969fa8',
        'size': [1.4, 1.4, 0.8],
        'parts': [
            {'label': 'Perfil angular doblado', 'shape': 'l_bracket', 'size': [1.4, 1.4, 0.8], 'position': [0, 0, 0], 'material': 'metal_brushed', 'color': '#969fa8', 'param': 0.18},
        ],
        'ports': {'base_mount': [0, -0.7, 0], 'wall_mount': [-0.7, 0, 0]},
    },
    'u_channel_bar': {
        'label': 'Perfil estructural en U / Canal de acero',
        'category': 'structural',
        'aliases': ['perfil_u', 'u_channel', 'canal', 'channel_bar'],
        'default_material': 'metal_brushed',
        'default_color': '#868e98',
        'size': [1.0, 3.0, 0.8],
        'parts': [
            {'label': 'Viga con perfil en U', 'shape': 'u_channel', 'size': [1.0, 3.0, 0.8], 'position': [0, 0, 0], 'material': 'metal_brushed', 'color': '#868e98', 'param': 0.14},
        ],
        'ports': {'top': [0, 1.5, 0], 'bottom': [0, -1.5, 0]},
    },
    'i_beam_girder': {
        'label': 'Viga estructural en doble T / Perfil en I',
        'category': 'structural',
        'aliases': ['viga_i', 'i_beam', 'viga_doble_t', 'girder', 'viga_acero'],
        'default_material': 'metal_anodized',
        'default_color': '#4e5b6c',
        'size': [1.2, 3.2, 1.2],
        'parts': [
            {'label': 'Viga laminada en I', 'shape': 'i_beam', 'size': [1.2, 3.2, 1.2], 'position': [0, 0, 0], 'material': 'metal_anodized', 'color': '#4e5b6c', 'param': 0.12},
        ],
        'ports': {'top': [0, 1.6, 0], 'bottom': [0, -1.6, 0]},
    },
    'pipe_elbow_flanged': {
        'label': 'Codo de tubería a 90 grados con bridas',
        'category': 'fluid',
        'aliases': ['codo', 'pipe_elbow', 'codo_tuberia', 'elbow_joint'],
        'default_material': 'metal_polished',
        'default_color': '#447856',
        'size': [1.4, 1.4, 0.9],
        'parts': [
            {'label': 'Curva toroidal a 90°', 'shape': 'pipe_elbow', 'size': [1.2, 1.2, 0.5], 'position': [0, 0, 0], 'material': 'metal_polished', 'color': '#447856', 'param': 0.22},
            {'label': 'Brida de entrada', 'shape': 'flange', 'size': [0.9, 0.1, 0.9], 'position': [-0.6, 0, 0], 'rotation': [0, 0, 90], 'material': 'metal_brushed', 'color': '#366245'},
            {'label': 'Brida de salida', 'shape': 'flange', 'size': [0.9, 0.1, 0.9], 'position': [0, -0.6, 0], 'material': 'metal_brushed', 'color': '#366245'},
        ],
        'ports': {'inlet': [-0.65, 0, 0], 'outlet': [0, -0.65, 0]},
    },
    'flange_coupling': {
        'label': 'Brida de acoplamiento circular con tornillería',
        'category': 'fluid',
        'aliases': ['brida', 'flange', 'acoplamiento_brida', 'flange_coupling'],
        'default_material': 'metal_polished',
        'default_color': '#929ca7',
        'size': [1.8, 0.75, 1.8],
        'parts': [
            {'label': 'Plato circular con orificios', 'shape': 'flange', 'size': [1.8, 0.22, 1.8], 'position': [0, -0.22, 0], 'material': 'metal_polished', 'color': '#929ca7', 'param': 6},
            {'label': 'Cuello de unión', 'shape': 'tube', 'size': [0.85, 0.55, 0.85], 'position': [0, 0.15, 0], 'material': 'metal_brushed', 'color': '#78828d', 'param': 0.2},
        ],
        'ports': {'mating_face': [0, -0.33, 0], 'pipe_side': [0, 0.42, 0], 'axis': [0, 1, 0]},
    },
    'heatsink_extrusion': {
        'label': 'Disipador térmico con aletas paralelas',
        'category': 'thermal',
        'aliases': ['disipador', 'heatsink', 'radiador', 'cooling_fins'],
        'default_material': 'metal_anodized',
        'default_color': '#282a2d',
        'size': [2.0, 1.2, 2.4],
        'parts': [
            {'label': 'Aletas de disipación y base térmica', 'shape': 'heatsink', 'size': [2.0, 1.2, 2.4], 'position': [0, 0, 0], 'material': 'metal_anodized', 'color': '#282a2d', 'param': 7},
        ],
        'ports': {'thermal_base': [0, -0.6, 0]},
    },
    'butterfly_valve': {
        'label': 'Válvula de control tipo mariposa',
        'category': 'fluid',
        'aliases': ['valvula', 'valve', 'valvula_mariposa', 'butterfly_valve'],
        'default_material': 'metal_anodized',
        'default_color': '#1c5e93',
        'size': [1.6, 1.6, 1.6],
        'parts': [
            {'label': 'Cuerpo tubular de la válvula', 'shape': 'tube', 'size': [1.6, 0.8, 1.6], 'position': [0, 0, 0], 'material': 'metal_anodized', 'color': '#1c5e93', 'param': 0.16},
            {'label': 'Disco obturador pivotante', 'shape': 'cylinder', 'size': [1.28, 0.08, 1.28], 'position': [0, 0, 0], 'rotation': [0, 25, 0], 'material': 'metal_polished', 'color': '#f2ce54'},
            {'label': 'Eje de mando', 'shape': 'cylinder', 'size': [0.18, 1.5, 0.18], 'position': [0, 0, 0], 'material': 'metal_brushed', 'color': '#969da4'},
        ],
        'ports': {'flow_in': [0, 0, -0.4], 'flow_out': [0, 0, 0.4]},
    },
    'fan_impeller': {
        'label': 'Rotor / rodete axial con álabes inclinados',
        'category': 'motion',
        'aliases': ['ventilador', 'fan', 'rotor_ventilador', 'impeller', 'alabe'],
        'default_material': 'plastic',
        'default_color': '#263442',
        'size': [2.6, 0.6, 2.6],
        'parts': [
            {'label': 'Núcleo central del rodete', 'shape': 'cylinder', 'size': [0.8, 0.5, 0.8], 'position': [0, 0, 0], 'material': 'plastic', 'color': '#263442'},
            {'label': 'Corona aerodinámica de álabes', 'shape': 'gear', 'size': [2.6, 0.35, 2.6], 'position': [0, 0, 0], 'material': 'plastic', 'color': '#304254', 'param': 8},
        ],
        'ports': {'hub_bore': [0, 0, 0], 'axis': [0, 1, 0]},
    },
    'hydraulic_actuator': {
        'label': 'Cilindro hidráulico / Actuador lineal',
        'category': 'motion',
        'aliases': ['cilindro_hidraulico', 'actuador', 'hydraulic_cylinder', 'piston_hidraulico', 'linear_actuator'],
        'default_material': 'metal_anodized',
        'default_color': '#16425b',
        'size': [1.2, 4.4, 1.2],
        'parts': [
            {'label': 'Camisa cilíndrica exterior', 'shape': 'cylinder', 'size': [1.2, 2.6, 1.2], 'position': [0, -0.6, 0], 'material': 'metal_anodized', 'color': '#16425b'},
            {'label': 'Vástago cromado telescópico', 'shape': 'cylinder', 'size': [0.55, 2.2, 0.55], 'position': [0, 1.2, 0], 'material': 'metal_polished', 'color': '#dde4eb'},
            {'label': 'Rótula de amarre trasera', 'shape': 'torus', 'size': [0.65, 0.3, 0.65], 'position': [0, -2.0, 0], 'rotation': [90, 0, 0], 'material': 'metal_brushed', 'color': '#58a4b0'},
        ],
        'ports': {'rod_clevis': [0, 2.3, 0], 'base_clevis': [0, -2.0, 0], 'axis': [0, 1, 0]},
    },
    'shock_absorber': {
        'label': 'Amortiguador con resorte telescópico coaxial',
        'category': 'motion',
        'aliases': ['amortiguador', 'shock_absorber', 'suspension', 'strut'],
        'default_material': 'metal_anodized',
        'default_color': '#cc0022',
        'size': [1.0, 3.6, 1.0],
        'parts': [
            {'label': 'Cuerpo hidráulico amortiguador', 'shape': 'cylinder', 'size': [0.6, 2.8, 0.6], 'position': [0, 0, 0], 'material': 'metal_anodized', 'color': '#cc0022'},
            {'label': 'Muelle envolvente exterior', 'shape': 'coil', 'size': [1.0, 2.0, 1.0], 'position': [0, 0, 0], 'material': 'metal_polished', 'color': '#ea1c34', 'param': 6.0},
            {'label': 'Ojal superior', 'shape': 'capsule', 'size': [0.45, 0.45, 0.45], 'position': [0, 1.5, 0], 'material': 'metal_brushed', 'color': '#282a36'},
            {'label': 'Ojal inferior', 'shape': 'capsule', 'size': [0.45, 0.45, 0.45], 'position': [0, -1.5, 0], 'material': 'metal_brushed', 'color': '#282a36'},
        ],
        'ports': {'top_eyelet': [0, 1.7, 0], 'bottom_eyelet': [0, -1.7, 0]},
    },
    'electronic_enclosure': {
        'label': 'Caja estanca modular para electrónica',
        'category': 'electrical',
        'aliases': ['caja_electronica', 'enclosure', 'gabinete', 'electronic_box', 'carcasa_modulo'],
        'default_material': 'plastic',
        'default_color': '#36394e',
        'size': [3.3, 1.45, 2.3],
        'parts': [
            {'label': 'Cuerpo base con esquinas biseladas', 'shape': 'box', 'size': [3.2, 1.2, 2.2], 'position': [0, 0, 0], 'material': 'plastic', 'color': '#36394e', 'param': 0.12},
            {'label': 'Tapa atornillada superior', 'shape': 'box', 'size': [3.3, 0.22, 2.3], 'position': [0, 0.68, 0], 'material': 'plastic', 'color': '#d97258', 'param': 0.08},
        ],
        'ports': {'mount_base': [0, -0.6, 0]},
    },
    'stepper_motor_nema': {
        'label': 'Cuerpo de motor paso a paso híbrido (NEMA)',
        'category': 'electro-mechanical',
        'aliases': ['motor_paso_a_paso', 'stepper_motor', 'nema', 'motor_nema', 'stepper'],
        'default_material': 'metal_anodized',
        'default_color': '#223e4a',
        'size': [2.0, 3.2, 2.0],
        'parts': [
            {'label': 'Cuerpo prismático del estator', 'shape': 'box', 'size': [2.0, 2.2, 2.0], 'position': [0, 0, 0], 'material': 'metal_anodized', 'color': '#223e4a', 'param': 0.1},
            {'label': 'Corona frontal de centrado', 'shape': 'cylinder', 'size': [1.1, 0.2, 1.1], 'position': [0, 1.2, 0], 'material': 'metal_polished', 'color': '#258c80'},
            {'label': 'Eje rectificado de salida', 'shape': 'cylinder', 'size': [0.28, 1.0, 0.28], 'position': [0, 1.6, 0], 'material': 'metal_polished', 'color': '#e2be64'},
        ],
        'ports': {'flange_face': [0, 1.1, 0], 'shaft_tip': [0, 2.1, 0], 'axis': [0, 1, 0]},
    },
    'crimp_terminal': {
        'label': 'Terminal eléctrico de horquilla para cable',
        'category': 'electrical',
        'aliases': ['terminal', 'terminal_horquilla', 'crimp_terminal', 'conector_pala'],
        'default_material': 'metal_polished',
        'default_color': '#e89855',
        'size': [0.8, 1.7, 0.45],
        'parts': [
            {'label': 'Horquilla de contacto metálica', 'shape': 'u_channel', 'size': [0.8, 0.7, 0.12], 'position': [0, 0.45, 0], 'material': 'metal_polished', 'color': '#e89855', 'param': 0.26},
            {'label': 'Manguito prensacables aislado', 'shape': 'tube', 'size': [0.45, 0.95, 0.45], 'position': [0, -0.35, 0], 'material': 'rubber', 'color': '#dc6446', 'param': 0.18},
        ],
        'ports': {'fork_contact': [0, 0.8, 0], 'wire_entry': [0, -0.8, 0]},
    },
    'hinge_assembly': {
        'label': 'Bisagra articulada de dos alas con pasador',
        'category': 'structural',
        'aliases': ['bisagra', 'hinge', 'articulacion', 'pernio'],
        'default_material': 'metal_brushed',
        'default_color': '#666f77',
        'size': [1.7, 1.8, 0.24],
        'parts': [
            {'label': 'Pasador central cilíndrico', 'shape': 'cylinder', 'size': [0.22, 1.8, 0.22], 'position': [0, 0, 0], 'material': 'metal_polished', 'color': '#a4adb6'},
            {'label': 'Ala fija perforada', 'shape': 'box', 'size': [0.8, 1.6, 0.08], 'position': [-0.44, 0, 0], 'material': 'metal_brushed', 'color': '#666f77'},
            {'label': 'Ala móvil perforada', 'shape': 'box', 'size': [0.8, 1.6, 0.08], 'position': [0.44, 0, 0], 'material': 'metal_brushed', 'color': '#666f77'},
        ],
        'ports': {'pin_axis': [0, 0, 0], 'axis': [0, 1, 0]},
    },
    'injector_nozzle': {
        'label': 'Tobera / Boquilla de inyección cónica',
        'category': 'fluid',
        'aliases': ['tobera', 'nozzle', 'boquilla', 'injector_nozzle', 'inyector'],
        'default_material': 'metal_polished',
        'default_color': '#cfa06f',
        'size': [1.0, 1.8, 1.0],
        'parts': [
            {'label': 'Cuerpo hexagonal de roscado', 'shape': 'hexprism', 'size': [1.0, 0.6, 1.0], 'position': [0, -0.55, 0], 'material': 'metal_polished', 'color': '#cfa06f'},
            {'label': 'Cono convergente de descarga', 'shape': 'frustum', 'size': [0.9, 1.15, 0.9], 'position': [0, 0.32, 0], 'material': 'metal_polished', 'color': '#f4e7c7', 'param': 0.26},
        ],
        'ports': {'inlet': [0, -0.85, 0], 'orifice': [0, 0.9, 0], 'axis': [0, 1, 0]},
    },
    'potentiometer_knob': {
        'label': 'Mando / perilla de potenciómetro con indicador',
        'category': 'electrical',
        'aliases': ['perilla', 'knob', 'mando', 'potentiometer_knob', 'selector'],
        'default_material': 'plastic',
        'default_color': '#111827',
        'size': [1.4, 0.9, 1.4],
        'parts': [
            {'label': 'Cuerpo giratorio con chaflán', 'shape': 'chamfer_cylinder', 'size': [1.4, 0.9, 1.4], 'position': [0, 0, 0], 'material': 'plastic', 'color': '#111827', 'param': 0.1},
            {'label': 'Puntero visual de posición', 'shape': 'wedge', 'size': [0.14, 0.55, 0.22], 'position': [0, 0.2, 0.6], 'material': 'emissive', 'color': '#10b981'},
        ],
        'ports': {'shaft_mount': [0, -0.45, 0], 'axis': [0, 1, 0]},
    },
    'threaded_stud': {
        'label': 'Espárrago / varilla roscada con tuercas',
        'category': 'fastener',
        'aliases': ['esparrago', 'varilla_roscada', 'threaded_stud', 'stud_bolt'],
        'default_material': 'metal_brushed',
        'default_color': '#b8bec6',
        'size': [0.75, 3.0, 0.75],
        'parts': [
            {'label': 'Varilla roscada', 'shape': 'threaded_rod', 'size': [0.4, 3.0, 0.4], 'position': [0, 0, 0], 'material': 'metal_brushed', 'color': '#b8bec6', 'param': 18},
            {'label': 'Tuerca superior', 'shape': 'hexprism', 'size': [0.75, 0.32, 0.75], 'position': [0, 1.1, 0], 'material': 'metal_polished', 'color': '#cfd4da'},
            {'label': 'Tuerca inferior', 'shape': 'hexprism', 'size': [0.75, 0.32, 0.75], 'position': [0, -1.1, 0], 'material': 'metal_polished', 'color': '#cfd4da'},
        ],
        'ports': {'top': [0, 1.5, 0], 'bottom': [0, -1.5, 0], 'axis': [0, 1, 0]},
    },
    'square_frame_tube': {
        'label': 'Tubo estructural rectangular hueco',
        'category': 'structural',
        'aliases': ['tubo_rectangular', 'tubo_cuadrado', 'rect_tube', 'box_section', 'perfil_hueco'],
        'default_material': 'metal_brushed',
        'default_color': '#7d8791',
        'size': [1.0, 3.0, 1.0],
        'parts': [
            {'label': 'Perfil hueco rectangular', 'shape': 'rect_tube', 'size': [1.0, 3.0, 1.0], 'position': [0, 0, 0], 'material': 'metal_brushed', 'color': '#7d8791', 'param': 0.1},
        ],
        'ports': {'top': [0, 1.5, 0], 'bottom': [0, -1.5, 0]},
    },
    'pull_handle': {
        'label': 'Tirador / asa curva con bases',
        'category': 'hardware',
        'aliases': ['tirador', 'asa', 'handle', 'pull_handle', 'manija'],
        'default_material': 'metal_polished',
        'default_color': '#d0d5db',
        'size': [2.0, 1.1, 0.4],
        'parts': [
            {'label': 'Asa curvada', 'shape': 'arc', 'size': [2.0, 2.0, 0.4], 'position': [0, 0, 0], 'material': 'metal_polished', 'color': '#d0d5db', 'param': 180},
            {'label': 'Base izquierda', 'shape': 'cylinder', 'size': [0.32, 0.18, 0.32], 'position': [-0.84, -0.09, 0], 'material': 'metal_brushed', 'color': '#9aa2ab'},
            {'label': 'Base derecha', 'shape': 'cylinder', 'size': [0.32, 0.18, 0.32], 'position': [0.84, -0.09, 0], 'material': 'metal_brushed', 'color': '#9aa2ab'},
        ],
        'ports': {'mount_left': [-0.84, -0.18, 0], 'mount_right': [0.84, -0.18, 0]},
    },
    'knurled_knob': {
        'label': 'Pomo moleteado de apriete manual',
        'category': 'hardware',
        'aliases': ['pomo', 'pomo_moleteado', 'knurled_knob', 'thumb_screw', 'tornillo_mariposa'],
        'default_material': 'metal_polished',
        'default_color': '#c9ced4',
        'size': [1.2, 1.6, 1.2],
        'parts': [
            {'label': 'Cabeza moleteada', 'shape': 'knurled_cylinder', 'size': [1.2, 0.5, 1.2], 'position': [0, 0.55, 0], 'material': 'metal_polished', 'color': '#c9ced4', 'param': 28},
            {'label': 'Espiga roscada', 'shape': 'threaded_rod', 'size': [0.4, 1.1, 0.4], 'position': [0, -0.25, 0], 'material': 'metal_brushed', 'color': '#a9b0b8', 'param': 9},
        ],
        'ports': {'tip': [0, -0.8, 0], 'axis': [0, 1, 0]},
    },
    'slotted_mount_plate': {
        'label': 'Placa de montaje con ojales de ajuste',
        'category': 'structural',
        'aliases': ['placa_ranurada', 'mount_plate', 'placa_montaje', 'slotted_plate'],
        'default_material': 'metal_anodized',
        'default_color': '#3d4652',
        'size': [3.0, 0.2, 1.6],
        'parts': [
            {'label': 'Placa base', 'shape': 'box', 'size': [3.0, 0.2, 1.6], 'position': [0, 0, 0], 'material': 'metal_anodized', 'color': '#3d4652', 'param': 0.04},
            {'label': 'Ojal de ajuste izquierdo', 'shape': 'slot', 'size': [0.7, 0.3, 0.22], 'position': [-1.0, 0.02, 0], 'rotation': [90, 0, 0], 'material': 'rubber', 'color': '#15181c'},
            {'label': 'Ojal de ajuste derecho', 'shape': 'slot', 'size': [0.7, 0.3, 0.22], 'position': [1.0, 0.02, 0], 'rotation': [90, 0, 0], 'material': 'rubber', 'color': '#15181c'},
        ],
        'ports': {'top_face': [0, 0.1, 0], 'bottom_face': [0, -0.1, 0]},
    },
    'turbofan_rotor': {
        'label': 'Rotor de ventilador / turbofán',
        'category': 'propulsion',
        'aliases': ['turbofan', 'ventilador_turbofan', 'fan_rotor', 'fan_blades', 'rotor_ventilador', 'rotor_fan'],
        'default_material': 'metal_anodized',
        'default_color': '#1a1d24',
        'size': [6.0, 0.8, 6.0],
        'parts': [
            {'label': 'Buje y disco central', 'shape': 'cylinder', 'size': [2.2, 0.8, 2.2], 'position': [0, 0, 0], 'rotation': [90, 0, 0], 'material': 'metal_anodized', 'color': '#1a1d24'},
            {'label': 'Ojiva / cono central', 'shape': 'cone', 'size': [1.2, 1.4, 1.2], 'position': [0, 0, 0.7], 'rotation': [-90, 0, 0], 'material': 'metal_polished', 'color': '#d0d4dc'},
            {'label': 'Conjunto de álabes perimetrales', 'shape': 'tube', 'size': [6.0, 0.6, 6.0], 'position': [0, 0, 0], 'rotation': [90, 0, 0], 'param': 0.25, 'material': 'metal_brushed', 'color': '#2b3038'},
        ],
    },
    'jet_engine_nacelle': {
        'label': 'Góndola de reactor / carcasa exterior',
        'category': 'propulsion',
        'aliases': ['gondola', 'nacelle', 'carcasa_reactor', 'cubierta_motor', 'cowling', 'conducto_admision'],
        'default_material': 'paint',
        'default_color': '#f0f2f5',
        'size': [6.4, 8.0, 6.4],
        'parts': [
            {'label': 'Carcasa aerodinámica', 'shape': 'tube', 'size': [6.4, 8.0, 6.4], 'position': [0, 0, 0], 'rotation': [90, 0, 0], 'param': 0.08, 'material': 'paint', 'color': '#f0f2f5'},
            {'label': 'Labio de entrada pulido', 'shape': 'torus', 'size': [6.4, 6.4, 0.6], 'position': [0, 0, 4.0], 'material': 'metal_polished', 'color': '#d4d8e0'},
        ],
    },
    'turbine_nozzle_guide': {
        'label': 'Corona de álabes directores de tobera',
        'category': 'propulsion',
        'aliases': ['tobera_guia', 'nozzle_guide_vane', 'estator_turbina', 'corona_directriz', 'ngv'],
        'default_material': 'metal_anodized',
        'default_color': '#2b3038',
        'size': [5.2, 0.5, 5.2],
        'parts': [
            {'label': 'Aro exterior de retención', 'shape': 'tube', 'size': [5.2, 0.5, 5.2], 'position': [0, 0, 0], 'rotation': [90, 0, 0], 'param': 0.12, 'material': 'metal_anodized', 'color': '#3f444d'},
            {'label': 'Aro interior de soporte', 'shape': 'cylinder', 'size': [2.0, 0.5, 2.0], 'position': [0, 0, 0], 'rotation': [90, 0, 0], 'material': 'metal_anodized', 'color': '#262930'},
        ],
    },
    'bevel_gear_pair': {
        'label': 'Par de engranajes cónicos a 90 grados',
        'category': 'motion',
        'aliases': ['engranaje_conico', 'bevel_gear', 'par_conico', 'pinon_conico', 'engranajes_angulares'],
        'default_material': 'metal_brushed',
        'default_color': '#8a929e',
        'size': [3.8, 2.0, 2.8],
        'parts': [
            {'label': 'Piñón cónico conductor', 'shape': 'cone', 'size': [1.8, 1.2, 1.8], 'position': [0, -0.6, 0], 'material': 'metal_brushed', 'color': '#8a929e'},
            {'label': 'Corona cónica conducida', 'shape': 'cone', 'size': [2.8, 1.4, 2.8], 'position': [1.0, 0, 0], 'rotation': [0, 0, -90], 'material': 'metal_brushed', 'color': '#9aa2ae'},
        ],
    },
    'worm_drive_gearbox': {
        'label': 'Mecanismo sinfín-corona reductor',
        'category': 'motion',
        'aliases': ['tornillo_sinfin', 'worm_drive', 'sinfin_corona', 'reductor_sinfin', 'worm_gear'],
        'default_material': 'metal_polished',
        'default_color': '#c8cdd6',
        'size': [2.6, 4.0, 2.6],
        'parts': [
            {'label': 'Árbol sinfín helicoidal', 'shape': 'threaded_rod', 'size': [0.9, 4.0, 0.9], 'position': [0, 1.1, 0], 'rotation': [0, 0, 90], 'material': 'metal_polished', 'color': '#c8cdd6'},
            {'label': 'Rueda dentada de bronce', 'shape': 'gear', 'size': [2.6, 0.7, 2.6], 'position': [0, 0, 0], 'rotation': [90, 0, 0], 'param': 0.18, 'material': 'metal_polished', 'color': '#cda250'},
        ],
    },
    'camshaft_eccentric': {
        'label': 'Árbol de levas con lóbulos excéntricos',
        'category': 'motion',
        'aliases': ['arbol_de_levas', 'camshaft', 'leva', 'eje_levas', 'lobulo_leva'],
        'default_material': 'metal_polished',
        'default_color': '#b4bac4',
        'size': [1.6, 5.0, 1.6],
        'parts': [
            {'label': 'Eje principal cilíndrico', 'shape': 'cylinder', 'size': [0.7, 5.0, 0.7], 'position': [0, 0, 0], 'rotation': [90, 0, 0], 'material': 'metal_polished', 'color': '#b4bac4'},
            {'label': 'Lóbulo de leva 1', 'shape': 'wedge', 'size': [0.8, 1.2, 0.5], 'position': [0, 0.5, -1.2], 'material': 'metal_brushed', 'color': '#68707c'},
            {'label': 'Lóbulo de leva 2', 'shape': 'wedge', 'size': [0.8, 1.2, 0.5], 'position': [0.5, 0, 1.2], 'rotation': [0, 0, -90], 'material': 'metal_brushed', 'color': '#68707c'},
        ],
    },
    'pillow_block_bearing': {
        'label': 'Soporte con rodamiento autoalineable de chumacera',
        'category': 'motion',
        'aliases': ['chumacera', 'pillow_block', 'soporte_rodamiento', 'caja_rodamiento', 'bearing_unit'],
        'default_material': 'metal_brushed',
        'default_color': '#454f5d',
        'size': [3.6, 2.4, 1.4],
        'parts': [
            {'label': 'Base de fundición con orificios', 'shape': 'box', 'size': [3.6, 0.6, 1.4], 'position': [0, -0.9, 0], 'material': 'metal_brushed', 'color': '#454f5d'},
            {'label': 'Carcasa anular', 'shape': 'tube', 'size': [2.4, 1.0, 2.4], 'position': [0, 0.3, 0], 'rotation': [90, 0, 0], 'param': 0.2, 'material': 'metal_brushed', 'color': '#454f5d'},
            {'label': 'Pista y rodamiento interior', 'shape': 'cylinder', 'size': [1.4, 1.2, 1.4], 'position': [0, 0.3, 0], 'rotation': [90, 0, 0], 'material': 'metal_polished', 'color': '#d4dae2'},
        ],
    },
    'connecting_rod_piston': {
        'label': 'Conjunto pistón motor con biela articulada',
        'category': 'motion',
        'aliases': ['piston', 'biela', 'biela_piston', 'connecting_rod', 'piston_assembly', 'embolo'],
        'default_material': 'metal_brushed',
        'default_color': '#a8b0bc',
        'size': [2.4, 5.6, 2.4],
        'parts': [
            {'label': 'Cabeza del pistón cilíndrica', 'shape': 'chamfer_cylinder', 'size': [2.4, 2.0, 2.4], 'position': [0, 2.2, 0], 'material': 'metal_brushed', 'color': '#a8b0bc'},
            {'label': 'Cuerpo de la biela en doble T', 'shape': 'i_beam', 'size': [0.6, 3.2, 0.8], 'position': [0, -0.4, 0], 'material': 'metal_brushed', 'color': '#525a66'},
            {'label': 'Cabeza de biela inferior', 'shape': 'tube', 'size': [1.4, 0.8, 1.4], 'position': [0, -2.1, 0], 'rotation': [90, 0, 0], 'param': 0.25, 'material': 'metal_polished', 'color': '#88909c'},
        ],
    },
    'universal_joint_coupler': {
        'label': 'Junta universal cardán para acoplamiento angular',
        'category': 'motion',
        'aliases': ['cardan', 'junta_cardan', 'universal_joint', 'u_joint', 'acoplamiento_articulado'],
        'default_material': 'metal_brushed',
        'default_color': '#7a828e',
        'size': [1.4, 4.0, 1.4],
        'parts': [
            {'label': 'Horquilla conductora', 'shape': 'u_channel', 'size': [1.4, 1.8, 1.4], 'position': [0, 1.1, 0], 'material': 'metal_brushed', 'color': '#7a828e'},
            {'label': 'Cruceta central de unión', 'shape': 'cylinder', 'size': [0.5, 1.5, 0.5], 'position': [0, 0, 0], 'material': 'metal_polished', 'color': '#c2c8d2'},
            {'label': 'Horquilla conducida', 'shape': 'u_channel', 'size': [1.4, 1.8, 1.4], 'position': [0, -1.1, 0], 'rotation': [0, 90, 180], 'material': 'metal_brushed', 'color': '#7a828e'},
        ],
    },
    'ball_valve_assembly': {
        'label': 'Válvula de bola flotante con maneta de accionamiento',
        'category': 'fluid',
        'aliases': ['valvula_bola', 'ball_valve', 'llave_paso', 'valvula_esfera', 'valvula_corte'],
        'default_material': 'metal_brushed',
        'default_color': '#98a0ac',
        'size': [2.2, 3.4, 3.4],
        'parts': [
            {'label': 'Cuerpo esférico central', 'shape': 'ellipsoid', 'size': [2.2, 2.2, 2.2], 'position': [0, 0, 0], 'material': 'metal_brushed', 'color': '#98a0ac'},
            {'label': 'Cuello de paso con bridas', 'shape': 'cylinder', 'size': [1.5, 3.4, 1.5], 'position': [0, 0, 0], 'rotation': [0, 0, 90], 'material': 'metal_brushed', 'color': '#98a0ac'},
            {'label': 'Palanca de mando', 'shape': 'box', 'size': [0.3, 0.2, 2.8], 'position': [0, 1.6, 1.1], 'material': 'plastic', 'color': '#d43830'},
        ],
    },
    'pipe_tee_junction': {
        'label': 'Colector en T para derivación de tuberías',
        'category': 'fluid',
        'aliases': ['tubo_en_t', 'pipe_tee', 'te_derivacion', 'union_en_t', 'tee_fitting'],
        'default_material': 'metal_brushed',
        'default_color': '#6c7480',
        'size': [4.2, 2.4, 2.4],
        'parts': [
            {'label': 'Conducto principal continuo', 'shape': 'tube', 'size': [1.6, 4.2, 1.6], 'position': [0, 0, 0], 'rotation': [0, 0, 90], 'param': 0.12, 'material': 'metal_brushed', 'color': '#6c7480'},
            {'label': 'Ramal perpendicular de derivación', 'shape': 'tube', 'size': [1.6, 2.0, 1.6], 'position': [0, 1.0, 0], 'param': 0.12, 'material': 'metal_brushed', 'color': '#6c7480'},
            {'label': 'Brida terminal de acople', 'shape': 'flange', 'size': [2.4, 0.3, 2.4], 'position': [0, 2.0, 0], 'material': 'metal_brushed', 'color': '#555d68'},
        ],
    },
    'hydraulic_distributor_spool': {
        'label': 'Bloque distribuidor hidráulico con corredera',
        'category': 'fluid',
        'aliases': ['distribuidor_hidraulico', 'hydraulic_manifold', 'bloque_valvulas', 'spool_valve'],
        'default_material': 'metal_anodized',
        'default_color': '#323842',
        'size': [4.0, 2.8, 2.2],
        'parts': [
            {'label': 'Bloque macizo mecanizado', 'shape': 'box', 'size': [4.0, 2.6, 2.2], 'position': [0, 0, 0], 'material': 'metal_anodized', 'color': '#323842'},
            {'label': 'Puertos de conexión roscados', 'shape': 'flange', 'size': [1.0, 0.4, 1.0], 'position': [-1.2, 1.4, 0], 'material': 'metal_polished', 'color': '#a0a8b4'},
            {'label': 'Palanca accionadora', 'shape': 'cylinder', 'size': [0.3, 2.0, 0.3], 'position': [1.6, 1.8, 0], 'rotation': [15, 0, 0], 'material': 'metal_polished', 'color': '#c8ced6'},
        ],
    },
    'centrifugal_pump_volute': {
        'label': 'Carcasa de voluta para bomba centrífuga',
        'category': 'fluid',
        'aliases': ['bomba_centrifuga', 'voluta', 'centrifugal_pump', 'cuerpo_bomba', 'carcasa_bomba'],
        'default_material': 'metal_brushed',
        'default_color': '#2f527a',
        'size': [4.2, 3.8, 4.2],
        'parts': [
            {'label': 'Cámara de espiral / voluta', 'shape': 'tube', 'size': [4.2, 1.6, 4.2], 'position': [0, 0, 0], 'rotation': [90, 0, 0], 'param': 0.15, 'material': 'metal_brushed', 'color': '#2f527a'},
            {'label': 'Boquilla de impulsión vertical', 'shape': 'rect_tube', 'size': [1.4, 2.2, 1.4], 'position': [1.8, 1.6, 0], 'material': 'metal_brushed', 'color': '#2f527a'},
            {'label': 'Brida frontal de aspiración', 'shape': 'flange', 'size': [2.2, 0.4, 2.2], 'position': [0, 0, 1.0], 'rotation': [90, 0, 0], 'material': 'metal_polished', 'color': '#a4acb8'},
        ],
    },
    'robotic_gripper_claw': {
        'label': 'Pinza / garra robótica articulada de dos dedos',
        'category': 'electro-mechanical',
        'aliases': ['pinza_robotica', 'gripper', 'garra_robot', 'robotic_claw', 'manipulador'],
        'default_material': 'metal_anodized',
        'default_color': '#1e222a',
        'size': [2.2, 3.7, 1.6],
        'parts': [
            {'label': 'Base del actuador de la pinza', 'shape': 'box', 'size': [2.0, 1.5, 1.6], 'position': [0, -1.0, 0], 'material': 'metal_anodized', 'color': '#1e222a'},
            {'label': 'Dedo izquierdo articulado', 'shape': 'wedge', 'size': [0.4, 2.2, 0.8], 'position': [-0.7, 0.8, 0], 'rotation': [0, 0, 10], 'material': 'metal_brushed', 'color': '#d0d6de'},
            {'label': 'Dedo derecho articulado', 'shape': 'wedge', 'size': [0.4, 2.2, 0.8], 'position': [0.7, 0.8, 0], 'rotation': [0, 0, -10], 'material': 'metal_brushed', 'color': '#d0d6de'},
        ],
    },
    'gimbal_bracket_mount': {
        'label': 'Soporte horquilla basculante de 2 ejes tipo cardán',
        'category': 'structural',
        'aliases': ['gimbal', 'soporte_cardan', 'horquilla_giro', 'pan_tilt_mount', 'estabilizador'],
        'default_material': 'metal_anodized',
        'default_color': '#282e38',
        'size': [3.4, 2.4, 1.6],
        'parts': [
            {'label': 'Horquilla exterior envolvente', 'shape': 'u_channel', 'size': [3.2, 2.4, 1.2], 'position': [0, 0, 0], 'material': 'metal_anodized', 'color': '#282e38'},
            {'label': 'Plataforma interior de montaje', 'shape': 'box', 'size': [2.0, 0.3, 1.6], 'position': [0, 0, 0], 'material': 'metal_brushed', 'color': '#7c8490'},
            {'label': 'Pivotes coaxiales de rotación', 'shape': 'cylinder', 'size': [0.5, 3.4, 0.5], 'position': [0, 0, 0], 'rotation': [0, 0, 90], 'material': 'metal_polished', 'color': '#d8dde6'},
        ],
    },
    'lead_screw_linear_stage': {
        'label': 'Guía lineal con husillo de rosca y carro deslizante',
        'category': 'motion',
        'aliases': ['guia_lineal', 'lead_screw', 'husillo_lineal', 'linear_stage', 'carro_deslizante'],
        'default_material': 'metal_polished',
        'default_color': '#ccd2dc',
        'size': [6.0, 1.6, 1.8],
        'parts': [
            {'label': 'Husillo roscado principal', 'shape': 'threaded_rod', 'size': [0.6, 6.0, 0.6], 'position': [0, 0, 0], 'rotation': [0, 0, 90], 'material': 'metal_polished', 'color': '#ccd2dc'},
            {'label': 'Carro de desplazamiento ranurado', 'shape': 'box', 'size': [1.6, 1.4, 1.8], 'position': [0, 0, 0], 'material': 'metal_anodized', 'color': '#1a202c'},
            {'label': 'Soporte extremo fijo', 'shape': 'l_bracket', 'size': [0.8, 1.6, 1.8], 'position': [-2.8, 0, 0], 'material': 'metal_brushed', 'color': '#4a5260'},
        ],
    },
    'pcb_electronic_board': {
        'label': 'Placa de circuito impreso con microcontrolador y pines',
        'category': 'electrical',
        'aliases': ['placa_electronica', 'pcb', 'tarjeta_circuito', 'placa_base', 'circuit_board'],
        'default_material': 'plastic',
        'default_color': '#186338',
        'size': [4.8, 0.8, 3.6],
        'parts': [
            {'label': 'Sustrato de fibra verde', 'shape': 'box', 'size': [4.8, 0.15, 3.6], 'position': [0, 0, 0], 'material': 'plastic', 'color': '#186338'},
            {'label': 'Microcontrolador encapsulado QFP', 'shape': 'box', 'size': [1.2, 0.2, 1.2], 'position': [-0.8, 0.15, -0.4], 'material': 'plastic', 'color': '#16181b'},
            {'label': 'Regleta de conectores de pines', 'shape': 'box', 'size': [0.4, 0.6, 2.6], 'position': [2.0, 0.35, 0], 'material': 'plastic', 'color': '#20242a'},
        ],
    },
    'toggle_switch_actuator': {
        'label': 'Interruptor de palanca basculante industrial',
        'category': 'electrical',
        'aliases': ['interruptor_palanca', 'toggle_switch', 'conmutador', 'palanca_mando', 'switch'],
        'default_material': 'metal_polished',
        'default_color': '#b4bcc8',
        'size': [1.6, 2.9, 1.2],
        'parts': [
            {'label': 'Cuerpo cúbico de baquelita', 'shape': 'box', 'size': [1.6, 1.4, 1.2], 'position': [0, -0.8, 0], 'material': 'plastic', 'color': '#1a1c20'},
            {'label': 'Cuello roscado con tuerca', 'shape': 'threaded_rod', 'size': [0.8, 0.6, 0.8], 'position': [0, 0.2, 0], 'material': 'metal_polished', 'color': '#b4bcc8'},
            {'label': 'Pomo cónico basculante', 'shape': 'cone', 'size': [0.5, 1.6, 0.5], 'position': [0, 1.1, 0.2], 'rotation': [20, 0, 0], 'material': 'metal_polished', 'color': '#dce2ec'},
        ],
    },
    'caster_wheel_swivel': {
        'label': 'Rueda orientable con horquilla y banda de rodadura',
        'category': 'hardware',
        'aliases': ['rueda_giratoria', 'caster_wheel', 'rueda_loca', 'rueda_pivote', 'swivel_wheel'],
        'default_material': 'metal_brushed',
        'default_color': '#687280',
        'size': [2.2, 2.7, 2.2],
        'parts': [
            {'label': 'Placa superior de anclaje', 'shape': 'box', 'size': [2.0, 0.2, 2.0], 'position': [0, 1.8, 0], 'material': 'metal_brushed', 'color': '#687280'},
            {'label': 'Horquilla estampada envolvente', 'shape': 'u_channel', 'size': [1.6, 1.6, 1.8], 'position': [0, 0.9, 0], 'rotation': [180, 0, 0], 'material': 'metal_brushed', 'color': '#687280'},
            {'label': 'Rueda de goma con llanta', 'shape': 'chamfer_cylinder', 'size': [2.2, 0.7, 2.2], 'position': [0, 0, 0], 'rotation': [0, 0, 90], 'material': 'rubber', 'color': '#202226'},
        ],
    },
    'radial_fin_heatsink': {
        'label': 'Disipador térmico cilíndrico de aletas radiales',
        'category': 'thermal',
        'aliases': ['disipador_radial', 'radial_heatsink', 'disipador_cilindrico', 'refrigerador_aletas'],
        'default_material': 'metal_anodized',
        'default_color': '#1e2229',
        'size': [3.6, 2.6, 3.6],
        'parts': [
            {'label': 'Núcleo central macizo', 'shape': 'cylinder', 'size': [1.6, 2.6, 1.6], 'position': [0, 0, 0], 'material': 'metal_anodized', 'color': '#1e2229'},
            {'label': 'Aletas radiales disipadoras', 'shape': 'heatsink', 'size': [3.6, 2.4, 3.6], 'position': [0, 0, 0], 'param': 0.12, 'material': 'metal_anodized', 'color': '#1e2229'},
        ],
    },
    'cable_gland_connector': {
        'label': 'Prensaestopas de estanqueidad para paso de cable',
        'category': 'hardware',
        'aliases': ['prensaestopas', 'cable_gland', 'racor_cable', 'pasacables_estanco', 'conector_prensa'],
        'default_material': 'plastic',
        'default_color': '#3a404a',
        'size': [1.6, 2.4, 1.6],
        'parts': [
            {'label': 'Cuerpo hexagonal con rosca', 'shape': 'hexprism', 'size': [1.6, 1.2, 1.6], 'position': [0, 0, 0], 'material': 'plastic', 'color': '#3a404a'},
            {'label': 'Tuerca cónica de apriete', 'shape': 'cone', 'size': [1.4, 0.8, 1.4], 'position': [0, 0.9, 0], 'material': 'plastic', 'color': '#2b3038'},
            {'label': 'Manguito de goma pasacable', 'shape': 'tube', 'size': [0.7, 2.4, 0.7], 'position': [0, 0.4, 0], 'param': 0.2, 'material': 'rubber', 'color': '#181a1d'},
        ],
    },

}


def _tokens(text: str) -> List[str]:
    """Lowercase word tokens, splitting on spaces, underscores and punctuation."""
    import re
    return [t for t in re.split(r'[^0-9a-záéíóúñü]+', (text or '').lower()) if t]


class ShapeRegistry:
    """Manages built-in technical components and dynamically learned shapes.

    Enables reusing shapes without re-generating geometry, adjusting them at will
    (scale, position, rotation, color, material, parameters), and seamlessly
    integrating them into SpatialPresentationPlan scene models.
    """

    def __init__(self, persistence_path: Optional[Union[str, Path]] = None):
        self.persistence_path = Path(persistence_path) if persistence_path else None
        self._static = copy.deepcopy(TECHNICAL_COMPONENTS)
        self._dynamic: Dict[str, Dict[str, Any]] = {}
        if self.persistence_path and self.persistence_path.is_file():
            self._load_dynamic()

    def _load_dynamic(self) -> None:
        try:
            with open(self.persistence_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self._dynamic = data
        except Exception:
            self._dynamic = {}

    def _save_dynamic(self) -> None:
        if not self.persistence_path:
            return
        try:
            self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.persistence_path, 'w', encoding='utf-8') as f:
                json.dump(self._dynamic, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    @property
    def catalog(self) -> Dict[str, Dict[str, Any]]:
        with LOCK:
            return {**self._static, **self._dynamic}

    def list_components(self) -> List[Dict[str, Any]]:
        with LOCK:
            cat = self.catalog
            return [{'id': cid, 'label': c['label'], 'category': c.get('category', 'general'),
                     'parts_count': len(c.get('parts', [])), 'size': c.get('size')}
                    for cid, c in cat.items()]

    def has_shape(self, shape_id: str) -> bool:
        with LOCK:
            return shape_id in self.catalog

    def get_shape(self, shape_id: str) -> Optional[Dict[str, Any]]:
        with LOCK:
            shape = self.catalog.get(shape_id)
            return copy.deepcopy(shape) if shape else None

    def match_shape(self, query: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Finds a matching component from query text using label, ID or aliases."""
        clean = (query or '').strip().lower()
        if not clean:
            return None
        with LOCK:
            # 1. Exact ID
            if clean in self.catalog:
                return clean, copy.deepcopy(self.catalog[clean])
            # 2. Match in aliases or labels
            for cid, c in self.catalog.items():
                if clean == c['label'].lower():
                    return cid, copy.deepcopy(c)
                if clean in [a.lower() for a in c.get('aliases', [])]:
                    return cid, copy.deepcopy(c)
            # 3. Whole-word match: every token of an alias must appear as a word in the query,
            # so 'asa' never matches inside 'carcasa'.
            words = set(_tokens(clean))
            for cid, c in self.catalog.items():
                for a in c.get('aliases', []):
                    alias_tokens = _tokens(a)
                    if alias_tokens and set(alias_tokens) <= words:
                        return cid, copy.deepcopy(c)
        return None

    def register_dynamic_shape(self, shape_id: str, definition: Dict[str, Any]) -> Dict[str, Any]:
        """Registers a newly learned or modeled shape for future reuse."""
        if not isinstance(shape_id, str) or not shape_id.strip():
            raise ValueError('shape_id must be a non-empty string')
        if not isinstance(definition, dict) or 'parts' not in definition:
            raise ValueError("definition must contain at least a 'parts' list")
        shape_id = shape_id.strip().lower()
        clean_def = {
            'label': definition.get('label', shape_id),
            'category': definition.get('category', 'custom'),
            'aliases': definition.get('aliases', [shape_id]),
            'default_material': definition.get('default_material', 'metal_brushed'),
            'default_color': definition.get('default_color', '#8a929c'),
            'size': definition.get('size', [1.0, 1.0, 1.0]),
            'parts': copy.deepcopy(definition['parts']),
            'ports': copy.deepcopy(definition.get('ports', {'center': [0, 0, 0]})),
        }
        with LOCK:
            self._dynamic[shape_id] = clean_def
            self._save_dynamic()
        return clean_def

    def instantiate(self,
                    shape_id: str,
                    *,
                    scale: Union[float, List[float], Tuple[float, float, float]] = 1.0,
                    position: Union[List[float], Tuple[float, float, float]] = (0.0, 0.0, 0.0),
                    rotation: Optional[Union[List[float], Tuple[float, float, float]]] = None,
                    color: Optional[str] = None,
                    material: Optional[str] = None,
                    explode_offset: Optional[Union[List[float], Tuple[float, float, float]]] = None,
                    id_prefix: str = 'p') -> List[Dict[str, Any]]:
        """Instantiates a technical component into a list of concrete scene objects.

        Allows adjusting size, position, orientation, colors and materials at will.
        """
        shape = self.get_shape(shape_id)
        if not shape:
            raise ValueError(f"Shape '{shape_id}' not found in registry.")

        if isinstance(scale, (int, float)):
            sx = sy = sz = float(scale)
        else:
            sx, sy, sz = float(scale[0]), float(scale[1]), float(scale[2])

        px, py, pz = float(position[0]), float(position[1]), float(position[2])
        ex, ey, ez = (float(explode_offset[0]), float(explode_offset[1]), float(explode_offset[2])) if explode_offset else (0.0, 1.5, 0.0)

        out_objects = []
        for idx, part in enumerate(shape['parts'], 1):
            psize = part.get('size', [1.0, 1.0, 1.0])
            scaled_size = [
                max(0.02, round(psize[0] * sx, 4)),
                max(0.02, round(psize[1] * sy, 4)),
                max(0.02, round(psize[2] * sz, 4)),
            ]
            ppos = part.get('position', [0.0, 0.0, 0.0])
            transformed_pos = [
                round(px + ppos[0] * sx, 4),
                round(py + ppos[1] * sy, 4),
                round(pz + ppos[2] * sz, 4),
            ]
            rot = copy.copy(part.get('rotation', [0.0, 0.0, 0.0]))
            if rotation:
                rot = [round(rot[i] + rotation[i], 2) for i in range(3)]

            item: Dict[str, Any] = {
                'id': f"{id_prefix}_{idx}",
                'label': part.get('label', shape['label']),
                'shape': part['shape'],
                'size': scaled_size,
                'position': transformed_pos,
                'color': color or part.get('color', shape.get('default_color', '#8a929c')),
                'material': material or part.get('material', shape.get('default_material', 'metal_brushed')),
                'explode': [round(ex, 3), round(ey, 3), round(ez, 3)],
            }
            if any(r != 0 for r in rot):
                item['rotation'] = rot
            if 'param' in part:
                item['param'] = part['param']

            out_objects.append(item)

        return out_objects

    def analyze_and_integrate(self,
                              observed_components: List[Union[str, Dict[str, Any]]],
                              *,
                              auto_register_missing: bool = True) -> Dict[str, Any]:
        """Analyzes required components for an observed technical object.

        Identifies which components match stored shapes in the registry, integrates
        them into concrete scene pieces, and automatically saves any newly created
        shapes into the persistent registry to avoid recomputation in subsequent runs.
        """
        integrated_parts = []
        matched_count = 0
        registered_count = 0

        for i, item in enumerate(observed_components, 1):
            if isinstance(item, str):
                name = item
                spec: Dict[str, Any] = {}
            elif isinstance(item, dict):
                name = item.get('label') or item.get('name') or f'part_{i}'
                spec = item
            else:
                continue

            match = self.match_shape(name)
            if match:
                cid, comp = match
                matched_count += 1
                inst = self.instantiate(
                    cid,
                    scale=spec.get('scale', 1.0),
                    position=spec.get('position', [0, 0, 0]),
                    rotation=spec.get('rotation'),
                    color=spec.get('color'),
                    material=spec.get('material'),
                    id_prefix=f'm{matched_count}'
                )
                integrated_parts.extend(inst)
            else:
                # Shape not found in registry -> create new shape and save it
                shape_kind = spec.get('shape', 'box')
                size = spec.get('size', [1.0, 1.0, 1.0])
                pos = spec.get('position', [0, 0, 0])
                color = spec.get('color', '#8a929c')
                mat = spec.get('material', 'metal_brushed')

                new_part_def = {
                    'label': name,
                    'category': spec.get('category', 'custom'),
                    'aliases': [name.lower()],
                    'default_material': mat,
                    'default_color': color,
                    'size': size,
                    'parts': [{'label': name, 'shape': shape_kind, 'size': size, 'position': [0, 0, 0], 'color': color, 'material': mat}],
                }
                if 'param' in spec:
                    new_part_def['parts'][0]['param'] = spec['param']

                if auto_register_missing:
                    new_cid = f"dynamic_{name.lower().replace(' ', '_')[:32]}"
                    self.register_dynamic_shape(new_cid, new_part_def)
                    registered_count += 1

                integrated_parts.append({
                    'id': f'o{len(integrated_parts) + 1}',
                    'label': name,
                    'shape': shape_kind,
                    'size': size,
                    'position': pos,
                    'color': color,
                    'material': mat,
                    'explode': spec.get('explode', [0, 1.5, 0]),
                })

        return {
            'total_pieces': len(integrated_parts),
            'reused_from_catalog': matched_count,
            'newly_registered': registered_count,
            'objects': integrated_parts,
        }


def catalog_text(registry: Optional[ShapeRegistry] = None, limit: int = 60) -> str:
    """Compact catalog line for the model contract: component ids the model may reference."""
    reg = registry or ShapeRegistry()
    items = sorted(reg.list_components(), key=lambda c: c['id'])[:limit]
    return '; '.join(f"{c['id']} ({c['label']}, {c['parts_count']} piezas)" for c in items)


def expand_component_refs(objects: List[Dict[str, Any]], registry: ShapeRegistry,
                          *, max_objects: int = 32) -> List[Dict[str, Any]]:
    """Replaces scene objects of the form {'component': id, ...} with their concrete parts.

    Plain objects pass through unchanged. Expanded parts receive fresh sequential ids
    (o1, o2, ...) and keep the reference label as a prefix, so focus/arrows written by
    the model against the reference id must be remapped by the caller via the returned
    'axx_component' marker. Unknown components and budget overflow raise ValueError.
    """
    out: List[Dict[str, Any]] = []
    for obj in objects:
        if not isinstance(obj, dict) or 'component' not in obj:
            out.append(obj)
            continue
        cid = obj['component']
        if not registry.has_shape(cid):
            raise ValueError(f'Componente desconocido: {cid}')
        parts = registry.instantiate(cid, scale=obj.get('scale', 1.0), position=obj.get('position', (0, 0, 0)),
                                     rotation=obj.get('rotation'), color=obj.get('color'),
                                     material=obj.get('material'), explode_offset=obj.get('explode'))
        for part in parts:
            part['label'] = f"{obj.get('label', cid)} · {part['label']}"[:80]
            part['axx_component'] = obj.get('id', cid)
            out.append(part)
    if len(out) > max_objects:
        raise ValueError(f'La escena expandida supera {max_objects} piezas.')
    used = {o['id'] for o in out if 'axx_component' not in o and isinstance(o.get('id'), str)}
    n = 1
    for o in out:
        if 'axx_component' in o:
            while f'o{n}' in used:
                n += 1
            o['id'] = f'o{n}'
            used.add(o['id'])
    return out
