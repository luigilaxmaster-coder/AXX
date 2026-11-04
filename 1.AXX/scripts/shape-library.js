// Generated from backend/shape_registry.py TECHNICAL_COMPONENTS; edit the Python catalog and regenerate.
export const TECHNICAL_COMPONENTS = {
 "hex_bolt": {
  "label": "Tornillo de cabeza hexagonal",
  "category": "fastener",
  "parts": [
   {
    "label": "Cabeza hexagonal",
    "shape": "hexprism",
    "size": [
     0.7,
     0.35,
     0.7
    ],
    "position": [
     0,
     0.7,
     0
    ],
    "material": "metal_polished",
    "color": "#cfd4da"
   },
   {
    "label": "Espiga roscada",
    "shape": "cylinder",
    "size": [
     0.38,
     1.4,
     0.38
    ],
    "position": [
     0,
     -0.175,
     0
    ],
    "material": "metal_brushed",
    "color": "#a8b0b8"
   }
  ]
 },
 "hex_nut": {
  "label": "Tuerca hexagonal métrica",
  "category": "fastener",
  "parts": [
   {
    "label": "Cuerpo hexagonal roscado",
    "shape": "hexprism",
    "size": [
     0.75,
     0.36,
     0.75
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_polished",
    "color": "#cfd4da",
    "param": 0.2
   }
  ]
 },
 "washer": {
  "label": "Arandela plana métrica",
  "category": "fastener",
  "parts": [
   {
    "label": "Anillo plano",
    "shape": "tube",
    "size": [
     0.85,
     0.08,
     0.85
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_brushed",
    "color": "#b4bcc4",
    "param": 0.45
   }
  ]
 },
 "spur_gear": {
  "label": "Engranaje recto con cubo y chavetero",
  "category": "motion",
  "parts": [
   {
    "label": "Corona dentada exterior",
    "shape": "gear",
    "size": [
     2.2,
     0.4,
     2.2
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_anodized",
    "color": "#c68630",
    "param": 16
   },
   {
    "label": "Cubo de acoplamiento central",
    "shape": "cylinder",
    "size": [
     0.65,
     0.5,
     0.65
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_brushed",
    "color": "#9aa0a6"
   }
  ]
 },
 "ball_bearing": {
  "label": "Rodamiento rígido de bolas",
  "category": "motion",
  "parts": [
   {
    "label": "Pista exterior",
    "shape": "tube",
    "size": [
     2.2,
     0.5,
     2.2
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_polished",
    "color": "#c5cdd6",
    "param": 0.16
   },
   {
    "label": "Pista interior",
    "shape": "tube",
    "size": [
     1.2,
     0.52,
     1.2
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_polished",
    "color": "#b0b8c2",
    "param": 0.22
   },
   {
    "label": "Jaula con bolas",
    "shape": "torus",
    "size": [
     1.7,
     0.26,
     1.7
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_brushed",
    "color": "#dca638"
   }
  ]
 },
 "keyed_shaft": {
  "label": "Eje cilíndrico de transmisión con chaveta",
  "category": "motion",
  "parts": [
   {
    "label": "Eje rectificado",
    "shape": "cylinder",
    "size": [
     0.6,
     3.2,
     0.6
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_polished",
    "color": "#c2cacf"
   },
   {
    "label": "Chaveta longitudinal",
    "shape": "box",
    "size": [
     0.12,
     0.8,
     0.14
    ],
    "position": [
     0.26,
     0.4,
     0
    ],
    "material": "metal_brushed",
    "color": "#828c96"
   }
  ]
 },
 "v_pulley": {
  "label": "Polea acanalada para correa trapezoidal",
  "category": "motion",
  "parts": [
   {
    "label": "Disco con llanta exterior",
    "shape": "cylinder",
    "size": [
     2.4,
     0.45,
     2.4
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_anodized",
    "color": "#364050"
   },
   {
    "label": "Garganta en V",
    "shape": "frustum",
    "size": [
     2.4,
     0.2,
     2.4
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_polished",
    "color": "#242c38",
    "param": 0.72
   },
   {
    "label": "Cubo de amarre al eje",
    "shape": "cylinder",
    "size": [
     0.72,
     0.6,
     0.72
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_brushed",
    "color": "#505b6c"
   }
  ]
 },
 "coil_spring": {
  "label": "Muelle / resorte helicoidal de compresión",
  "category": "motion",
  "parts": [
   {
    "label": "Hélice helicoidal de acero",
    "shape": "coil",
    "size": [
     0.85,
     2.2,
     0.85
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_polished",
    "color": "#4287f5",
    "param": 5.0
   }
  ]
 },
 "l_bracket": {
  "label": "Escuadra de montaje angular en L",
  "category": "structural",
  "parts": [
   {
    "label": "Perfil angular doblado",
    "shape": "l_bracket",
    "size": [
     1.4,
     1.4,
     0.8
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_brushed",
    "color": "#969fa8",
    "param": 0.18
   }
  ]
 },
 "u_channel_bar": {
  "label": "Perfil estructural en U / Canal de acero",
  "category": "structural",
  "parts": [
   {
    "label": "Viga con perfil en U",
    "shape": "u_channel",
    "size": [
     1.0,
     3.0,
     0.8
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_brushed",
    "color": "#868e98",
    "param": 0.14
   }
  ]
 },
 "i_beam_girder": {
  "label": "Viga estructural en doble T / Perfil en I",
  "category": "structural",
  "parts": [
   {
    "label": "Viga laminada en I",
    "shape": "i_beam",
    "size": [
     1.2,
     3.2,
     1.2
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_anodized",
    "color": "#4e5b6c",
    "param": 0.12
   }
  ]
 },
 "pipe_elbow_flanged": {
  "label": "Codo de tubería a 90 grados con bridas",
  "category": "fluid",
  "parts": [
   {
    "label": "Curva toroidal a 90°",
    "shape": "pipe_elbow",
    "size": [
     1.2,
     1.2,
     0.5
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_polished",
    "color": "#447856",
    "param": 0.22
   },
   {
    "label": "Brida de entrada",
    "shape": "flange",
    "size": [
     0.9,
     0.1,
     0.9
    ],
    "position": [
     -0.6,
     0,
     0
    ],
    "rotation": [
     0,
     0,
     90
    ],
    "material": "metal_brushed",
    "color": "#366245"
   },
   {
    "label": "Brida de salida",
    "shape": "flange",
    "size": [
     0.9,
     0.1,
     0.9
    ],
    "position": [
     0,
     -0.6,
     0
    ],
    "material": "metal_brushed",
    "color": "#366245"
   }
  ]
 },
 "flange_coupling": {
  "label": "Brida de acoplamiento circular con tornillería",
  "category": "fluid",
  "parts": [
   {
    "label": "Plato circular con orificios",
    "shape": "flange",
    "size": [
     1.8,
     0.22,
     1.8
    ],
    "position": [
     0,
     -0.22,
     0
    ],
    "material": "metal_polished",
    "color": "#929ca7",
    "param": 6
   },
   {
    "label": "Cuello de unión",
    "shape": "tube",
    "size": [
     0.85,
     0.55,
     0.85
    ],
    "position": [
     0,
     0.15,
     0
    ],
    "material": "metal_brushed",
    "color": "#78828d",
    "param": 0.2
   }
  ]
 },
 "heatsink_extrusion": {
  "label": "Disipador térmico con aletas paralelas",
  "category": "thermal",
  "parts": [
   {
    "label": "Aletas de disipación y base térmica",
    "shape": "heatsink",
    "size": [
     2.0,
     1.2,
     2.4
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_anodized",
    "color": "#282a2d",
    "param": 7
   }
  ]
 },
 "butterfly_valve": {
  "label": "Válvula de control tipo mariposa",
  "category": "fluid",
  "parts": [
   {
    "label": "Cuerpo tubular de la válvula",
    "shape": "tube",
    "size": [
     1.6,
     0.8,
     1.6
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_anodized",
    "color": "#1c5e93",
    "param": 0.16
   },
   {
    "label": "Disco obturador pivotante",
    "shape": "cylinder",
    "size": [
     1.28,
     0.08,
     1.28
    ],
    "position": [
     0,
     0,
     0
    ],
    "rotation": [
     0,
     25,
     0
    ],
    "material": "metal_polished",
    "color": "#f2ce54"
   },
   {
    "label": "Eje de mando",
    "shape": "cylinder",
    "size": [
     0.18,
     1.5,
     0.18
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_brushed",
    "color": "#969da4"
   }
  ]
 },
 "fan_impeller": {
  "label": "Rotor / rodete axial con álabes inclinados",
  "category": "motion",
  "parts": [
   {
    "label": "Núcleo central del rodete",
    "shape": "cylinder",
    "size": [
     0.8,
     0.5,
     0.8
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "plastic",
    "color": "#263442"
   },
   {
    "label": "Corona aerodinámica de álabes",
    "shape": "gear",
    "size": [
     2.6,
     0.35,
     2.6
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "plastic",
    "color": "#304254",
    "param": 8
   }
  ]
 },
 "hydraulic_actuator": {
  "label": "Cilindro hidráulico / Actuador lineal",
  "category": "motion",
  "parts": [
   {
    "label": "Camisa cilíndrica exterior",
    "shape": "cylinder",
    "size": [
     1.2,
     2.6,
     1.2
    ],
    "position": [
     0,
     -0.6,
     0
    ],
    "material": "metal_anodized",
    "color": "#16425b"
   },
   {
    "label": "Vástago cromado telescópico",
    "shape": "cylinder",
    "size": [
     0.55,
     2.2,
     0.55
    ],
    "position": [
     0,
     1.2,
     0
    ],
    "material": "metal_polished",
    "color": "#dde4eb"
   },
   {
    "label": "Rótula de amarre trasera",
    "shape": "torus",
    "size": [
     0.65,
     0.3,
     0.65
    ],
    "position": [
     0,
     -2.0,
     0
    ],
    "rotation": [
     90,
     0,
     0
    ],
    "material": "metal_brushed",
    "color": "#58a4b0"
   }
  ]
 },
 "shock_absorber": {
  "label": "Amortiguador con resorte telescópico coaxial",
  "category": "motion",
  "parts": [
   {
    "label": "Cuerpo hidráulico amortiguador",
    "shape": "cylinder",
    "size": [
     0.6,
     2.8,
     0.6
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_anodized",
    "color": "#cc0022"
   },
   {
    "label": "Muelle envolvente exterior",
    "shape": "coil",
    "size": [
     1.0,
     2.0,
     1.0
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_polished",
    "color": "#ea1c34",
    "param": 6.0
   },
   {
    "label": "Ojal superior",
    "shape": "capsule",
    "size": [
     0.45,
     0.45,
     0.45
    ],
    "position": [
     0,
     1.5,
     0
    ],
    "material": "metal_brushed",
    "color": "#282a36"
   },
   {
    "label": "Ojal inferior",
    "shape": "capsule",
    "size": [
     0.45,
     0.45,
     0.45
    ],
    "position": [
     0,
     -1.5,
     0
    ],
    "material": "metal_brushed",
    "color": "#282a36"
   }
  ]
 },
 "electronic_enclosure": {
  "label": "Caja estanca modular para electrónica",
  "category": "electrical",
  "parts": [
   {
    "label": "Cuerpo base con esquinas biseladas",
    "shape": "box",
    "size": [
     3.2,
     1.2,
     2.2
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "plastic",
    "color": "#36394e",
    "param": 0.12
   },
   {
    "label": "Tapa atornillada superior",
    "shape": "box",
    "size": [
     3.3,
     0.22,
     2.3
    ],
    "position": [
     0,
     0.68,
     0
    ],
    "material": "plastic",
    "color": "#d97258",
    "param": 0.08
   }
  ]
 },
 "stepper_motor_nema": {
  "label": "Cuerpo de motor paso a paso híbrido (NEMA)",
  "category": "electro-mechanical",
  "parts": [
   {
    "label": "Cuerpo prismático del estator",
    "shape": "box",
    "size": [
     2.0,
     2.2,
     2.0
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_anodized",
    "color": "#223e4a",
    "param": 0.1
   },
   {
    "label": "Corona frontal de centrado",
    "shape": "cylinder",
    "size": [
     1.1,
     0.2,
     1.1
    ],
    "position": [
     0,
     1.2,
     0
    ],
    "material": "metal_polished",
    "color": "#258c80"
   },
   {
    "label": "Eje rectificado de salida",
    "shape": "cylinder",
    "size": [
     0.28,
     1.0,
     0.28
    ],
    "position": [
     0,
     1.6,
     0
    ],
    "material": "metal_polished",
    "color": "#e2be64"
   }
  ]
 },
 "crimp_terminal": {
  "label": "Terminal eléctrico de horquilla para cable",
  "category": "electrical",
  "parts": [
   {
    "label": "Horquilla de contacto metálica",
    "shape": "u_channel",
    "size": [
     0.8,
     0.7,
     0.12
    ],
    "position": [
     0,
     0.45,
     0
    ],
    "material": "metal_polished",
    "color": "#e89855",
    "param": 0.26
   },
   {
    "label": "Manguito prensacables aislado",
    "shape": "tube",
    "size": [
     0.45,
     0.95,
     0.45
    ],
    "position": [
     0,
     -0.35,
     0
    ],
    "material": "rubber",
    "color": "#dc6446",
    "param": 0.18
   }
  ]
 },
 "hinge_assembly": {
  "label": "Bisagra articulada de dos alas con pasador",
  "category": "structural",
  "parts": [
   {
    "label": "Pasador central cilíndrico",
    "shape": "cylinder",
    "size": [
     0.22,
     1.8,
     0.22
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_polished",
    "color": "#a4adb6"
   },
   {
    "label": "Ala fija perforada",
    "shape": "box",
    "size": [
     0.8,
     1.6,
     0.08
    ],
    "position": [
     -0.44,
     0,
     0
    ],
    "material": "metal_brushed",
    "color": "#666f77"
   },
   {
    "label": "Ala móvil perforada",
    "shape": "box",
    "size": [
     0.8,
     1.6,
     0.08
    ],
    "position": [
     0.44,
     0,
     0
    ],
    "material": "metal_brushed",
    "color": "#666f77"
   }
  ]
 },
 "injector_nozzle": {
  "label": "Tobera / Boquilla de inyección cónica",
  "category": "fluid",
  "parts": [
   {
    "label": "Cuerpo hexagonal de roscado",
    "shape": "hexprism",
    "size": [
     1.0,
     0.6,
     1.0
    ],
    "position": [
     0,
     -0.55,
     0
    ],
    "material": "metal_polished",
    "color": "#cfa06f"
   },
   {
    "label": "Cono convergente de descarga",
    "shape": "frustum",
    "size": [
     0.9,
     1.15,
     0.9
    ],
    "position": [
     0,
     0.32,
     0
    ],
    "material": "metal_polished",
    "color": "#f4e7c7",
    "param": 0.26
   }
  ]
 },
 "potentiometer_knob": {
  "label": "Mando / perilla de potenciómetro con indicador",
  "category": "electrical",
  "parts": [
   {
    "label": "Cuerpo giratorio con chaflán",
    "shape": "chamfer_cylinder",
    "size": [
     1.4,
     0.9,
     1.4
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "plastic",
    "color": "#111827",
    "param": 0.1
   },
   {
    "label": "Puntero visual de posición",
    "shape": "wedge",
    "size": [
     0.14,
     0.55,
     0.22
    ],
    "position": [
     0,
     0.2,
     0.6
    ],
    "material": "emissive",
    "color": "#10b981"
   }
  ]
 },
 "threaded_stud": {
  "label": "Espárrago / varilla roscada con tuercas",
  "category": "fastener",
  "parts": [
   {
    "label": "Varilla roscada",
    "shape": "threaded_rod",
    "size": [
     0.4,
     3.0,
     0.4
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_brushed",
    "color": "#b8bec6",
    "param": 18
   },
   {
    "label": "Tuerca superior",
    "shape": "hexprism",
    "size": [
     0.75,
     0.32,
     0.75
    ],
    "position": [
     0,
     1.1,
     0
    ],
    "material": "metal_polished",
    "color": "#cfd4da"
   },
   {
    "label": "Tuerca inferior",
    "shape": "hexprism",
    "size": [
     0.75,
     0.32,
     0.75
    ],
    "position": [
     0,
     -1.1,
     0
    ],
    "material": "metal_polished",
    "color": "#cfd4da"
   }
  ]
 },
 "square_frame_tube": {
  "label": "Tubo estructural rectangular hueco",
  "category": "structural",
  "parts": [
   {
    "label": "Perfil hueco rectangular",
    "shape": "rect_tube",
    "size": [
     1.0,
     3.0,
     1.0
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_brushed",
    "color": "#7d8791",
    "param": 0.1
   }
  ]
 },
 "pull_handle": {
  "label": "Tirador / asa curva con bases",
  "category": "hardware",
  "parts": [
   {
    "label": "Asa curvada",
    "shape": "arc",
    "size": [
     2.0,
     2.0,
     0.4
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_polished",
    "color": "#d0d5db",
    "param": 180
   },
   {
    "label": "Base izquierda",
    "shape": "cylinder",
    "size": [
     0.32,
     0.18,
     0.32
    ],
    "position": [
     -0.84,
     -0.09,
     0
    ],
    "material": "metal_brushed",
    "color": "#9aa2ab"
   },
   {
    "label": "Base derecha",
    "shape": "cylinder",
    "size": [
     0.32,
     0.18,
     0.32
    ],
    "position": [
     0.84,
     -0.09,
     0
    ],
    "material": "metal_brushed",
    "color": "#9aa2ab"
   }
  ]
 },
 "knurled_knob": {
  "label": "Pomo moleteado de apriete manual",
  "category": "hardware",
  "parts": [
   {
    "label": "Cabeza moleteada",
    "shape": "knurled_cylinder",
    "size": [
     1.2,
     0.5,
     1.2
    ],
    "position": [
     0,
     0.55,
     0
    ],
    "material": "metal_polished",
    "color": "#c9ced4",
    "param": 28
   },
   {
    "label": "Espiga roscada",
    "shape": "threaded_rod",
    "size": [
     0.4,
     1.1,
     0.4
    ],
    "position": [
     0,
     -0.25,
     0
    ],
    "material": "metal_brushed",
    "color": "#a9b0b8",
    "param": 9
   }
  ]
 },
 "slotted_mount_plate": {
  "label": "Placa de montaje con ojales de ajuste",
  "category": "structural",
  "parts": [
   {
    "label": "Placa base",
    "shape": "box",
    "size": [
     3.0,
     0.2,
     1.6
    ],
    "position": [
     0,
     0,
     0
    ],
    "material": "metal_anodized",
    "color": "#3d4652",
    "param": 0.04
   },
   {
    "label": "Ojal de ajuste izquierdo",
    "shape": "slot",
    "size": [
     0.7,
     0.3,
     0.22
    ],
    "position": [
     -1.0,
     0.02,
     0
    ],
    "rotation": [
     90,
     0,
     0
    ],
    "material": "rubber",
    "color": "#15181c"
   },
   {
    "label": "Ojal de ajuste derecho",
    "shape": "slot",
    "size": [
     0.7,
     0.3,
     0.22
    ],
    "position": [
     1.0,
     0.02,
     0
    ],
    "rotation": [
     90,
     0,
     0
    ],
    "material": "rubber",
    "color": "#15181c"
   }
  ]
 }
};

export function instantiateComponent(cid, { scale = 1, position = [0, 0, 0], color = null, material = null, idPrefix = 'p' } = {}) {
  const comp = TECHNICAL_COMPONENTS[cid];
  if (!comp) return [];
  const s = Array.isArray(scale) ? scale : [scale, scale, scale];
  return comp.parts.map((p, i) => ({
    id: `${idPrefix}_${i + 1}`,
    label: p.label,
    shape: p.shape,
    size: [Math.max(0.02, p.size[0] * s[0]), Math.max(0.02, p.size[1] * s[1]), Math.max(0.02, p.size[2] * s[2])],
    position: [position[0] + p.position[0] * s[0], position[1] + p.position[1] * s[1], position[2] + p.position[2] * s[2]],
    color: color || p.color,
    material: material || p.material,
    ...(p.rotation ? { rotation: p.rotation } : {}),
    ...(p.param !== undefined ? { param: p.param } : {})
  }));
}
