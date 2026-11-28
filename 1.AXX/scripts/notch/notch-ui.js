/* AXX Precision Identity Notch Renderer & Settings Card (`Axx.notchUI`)
 * Apple-grade Spatial Obsidian & Liquid Glass presentation:
 * Media Panoramic, Agent Observatory, Spotlight Intent Launcher, Portal Smart Shelf,
 * Voice Resonance Studio, Parallel Lanes, SVG Ring Resource Lens, Recall Threads,
 * Auto-Fade Idle Wake, and Unified Settings.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  }
  const Axx = root.Axx || (root.Axx = {});
  Axx.notchUI = api;
})(typeof globalThis !== 'undefined' ? globalThis : window, function () {
  'use strict';

  const MODE_LINKS = [
    { id: 'orbit', label: 'Inicio', hint: 'Resumen y accesos' },
    { id: 'parallel', label: 'Actividades', hint: 'Carriles en vivo' },
    { id: 'intent', label: 'Acciones', hint: 'Comandos rápidos' },
    { id: 'portal', label: 'Archivos', hint: 'Soltar y compartir' },
    { id: 'media', label: 'Música', hint: 'Reproductor y sesión' },
    { id: 'agents', label: 'Agentes', hint: 'Axx Code Studio' },
    { id: 'voice', label: 'Voz', hint: 'Dictado con control' },
    { id: 'resources', label: 'Sistema', hint: 'CPU, RAM y disco' },
    { id: 'recall', label: 'Recientes', hint: 'Tus conversaciones' }
  ];

  const BADGE_LABELS = {
    approval: 'APROBAR',
    error: 'ERROR',
    offline: 'OFFLINE',
    completed: 'LISTO'
  };

  const VIEW_META = {
    orbit: ['Tu AXX, al instante.', 'Conversaciones, acciones y archivos desde el borde.'],
    parallel: ['Actividades en vivo', 'Supervisa procesos paralelos sin perder el foco.'],
    intent: ['Acciones rápidas', 'Busca una herramienta o escribe lo que necesitas.'],
    portal: ['Portal de archivos', 'Suelta documentos, imágenes o enlaces para usarlos al instante.'],
    media: ['Ahora suena', 'Control multimedia del equipo en una vista panorámica.'],
    agents: ['Trabajo en curso', 'Operaciones, herramientas y aprobaciones de agentes.'],
    voice: ['Estudio de voz', 'Habla cuando estés listo con dictado revisable.'],
    chat: ['Chat directo', 'Elige proyecto y continúa sin cambiar de ventana.'],
    resources: ['El pulso de tu PC', 'Telemetría real bajo demanda, sin ruido de fondo.'],
    recall: ['Conversaciones recientes', 'Retoma cualquier hilo donde lo dejaste.']
  };

  const APPEARANCE_FIELDS = [
    ['styleDirection', 'Identidad', [['identity-accent', 'Obsidian · AXX'], ['neutral-monolith', 'Grafito neutro'], ['theme-adaptive', 'Seguir tema AXX']]],
    ['surfaceTheme', 'Atmósfera', [['obsidian', 'Obsidian'], ['midnight', 'Midnight'], ['carbon', 'Carbon OLED'], ['slate', 'Nordic Slate'], ['amethyst', 'Amethyst'], ['forest', 'Deep Forest']]],
    ['accent', 'Acento', [['avatar', 'Paleta del avatar'], ['gemini', 'Google Gemini'], ['ice', 'Hielo ártico'], ['iris', 'Iris violeta'], ['sage', 'Salvia'], ['amber', 'Ámbar'], ['emerald', 'Esmeralda'], ['rose', 'Cuarzo rosa'], ['cyberpunk', 'Cyberpunk Neón'], ['sunset', 'Atardecer'], ['gold', 'Oro solar'], ['crimson', 'Carmesí'], ['custom', 'Color libre (HEX)']]],
    ['surfaceShape', 'Forma', [['notch', 'Notch en borde'], ['island', 'Isla flotante'], ['pill', 'Píldora editorial'], ['capsule', 'Cápsula flotante'], ['ribbon', 'Barra continua'], ['bevel', 'Bisel precisión'], ['zen-dot', 'Punto Zen']]],
    ['borderStyle', 'Borde y aura', [['subtle', 'Hairline'], ['glow', 'Aura'], ['borderless', 'Sin borde'], ['neon-edge', 'Neón'], ['glass-bevel', 'Bisel'], ['prism', 'Prisma']]],
    ['horizontalAlign', 'Posición superior', [['left', 'Izquierda'], ['center', 'Centro'], ['right', 'Derecha']]],
    ['compactMetrics', 'Barra en reposo', [['auto', 'Actividad'], ['clock', 'Reloj'], ['clock-date', 'Reloj + fecha'], ['stats', 'CPU / RAM'], ['studio', 'Agentes'], ['greeting', 'Saludo'], ['minimal', 'Punto Zen']]],
    ['material', 'Material', [['solid', 'Sólido'], ['translucent', 'Glass'], ['mica', 'Mica'], ['aurora', 'Aurora'], ['frosted', 'Frosted']]],
    ['density', 'Espaciado', [['compact', 'Preciso'], ['comfortable', 'Relajado']]],
    ['surfaceScale', 'Tamaño', [['small', 'Discreto'], ['standard', 'Equilibrado'], ['large', 'Amplio']]],
    ['cornerRadiusScale', 'Esquinas', [['sharp', 'Rectas'], ['balanced', 'Equilibradas'], ['round', 'Orgánicas']]],
    ['glowIntensity', 'Intensidad aura', [['off', 'Apagada'], ['subtle', 'Sutil'], ['vivid', 'Intensa']]],
    ['fontPreset', 'Tipografía', [['system', 'Sistema'], ['geometric', 'Geométrica'], ['mono', 'HUD Mono']]],
    ['soundProfile', 'Perfil acústico', [['crystal', 'Cristal'], ['soft', 'Zen suave'], ['mechanical', 'Táctil'], ['synth', 'Synth']]],
    ['contrast', 'Contraste', [['standard', 'Estándar'], ['high', 'Alto']]],
    ['motionIntensity', 'Movimiento', [['organic', 'Fluido'], ['crisp', 'Directo'], ['reduced', 'Reducido']]]
  ];

  const SURFACE_THEMES = [
    ['obsidian', 'Obsidian', 'linear-gradient(145deg, #1b2230, #0d1017)'],
    ['midnight', 'Midnight', 'linear-gradient(145deg, #152546, #091020)'],
    ['carbon', 'Carbon', 'linear-gradient(145deg, #14161a, #040507)'],
    ['slate', 'Slate', 'linear-gradient(145deg, #273040, #141820)'],
    ['amethyst', 'Amethyst', 'linear-gradient(145deg, #24193a, #100c19)'],
    ['forest', 'Forest', 'linear-gradient(145deg, #152b24, #091410)']
  ];

  const SHAPE_CARDS = [
    ['notch', 'Notch', 'M2 2h28v10a6 6 0 0 1-6 6H8a6 6 0 0 1-6-6V2z'],
    ['island', 'Isla', 'M5 5h22a5 5 0 0 1 5 5v2a5 5 0 0 1-5 5H5a5 5 0 0 1-5-5v-2a5 5 0 0 1 5-5z'],
    ['pill', 'Píldora', 'M8 6h16a5 5 0 0 1 0 10H8a5 5 0 0 1 0-10z'],
    ['capsule', 'Cápsula', 'M4 5h24a6 6 0 0 1 0 12H4a6 6 0 0 1 0-12z'],
    ['ribbon', 'Cinta', 'M1 2h30v8a4 4 0 0 1-4 4H5a4 4 0 0 1-4-4V2z'],
    ['bevel', 'Bisel', 'M2 2h28v12l-4 4H6l-4-4V2z'],
    ['zen-dot', 'Zen Dot', 'M11 6h10a5 5 0 0 1 0 10H11a5 5 0 0 1 0-10z']
  ];

  const IDLE_FADE_DELAY_OPTIONS = [
    ['0', 'Desactivado'],
    ['3', '3 segundos'],
    ['5', '5 segundos'],
    ['8', '8 segundos'],
    ['15', '15 segundos'],
    ['30', '30 segundos'],
    ['60', '1 minuto']
  ];

  const IDLE_FADE_OPACITY_OPTIONS = [
    ['invisible', 'Invisible (0%)'],
    ['ghost', 'Ultra sutil (8%)'],
    ['subtle', 'Sutil (22%)'],
    ['dim', 'Discreto (42%)']
  ];

  const ACCENTS = {
    gemini: '#8ab4f8',
    ice: '#8ad4ff',
    iris: '#b8a6ff',
    sage: '#8be0b0',
    amber: '#f7cb77',
    emerald: '#6de8b4',
    rose: '#ff9ab8',
    cyberpunk: '#00f0ff',
    sunset: '#ff8a65',
    gold: '#ffd56b',
    crimson: '#ff6b81'
  };
  const ACCENT_SECONDARIES = {
    gemini: '#c58af9',
    ice: '#6ee7f7',
    iris: '#e0aaff',
    sage: '#5ce0a8',
    amber: '#ff9e64',
    emerald: '#38bdf8',
    rose: '#c084fc',
    cyberpunk: '#ff007f',
    sunset: '#ff5e8a',
    gold: '#ff9f43',
    crimson: '#ff9a76'
  };
  const SWATCH_META = [
    ['avatar', 'Avatar', 'linear-gradient(135deg, #4cc9f0, #7b61ff)'],
    ['gemini', 'Gemini', 'linear-gradient(135deg, #4285F4, #C58AF9)'],
    ['ice', 'Hielo', 'linear-gradient(135deg, #8ad4ff, #5eead4)'],
    ['iris', 'Iris', 'linear-gradient(135deg, #b8a6ff, #e879f9)'],
    ['sage', 'Salvia', 'linear-gradient(135deg, #8be0b0, #34d399)'],
    ['amber', 'Ámbar', 'linear-gradient(135deg, #f7cb77, #fb923c)'],
    ['emerald', 'Esmeralda', 'linear-gradient(135deg, #6de8b4, #38bdf8)'],
    ['rose', 'Rosa', 'linear-gradient(135deg, #ff9ab8, #c084fc)'],
    ['cyberpunk', 'Cyber', 'linear-gradient(135deg, #00f0ff, #ff007f)'],
    ['sunset', 'Atardecer', 'linear-gradient(135deg, #ff8a65, #ff5e8a)'],
    ['gold', 'Oro', 'linear-gradient(135deg, #ffd56b, #ff9f43)'],
    ['crimson', 'Carmesí', 'linear-gradient(135deg, #ff6b81, #fb7185)']
  ];
  const WORKSPACE_PROFILES = [
    { id: 'balanced', label: 'Minimal', description: 'Obsidian puro y calmo', values: { styleDirection: 'identity-accent', surfaceTheme: 'obsidian', surfaceShape: 'notch', borderStyle: 'subtle', density: 'compact', surfaceScale: 'standard', material: 'solid', motionIntensity: 'organic', contrast: 'standard', glowIntensity: 'off', fontPreset: 'system', surfaceOpacity: 96, topOffsetPx: 0 } },
    { id: 'focus', label: 'Zen', description: 'Isla · Mica · Silencioso', values: { styleDirection: 'neutral-monolith', surfaceTheme: 'carbon', surfaceShape: 'island', borderStyle: 'borderless', density: 'compact', surfaceScale: 'standard', material: 'mica', motionIntensity: 'crisp', contrast: 'standard', accent: 'ice', glowIntensity: 'off', fontPreset: 'geometric', compactMetrics: 'minimal', idleFadeSeconds: 5, surfaceOpacity: 92, topOffsetPx: 8 } },
    { id: 'cyberpunk', label: 'Aura', description: 'Cápsula · Aurora · Prisma', values: { styleDirection: 'identity-accent', surfaceTheme: 'midnight', surfaceShape: 'capsule', borderStyle: 'prism', density: 'compact', surfaceScale: 'standard', material: 'aurora', motionIntensity: 'organic', contrast: 'standard', accent: 'gemini', glowIntensity: 'subtle', fontPreset: 'geometric', compactMetrics: 'clock', surfaceOpacity: 94, topOffsetPx: 8 } },
    { id: 'comfortable', label: 'Cómodo', description: 'Amplio y legible', values: { styleDirection: 'identity-accent', surfaceTheme: 'slate', surfaceShape: 'notch', borderStyle: 'subtle', density: 'comfortable', surfaceScale: 'large', material: 'solid', motionIntensity: 'organic', contrast: 'high', glowIntensity: 'off', fontPreset: 'system', surfaceOpacity: 98, topOffsetPx: 0 } }
  ];

  const ICONS = {
    orbit: 'M12 3a9 9 0 1 0 9 9M12 8a4 4 0 1 0 4 4M17 3h4v4M16 8l5-5',
    intent: 'm9 6 6 6-6 6M4 20h16',
    portal: 'M12 3v11m-4-4 4 4 4-4M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4',
    media: 'M9 18V5l11-2v13M9 9l11-2M6 18a3 3 0 1 1 0-6 3 3 0 0 1 0 6Zm11-2a3 3 0 1 1 0-6 3 3 0 0 1 0 6Z',
    agents: 'M5 7h14v12H5zM9 3h6v4M9 12h.01M15 12h.01M9 16h6',
    resources: 'M3 12h4l3-7 4 14 3-7h4',
    recall: 'M3 11a9 9 0 1 1 2 7M3 4v7h7M12 7v5l3 2',
    clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 7v5l3 2',
    moon: 'M20 14.5A8 8 0 0 1 9.5 4 7 7 0 1 0 20 14.5z',
    pen: 'm15 4 5 5M4 20l5-1L21 7l-4-4L5 15z',
    parallel: 'M4 5h6v14H4zM14 5h6v14h-6z',
    voice: 'M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0zM5 10v2a7 7 0 0 0 14 0v-2M12 19v3M9 22h6',
    expand: 'm7 10 5 5 5-5',
    collapse: 'm7 14 5-5 5 5',
    undock: 'M5 9V4h5M14 20h6v-6M4 4l6 6m4 4 6 6',
    stage: 'M3 5h18v14H3zM3 10h18M9 10v9',
    tune: 'M4 7h6m4 0h6M4 17h10m4 0h2M10 4v6m4 4v6',
    close: 'm6 6 12 12M6 18 18 6',
    play: 'm8 5 11 7-11 7z',
    pause: 'M8 5v14M16 5v14',
    previous: 'M6 5v14m12-14L8 12l10 7z',
    next: 'M18 5v14M6 5l10 7-10 7z',
    pin: 'm9 3 6 0-1 7 4 4H6l4-4-1-7M12 14v7',
    check: 'm5 12 4 4L19 6',
    search: 'M20 20l-4.5-4.5M17 10.5a6.5 6.5 0 1 1-13 0 6.5 6.5 0 0 1 13 0',
    arrowUpRight: 'M7 17 17 7M9 7h8v8',
    file: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5',
    image: 'M4 6h16v12H4zM8 10.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3M5 17l4.5-4.5 3.5 3 3-2.5 4 4',
    link: 'M10 13a5 5 0 0 0 7.1.2l2.1-2.1a5 5 0 0 0-7.1-7.1L10.8 5.3M14 11a5 5 0 0 0-7.1-.2L4.8 13a5 5 0 0 0 7.1 7.1l1.2-1.2',
    terminal: 'm6 8 4 4-4 4M12 16h6',
    chat: 'M5 6h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H9l-4 3v-3H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z',
    volume: 'M11 5 6 9H3v6h3l5 4zM15.5 8.5a5 5 0 0 1 0 7M18.5 6a8.5 8.5 0 0 1 0 12',
    shield: 'M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6z',
    cpu: 'M7 7h10v10H7zM9 3v4M15 3v4M9 17v4M15 17v4M3 9h4M3 15h4M17 9h4M17 15h4'
  };

  function icon(name, size = 17) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    for (const [k, v] of Object.entries({ viewBox: '0 0 24 24', width: size, height: size, fill: 'none', stroke: 'currentColor', 'stroke-width': 1.65, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' })) {
      svg.setAttribute(k, String(v));
    }
    const path = document.createElementNS(svg.namespaceURI, 'path');
    path.setAttribute('d', ICONS[name] || ICONS.orbit);
    svg.append(path);
    return svg;
  }

  let ringGradSeq = 0;
  function createResourceRing(percent, tone = 'accent') {
    const r = 27;
    const c = 2 * Math.PI * r;
    const safePct = Number.isFinite(percent) ? Math.max(0, Math.min(100, percent)) : 0;
    const offset = c * (1 - safePct / 100);
    const gid = `notch-ring-g-${++ringGradSeq}`;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 68 68');
    svg.setAttribute('class', 'notch-resource-ring');
    svg.setAttribute('aria-hidden', 'true');
    const defs = document.createElementNS(svg.namespaceURI, 'defs');
    const grad = document.createElementNS(svg.namespaceURI, 'linearGradient');
    grad.setAttribute('id', gid);
    grad.setAttribute('x1', '0%'); grad.setAttribute('y1', '0%');
    grad.setAttribute('x2', '100%'); grad.setAttribute('y2', '100%');
    const s1 = document.createElementNS(svg.namespaceURI, 'stop');
    s1.setAttribute('offset', '0%');
    s1.setAttribute('stop-color', tone === 'warning' ? 'var(--notch-warning)' : 'var(--notch-accent)');
    const s2 = document.createElementNS(svg.namespaceURI, 'stop');
    s2.setAttribute('offset', '100%');
    s2.setAttribute('stop-color', tone === 'warning' ? 'var(--notch-danger)' : 'var(--notch-accent-2)');
    grad.append(s1, s2);
    defs.append(grad);
    const outer = document.createElementNS(svg.namespaceURI, 'circle');
    outer.setAttribute('cx', '34'); outer.setAttribute('cy', '34'); outer.setAttribute('r', '31');
    outer.setAttribute('class', 'notch-ring-halo');
    const bg = document.createElementNS(svg.namespaceURI, 'circle');
    bg.setAttribute('cx', '34'); bg.setAttribute('cy', '34'); bg.setAttribute('r', String(r));
    bg.setAttribute('class', 'notch-ring-track');
    const fg = document.createElementNS(svg.namespaceURI, 'circle');
    fg.setAttribute('cx', '34'); fg.setAttribute('cy', '34'); fg.setAttribute('r', String(r));
    fg.setAttribute('class', 'notch-ring-fill');
    fg.dataset.tone = tone;
    fg.setAttribute('stroke', `url(#${gid})`);
    fg.style.strokeDasharray = c.toFixed(2);
    fg.style.strokeDashoffset = (Number.isFinite(percent) ? offset : c).toFixed(2);
    svg.append(defs, outer, bg, fg);
    return svg;
  }

  function readableAccent(value) {
    const raw = /^#[0-9a-f]{6}$/i.test(value || '') ? value : '#8ad4ff';
    let rgb = [1, 3, 5].map(i => parseInt(raw.slice(i, i + 2), 16));
    const luminance = (values) => values.map(x => x / 255).map(x => x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4).reduce((sum, x, i) => sum + x * [0.2126, 0.7152, 0.0722][i], 0);
    for (let n = 0; n < 24 && (luminance(rgb) + 0.05) / (luminance([36, 39, 44]) + 0.05) < 4.5; n++) rgb = rgb.map(x => Math.round(x + (255 - x) * 0.12));
    return '#' + rgb.map(x => x.toString(16).padStart(2, '0')).join('');
  }

  function createEl(tag, cls, attrs = {}) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined) continue;
      if (k === 'text') el.textContent = String(v);
      else el.setAttribute(k, String(v));
    }
    return el;
  }

  function paletteColors(Axx) {
    const raw = Axx?.app?.store?.data?.settings?.palette;
    const idx = Number.isInteger(raw) ? raw : 0;
    const pal = Axx?.PALETTES?.[idx] || Axx?.PALETTES?.[0];
    const stops = Array.isArray(pal?.colors) && pal.colors.length >= 2 ? pal.colors : ['#4cc9f0', '#7b61ff'];
    return [stops[0], stops[Math.min(1, stops.length - 1)]];
  }

  function formatBytes(b) {
    const n = Number(b) || 0;
    if (n < 1024) return `${n} B`;
    if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1048576).toFixed(1)} MB`;
  }

  function createAvatarPortrait() {
    return createEl('img', 'notch-avatar-portrait', { alt: '', 'aria-hidden': 'true', draggable: 'false', hidden: '' });
  }

  function createNotchUI(handlers = {}) {
    const rootEl = createEl('div', '', { id: 'axx-notch-root', 'data-style': 'identity-accent' });
    const approachEl = createEl('div', '', {
      id: 'axx-notch-approach',
      'data-active': 'false',
      'aria-hidden': 'true'
    });
    approachEl.append(createAvatarPortrait(), createEl('span', '', { text: 'Soltar para acoplar AXX' }));

    const shellEl = createEl('section', '', {
      id: 'axx-notch-shell',
      hidden: '',
      tabindex: '-1',
      role: 'region',
      'aria-label': 'AXX Notch',
      'data-size': 'compact',
      'data-content': 'home',
      'data-attention': 'idle',
      'data-layout-mode': 'minimal',
      'data-idle-faded': 'false'
    });

    const headerEl = createEl('div', 'notch-header');
    const spineBtn = createEl('button', 'notch-spine-btn', {
      type: 'button',
      id: 'notch-spine-btn',
      'aria-label': 'Expandir o contraer AXX Notch',
      title: 'Expandir / Contraer (Alt+Shift+N)'
    });
    const dotEl = createEl('span', 'notch-attention-dot', { 'aria-hidden': 'true' });
    spineBtn.append(createAvatarPortrait(), dotEl);

    const leadingEl = createEl('div', 'notch-leading');
    const badgeEl = createEl('span', 'notch-status-badge', { id: 'notch-status-badge', hidden: '' });
    const titleEl = createEl('span', 'notch-primary-title', { id: 'notch-primary-title', text: 'AXX' });
    const metricEl = createEl('span', 'notch-primary-metric', { id: 'notch-primary-metric', text: '' });
    leadingEl.append(badgeEl, titleEl, metricEl);

    const trailingEl = createEl('div', 'notch-trailing');
    const peakMiniEl = createEl('span', 'notch-peak-mini', { id: 'notch-peak-mini', hidden: '', 'aria-hidden': 'true' });
    for (let i = 0; i < 4; i++) peakMiniEl.append(createEl('i'));

    const overflowBtn = createEl('button', 'notch-overflow-pill', {
      type: 'button',
      id: 'notch-overflow-pill',
      hidden: '',
      'aria-label': 'Ver actividades concurrentes'
    });
    const expandBtn = createEl('button', 'notch-icon-btn', {
      type: 'button',
      id: 'notch-expand-btn',
      'aria-label': 'Abrir superficie ampliada del Notch',
      title: 'Expandir o contraer'
    });
    expandBtn.append(icon('expand', 15));
    const undockBtn = createEl('button', 'notch-icon-btn', {
      type: 'button',
      id: 'notch-undock-btn',
      'aria-label': 'Desacoplar a avatar 3D',
      title: 'Volver al avatar 3D libre'
    });
    undockBtn.append(icon('undock', 14));
    const quickChatBtn = createEl('button', 'notch-quick-chat-btn', { type: 'button', id: 'notch-quick-chat-btn', text: 'Escribir', 'aria-label': 'Escribir a un chat desde AXX' });
    quickChatBtn.addEventListener('click', () => handlers.onSelectContent?.('chat'));

    trailingEl.append(peakMiniEl, overflowBtn, quickChatBtn, expandBtn, undockBtn);
    headerEl.append(spineBtn, leadingEl, trailingEl);

    const progressTrack = createEl('div', 'notch-progress-track', { id: 'notch-progress-track', hidden: '' });
    const progressFill = createEl('div', 'notch-progress-fill', { id: 'notch-progress-fill' });
    progressTrack.append(progressFill);

    const bodyEl = createEl('div', 'notch-body', { id: 'notch-body' });
    const approvalHost = createEl('div', 'notch-approval-host', { hidden: '' });
    let approvalSignature = '';
    const footerEl = createEl('div', 'notch-context-footer', { id: 'notch-context-footer' });
    const liveEl = createEl('div', 'notch-sr-only', { id: 'notch-live-status', 'aria-live': 'polite' });
    const appearanceEl = createEl('section', 'notch-appearance-sheet', { id: 'notch-appearance-sheet', 'aria-label': 'Personalizar Notch', hidden: '' });
    let appearancePrefs = {};
    let appearanceReturnFocus = null;

    function closeAppearance(restoreFocus = true) {
      const wasOpen = !appearanceEl.hidden;
      appearanceEl.hidden = true;
      bodyEl.inert = false;
      if (restoreFocus && appearanceReturnFocus?.isConnected) appearanceReturnFocus.focus();
      if (wasOpen) handlers.onAppearanceChange?.(false);
    }

    function shapeSvg(d) {
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      for (const [k, v] of Object.entries({ viewBox: '0 0 32 20', width: 30, height: 18, fill: 'none', stroke: 'currentColor', 'stroke-width': 1.5, 'aria-hidden': 'true' })) {
        svg.setAttribute(k, String(v));
      }
      const p = document.createElementNS(svg.namespaceURI, 'path');
      p.setAttribute('d', d);
      p.setAttribute('fill', 'currentColor');
      p.setAttribute('fill-opacity', '0.16');
      svg.append(p);
      return svg;
    }

    let previewPillEl = null;
    let previewMetaEl = null;
    let previewTimeEl = null;

    function syncLivePreview() {
      if (!previewPillEl) return;
      const p = appearancePrefs;
      previewPillEl.setAttribute('data-shape', p.surfaceShape || 'notch');
      previewPillEl.setAttribute('data-material', p.material || 'solid');
      previewPillEl.setAttribute('data-border-style', p.borderStyle || 'subtle');
      previewPillEl.setAttribute('data-theme', p.surfaceTheme || 'obsidian');
      previewPillEl.setAttribute('data-font', p.fontPreset || 'system');
      previewPillEl.setAttribute('data-align', p.horizontalAlign || 'center');
      const cm = p.compactMetrics || 'auto';
      if (previewTimeEl) {
        const now = new Date();
        previewTimeEl.textContent = cm === 'clock'
          ? now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          : cm === 'clock-date'
            ? `${now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · ${now.toLocaleDateString([], { weekday: 'short', day: 'numeric' })}`
            : cm === 'stats' ? 'CPU 18% · RAM 46%'
            : cm === 'studio' ? 'Studio · Listo'
            : cm === 'greeting' ? (now.getHours() < 12 ? 'Buenos días' : now.getHours() < 19 ? 'Buenas tardes' : 'Buenas noches')
            : cm === 'minimal' ? ''
            : 'En línea';
      }
      if (previewMetaEl) {
        const shapeLbl = (SHAPE_CARDS.find(([k]) => k === (p.surfaceShape || 'notch')) || ['', 'Notch'])[1];
        const matLbl = (APPEARANCE_FIELDS.find(([k]) => k === 'material')?.[2]?.find(([v]) => v === (p.material || 'solid')) || ['', 'Sólido'])[1];
        const thLbl = (SURFACE_THEMES.find(([k]) => k === (p.surfaceTheme || 'obsidian')) || ['', 'Obsidian'])[1];
        previewMetaEl.textContent = `${shapeLbl} · ${thLbl} · ${matLbl} · ${p.surfaceOpacity ?? 96}%`;
      }
    }

    function openAppearance(trigger) {
      chatSurface?.closePicker?.();
      appearanceReturnFocus = trigger;
      appearanceEl.replaceChildren();
      const top = createEl('div', 'notch-row-between notch-sheet-head');
      const titleGroup = createEl('div', 'notch-sheet-title');
      titleGroup.append(createEl('span', 'notch-eyebrow', { text: 'NOTCH DESIGN STUDIO' }), createEl('h2', 'notch-title-md', { text: 'Diseña tu AXX' }));
      const close = createEl('button', 'notch-icon-btn', { type: 'button', 'aria-label': 'Cerrar personalización' });
      close.append(icon('close', 16));
      close.addEventListener('click', () => closeAppearance());
      top.append(titleGroup, close);

      // Interactive Live Miniature Notch Preview Stage
      const stagePreview = createEl('div', 'notch-live-stage');
      const horizon = createEl('div', 'notch-live-horizon');
      previewPillEl = createEl('div', 'notch-mini-notch', { 'data-shape': appearancePrefs.surfaceShape || 'notch' });
      const miniPortrait = createAvatarPortrait();
      if (avatarPortrait) { miniPortrait.src = avatarPortrait; miniPortrait.hidden = false; }
      const miniTitle = createEl('span', 'notch-mini-brand', { text: 'AXX' });
      previewTimeEl = createEl('span', 'notch-mini-metric', { text: 'En línea' });
      const miniDot = createEl('span', 'notch-mini-dot', { 'aria-hidden': 'true' });
      previewPillEl.append(miniPortrait, miniTitle, previewTimeEl, miniDot);
      horizon.append(previewPillEl);
      previewMetaEl = createEl('div', 'notch-live-caption', { text: 'Notch · Obsidian · Sólido · 96%' });
      stagePreview.append(horizon, previewMetaEl);
      syncLivePreview();
      appearanceEl.append(top, stagePreview);

      const tabsNav = createEl('div', 'notch-sheet-tabs', { role: 'tablist', 'aria-label': 'Categorías de personalización' });
      const panes = {};
      let activeTab = 'style';
      const selectTab = (tabId) => {
        activeTab = tabId;
        playTactileChime('click');
        for (const btn of tabsNav.children) btn.setAttribute('aria-selected', String(btn.dataset.tab === tabId));
        for (const [id, pane] of Object.entries(panes)) pane.hidden = id !== tabId;
      };
      for (const [id, label] of [['style', 'Estudio'], ['geometry', 'Forma'], ['bar', 'Barra y Aura'], ['system', 'Sistema']]) {
        const b = createEl('button', 'notch-sheet-tab', { type: 'button', role: 'tab', 'data-tab': id, 'aria-selected': String(id === activeTab), text: label });
        b.addEventListener('click', () => selectTab(id));
        tabsNav.append(b);
      }
      appearanceEl.append(tabsNav);

      const applyPref = (patch) => {
        playTactileChime('click');
        handlers.onPreferencesChange?.(patch);
      };

      const mkSegmented = (key, label, options, compact = false) => {
        const wrap = createEl('div', 'notch-seg-block');
        if (label) wrap.append(createEl('span', 'notch-eyebrow', { text: label }));
        const bar = createEl('div', 'notch-seg-group' + (compact ? ' notch-seg-compact' : ''), { 'data-seg-pref': key });
        for (const [val, txt] of options) {
          const btn = createEl('button', 'notch-seg-btn', {
            type: 'button',
            'data-seg-key': key,
            'data-seg-val': val,
            'aria-pressed': String((appearancePrefs[key] ?? options[0][0]) === val),
            text: txt
          });
          btn.addEventListener('click', () => applyPref({ [key]: val }));
          bar.append(btn);
        }
        wrap.append(bar);
        return wrap;
      };

      // ── TAB 1: ESTUDIO (Perfiles, Atmósfera, Acento + Color Picker libre, Material, Borde) ──
      const stylePane = createEl('div', 'notch-tab-pane');
      const profiles = createEl('div', 'notch-profile-options', { 'aria-label': 'Perfiles de apariencia' });
      for (const profile of WORKSPACE_PROFILES) {
        const active = Object.entries(profile.values).every(([key, value]) => appearancePrefs[key] === value);
        const button = createEl('button', 'notch-profile-option', { type: 'button', 'data-profile': profile.id, 'aria-pressed': String(active) });
        button.append(createEl('strong', '', { text: profile.label }), createEl('span', 'notch-muted', { text: profile.description }));
        button.addEventListener('click', () => applyPref(profile.values));
        profiles.append(button);
      }
      stylePane.append(profiles);

      // Surface Theme Visual Swatches (6 Atmospheric Finishes)
      const themeBar = createEl('div', 'notch-studio-strip');
      themeBar.append(createEl('span', 'notch-eyebrow', { text: 'ATMÓSFERA DE SUPERFICIE' }));
      const themeRow = createEl('div', 'notch-theme-row');
      for (const [id, label, bg] of SURFACE_THEMES) {
        const chip = createEl('button', 'notch-theme-chip', {
          type: 'button',
          'data-seg-key': 'surfaceTheme',
          'data-seg-val': id,
          'aria-pressed': String((appearancePrefs.surfaceTheme || 'obsidian') === id)
        });
        const orb = createEl('span', 'notch-theme-orb', { 'aria-hidden': 'true' });
        orb.style.background = bg;
        chip.append(orb, createEl('span', '', { text: label }));
        chip.addEventListener('click', () => applyPref({ surfaceTheme: id }));
        themeRow.append(chip);
      }
      themeBar.append(themeRow);
      stylePane.append(themeBar);

      // Accent Gemstone Swatches + Free HEX Color Picker
      const swatchRow = createEl('div', 'notch-swatch-bar');
      swatchRow.append(createEl('span', 'notch-eyebrow', { text: 'ACENTO CROMÁTICO' }));
      const swatches = createEl('div', 'notch-swatch-row');
      for (const [id, label, color] of SWATCH_META) {
        const sw = createEl('button', 'notch-swatch', {
          type: 'button',
          title: label,
          'aria-label': `Acento ${label}`,
          'data-swatch': id,
          'aria-pressed': String((appearancePrefs.accent || 'avatar') === id)
        });
        sw.style.background = color;
        sw.addEventListener('click', () => applyPref({ accent: id }));
        swatches.append(sw);
      }
      const colorWrap = createEl('label', 'notch-color-picker-btn', {
        title: 'Elegir color personalizado (HEX)',
        'aria-label': 'Color de acento personalizado',
        'data-swatch': 'custom',
        'aria-pressed': String(appearancePrefs.accent === 'custom')
      });
      const colorInput = createEl('input', 'notch-color-input', {
        type: 'color',
        value: appearancePrefs.customAccentHex || '#8ab4f8',
        'data-preference': 'customAccentHex',
        'aria-label': 'Selector de color HEX'
      });
      colorInput.addEventListener('input', () => handlers.onPreferencesChange?.({ accent: 'custom', customAccentHex: colorInput.value }));
      colorWrap.style.background = `conic-gradient(from 0deg, #ff6b81, #ffd56b, #6de8b4, #8ab4f8, #b8a6ff, #ff6b81)`;
      colorWrap.append(colorInput);
      swatches.append(colorWrap);
      swatchRow.append(swatches);
      stylePane.append(swatchRow);

      // Material + Border Segmented Cards (side-by-side cleanly or stacked ultra-crisp)
      stylePane.append(
        mkSegmented('material', 'MATERIAL ÓPTICO', APPEARANCE_FIELDS.find(([k]) => k === 'material')[2]),
        mkSegmented('borderStyle', 'BORDE Y AURA PERIMETRAL', APPEARANCE_FIELDS.find(([k]) => k === 'borderStyle')[2])
      );
      panes.style = stylePane;

      // ── TAB 2: FORMA (7 Siluetas visuales + Proporción + Sliders en vivo) ──
      const geoPane = createEl('div', 'notch-tab-pane', { hidden: '' });
      const shapeWrap = createEl('div', 'notch-studio-strip');
      shapeWrap.append(createEl('span', 'notch-eyebrow', { text: 'FACTOR DE FORMA (7 SILUETAS)' }));
      const shapeGrid = createEl('div', 'notch-shape-grid');
      for (const [id, label, pathD] of SHAPE_CARDS) {
        const card = createEl('button', 'notch-shape-card', {
          type: 'button',
          'data-seg-key': 'surfaceShape',
          'data-seg-val': id,
          'aria-pressed': String((appearancePrefs.surfaceShape || 'notch') === id)
        });
        card.append(shapeSvg(pathD), createEl('span', '', { text: label }));
        card.addEventListener('click', () => applyPref({ surfaceShape: id }));
        shapeGrid.append(card);
      }
      shapeWrap.append(shapeGrid);
      geoPane.append(shapeWrap);

      const propGrid = createEl('div', 'notch-appearance-grid');
      const propLeft = createEl('div', 'notch-settings-pane');
      propLeft.append(
        mkSegmented('horizontalAlign', 'POSICIÓN SUPERIOR', APPEARANCE_FIELDS.find(([k]) => k === 'horizontalAlign')[2], true),
        mkSegmented('cornerRadiusScale', 'CURVATURA DE ESQUINAS', APPEARANCE_FIELDS.find(([k]) => k === 'cornerRadiusScale')[2], true)
      );
      const propRight = createEl('div', 'notch-settings-pane');
      propRight.append(
        mkSegmented('surfaceScale', 'ESCALA DE SUPERFICIE', APPEARANCE_FIELDS.find(([k]) => k === 'surfaceScale')[2], true),
        mkSegmented('density', 'ESPACIADO INTERNO', APPEARANCE_FIELDS.find(([k]) => k === 'density')[2], true)
      );
      propGrid.append(propLeft, propRight);
      geoPane.append(propGrid);

      const sliderGrid = createEl('div', 'notch-appearance-grid');
      const mkSlider = (key, label, min, max, unit) => {
        const card = createEl('div', 'notch-settings-pane notch-slider-card');
        const head = createEl('div', 'notch-row-between');
        const valSpan = createEl('span', 'notch-badge-chip', { 'data-slider-val': key, text: `${appearancePrefs[key] ?? min}${unit}` });
        head.append(createEl('span', 'notch-eyebrow', { text: label }), valSpan);
        const inp = createEl('input', 'notch-range-slider', {
          type: 'range',
          min: String(min),
          max: String(max),
          value: String(appearancePrefs[key] ?? min),
          'data-preference': key,
          'aria-label': label
        });
        inp.addEventListener('input', () => {
          valSpan.textContent = `${inp.value}${unit}`;
          handlers.onPreferencesChange?.({ [key]: Number(inp.value) });
        });
        card.append(head, inp);
        return card;
      };
      sliderGrid.append(
        mkSlider('surfaceOpacity', 'OPACIDAD DE SUPERFICIE', 65, 100, '%'),
        mkSlider('topOffsetPx', 'MARGEN SUPERIOR', 0, 24, ' px')
      );
      geoPane.append(sliderGrid);
      panes.geometry = geoPane;

      // ── TAB 3: BARRA Y AURA (Widgets en reposo, Tipografía, Aura, Auto-Fade) ──
      const barPane = createEl('div', 'notch-tab-pane', { hidden: '' });
      barPane.append(mkSegmented('compactMetrics', 'WIDGET DE BARRA EN REPOSO', APPEARANCE_FIELDS.find(([k]) => k === 'compactMetrics')[2], true));

      const typoGrid = createEl('div', 'notch-appearance-grid');
      const typoLeft = createEl('div', 'notch-settings-pane');
      typoLeft.append(
        mkSegmented('fontPreset', 'TIPOGRAFÍA', APPEARANCE_FIELDS.find(([k]) => k === 'fontPreset')[2], true),
        mkSegmented('motionIntensity', 'DINÁMICA DE MOVIMIENTO', APPEARANCE_FIELDS.find(([k]) => k === 'motionIntensity')[2], true)
      );
      const typoRight = createEl('div', 'notch-settings-pane');
      typoRight.append(
        mkSegmented('glowIntensity', 'INTENSIDAD DE AURA', APPEARANCE_FIELDS.find(([k]) => k === 'glowIntensity')[2], true),
        mkSegmented('contrast', 'CONTRASTE VISUAL', APPEARANCE_FIELDS.find(([k]) => k === 'contrast')[2], true)
      );
      typoGrid.append(typoLeft, typoRight);
      barPane.append(typoGrid);

      const fadeGrid = createEl('div', 'notch-appearance-grid');
      const fadeCard = createEl('div', 'notch-settings-pane');
      fadeCard.append(createEl('span', 'notch-eyebrow', { text: 'AUTO-FADE INTELIGENTE' }));
      const mkToggle = (key, label) => {
        const row = createEl('label', 'notch-settings-row');
        const check = createEl('input', '', { type: 'checkbox', 'data-preference': key });
        check.checked = Boolean(appearancePrefs[key]);
        check.addEventListener('change', () => applyPref({ [key]: check.checked }));
        row.append(createEl('span', '', { text: label }), check);
        return row;
      };
      fadeCard.append(mkToggle('idleFadeEnabled', 'Desvanecer al no usar'));
      const delayRow = createEl('label', 'notch-settings-row');
      const delaySel = createEl('select', 'notch-field', { 'data-preference': 'idleFadeSeconds', 'aria-label': 'Tiempo para desvanecer' });
      for (const [val, txt] of IDLE_FADE_DELAY_OPTIONS) delaySel.add(new Option(txt, val));
      delaySel.value = String(appearancePrefs.idleFadeSeconds ?? 8);
      delaySel.addEventListener('change', () => applyPref({ idleFadeSeconds: Number(delaySel.value) }));
      delayRow.append(createEl('span', '', { text: 'Espera' }), delaySel);
      const opRow = createEl('label', 'notch-settings-row');
      const opSel = createEl('select', 'notch-field', { 'data-preference': 'idleFadeOpacity', 'aria-label': 'Opacidad en reposo' });
      for (const [val, txt] of IDLE_FADE_OPACITY_OPTIONS) opSel.add(new Option(txt, val));
      opSel.value = appearancePrefs.idleFadeOpacity || 'subtle';
      opSel.addEventListener('change', () => applyPref({ idleFadeOpacity: opSel.value }));
      opRow.append(createEl('span', '', { text: 'Transparencia' }), opSel);
      fadeCard.append(delayRow, opRow);

      const elemCard = createEl('div', 'notch-settings-pane');
      elemCard.append(
        createEl('span', 'notch-eyebrow', { text: 'ELEMENTOS EN BARRA' }),
        mkToggle('showAvatarInNotch', 'Retrato 3D en barra compacta'),
        mkToggle('showQuickChatButton', 'Acceso rápido «Escribir»'),
        mkToggle('ambientPulse', 'Respiración ambiental de acento')
      );
      fadeGrid.append(fadeCard, elemCard);
      barPane.append(fadeGrid);
      panes.bar = barPane;

      // ── TAB 4: SISTEMA (Audio Háptico, Interacción, Privacidad y Presets JSON) ──
      const sysPane = createEl('div', 'notch-tab-pane', { hidden: '' });
      const soundCard = createEl('div', 'notch-settings-pane');
      const soundHead = createEl('div', 'notch-row-between');
      soundHead.append(createEl('span', 'notch-eyebrow', { text: 'ESTUDIO ACÚSTICO (WEB AUDIO)' }));
      const testSoundBtn = createEl('button', 'notch-pill-btn notch-btn-xs', { type: 'button', text: 'Probar sonido' });
      testSoundBtn.addEventListener('click', () => playTactileChime('dock', true));
      soundHead.append(testSoundBtn);
      soundCard.append(
        soundHead,
        mkToggle('soundEffectsEnabled', 'Feedback acústico en docking, acciones y archivos'),
        mkSegmented('soundProfile', '', APPEARANCE_FIELDS.find(([k]) => k === 'soundProfile')[2], true)
      );
      sysPane.append(soundCard);

      const privGrid = createEl('div', 'notch-appearance-grid');
      const interCard = createEl('div', 'notch-settings-pane');
      interCard.append(
        createEl('span', 'notch-eyebrow', { text: 'INTERACCIÓN' }),
        mkToggle('hoverPeek', 'Vista rápida (Peek) al pasar cursor'),
        mkToggle('autoDockOnTopDrag', 'Acoplar al arrastrar al borde'),
        mkToggle('suspendRendererWhenDocked', 'Suspender 3D al acoplar')
      );
      const privCard = createEl('div', 'notch-settings-pane');
      privCard.append(
        createEl('span', 'notch-eyebrow', { text: 'PRIVACIDAD E IDENTIDAD' }),
        mkToggle('privacyCurtain', 'Ocultar datos sensibles'),
        mkToggle('autoHideFullscreen', 'Ocultar en pantalla completa'),
        mkSegmented('styleDirection', '', [['identity-accent', 'AXX'], ['neutral-monolith', 'Neutro'], ['theme-adaptive', 'Tema']], true)
      );
      privGrid.append(interCard, privCard);
      sysPane.append(privGrid);

      const presetCard = createEl('div', 'notch-settings-pane');
      const presetHead = createEl('div', 'notch-row-between');
      const presetStatus = createEl('span', 'notch-muted', { text: appearancePrefs.customPreset ? 'Tienes un diseño guardado' : 'Guarda o comparte tu diseño' });
      presetHead.append(createEl('span', 'notch-eyebrow', { text: 'MI PRESET Y PORTABILIDAD' }), presetStatus);
      const presetRow = createEl('div', 'notch-actions-row');
      const saveMine = createEl('button', 'notch-pill-btn notch-btn-xs', { type: 'button', 'data-primary': 'true', text: 'Guardar mi diseño' });
      const applyMine = createEl('button', 'notch-pill-btn notch-btn-xs', { type: 'button', text: 'Aplicar mi diseño', ...(appearancePrefs.customPreset ? {} : { disabled: '' }) });
      const copyJson = createEl('button', 'notch-pill-btn notch-btn-xs', { type: 'button', text: 'Copiar JSON' });
      const importJson = createEl('button', 'notch-pill-btn notch-btn-xs', { type: 'button', text: 'Importar JSON' });
      saveMine.addEventListener('click', () => {
        handlers.onSaveCustomPreset?.();
        applyMine.disabled = false;
        presetStatus.textContent = 'Diseño guardado';
        playTactileChime('dock');
      });
      applyMine.addEventListener('click', () => {
        if (handlers.onApplyCustomPreset?.()) {
          presetStatus.textContent = 'Diseño aplicado';
          playTactileChime('click');
        }
      });
      copyJson.addEventListener('click', async () => {
        const json = handlers.onExportPreferences?.() || '';
        try { await navigator.clipboard?.writeText?.(json); presetStatus.textContent = 'JSON copiado al portapapeles'; }
        catch { presetStatus.textContent = 'Exportado en Axx.notch.exportPreferencesJSON()'; }
      });
      importJson.addEventListener('click', () => {
        const raw = typeof window.prompt === 'function' ? window.prompt('Pega el JSON de configuración del Notch:') : '';
        if (!raw) return;
        const res = handlers.onImportPreferences?.(raw);
        presetStatus.textContent = res?.ok ? 'Diseño importado' : (res?.reason || 'JSON inválido');
      });
      presetRow.append(saveMine, applyMine, copyJson, importJson);
      presetCard.append(presetHead, presetRow);
      sysPane.append(presetCard);
      panes.system = sysPane;

      appearanceEl.append(stylePane, geoPane, barPane, sysPane);

      const actionFoot = createEl('div', 'notch-row-between notch-sheet-footer');
      const hide = createEl('button', 'notch-pill-btn', { type: 'button', id: 'notch-hide-btn', text: 'Ocultar · Alt+Shift+N para volver' });
      hide.addEventListener('click', () => handlers.onHideNotch?.());
      const resetBtn = createEl('button', 'notch-pill-btn', { type: 'button', 'data-danger': 'true', text: 'Restablecer' });
      resetBtn.addEventListener('click', () => handlers.onPreferencesChange?.({ resetNotch: true }));
      actionFoot.append(hide, resetBtn);
      appearanceEl.append(actionFoot);

      appearanceEl.hidden = false;
      bodyEl.inert = true;
      close.focus();
      handlers.onAppearanceChange?.(true);
    }

    shellEl.append(headerEl, progressTrack, approvalHost, bodyEl, footerEl, appearanceEl, liveEl);
    rootEl.append(approachEl, shellEl);

    const mountRoot = () => {
      if (!document.body) return;
      if (!document.getElementById('axx-notch-root')) document.body.appendChild(rootEl);
    };
    if (document.body) mountRoot();
    else document.addEventListener('DOMContentLoaded', mountRoot, { once: true });

    spineBtn.addEventListener('click', () => handlers.onToggleExpand?.());
    expandBtn.addEventListener('click', () => handlers.onToggleExpand?.());
    overflowBtn.addEventListener('click', () => handlers.onSelectContent?.('parallel'));
    undockBtn.addEventListener('click', () => handlers.onUndock?.('button'));

    let pullStartY = null;
    let pulledToUndock = false;
    headerEl.addEventListener('pointerdown', (ev) => {
      handlers.onUserActivity?.();
      if (ev.target.closest('button')) return;
      pullStartY = ev.clientY;
      pulledToUndock = false;
    });
    window.addEventListener('pointermove', (ev) => {
      if (pullStartY === null) return;
      if (ev.clientY - pullStartY >= 52) {
        pullStartY = null;
        pulledToUndock = true;
        handlers.onUndock?.('pull-down');
      }
    });
    window.addEventListener('pointerup', () => { pullStartY = null; });
    window.addEventListener('pointercancel', () => { pullStartY = null; });
    headerEl.addEventListener('click', (ev) => {
      const fromButton = ev.composedPath().some(node => node?.tagName === 'BUTTON');
      if (!fromButton && !pulledToUndock) handlers.onToggleExpand?.();
    });

    shellEl.addEventListener('pointerenter', () => handlers.onPointerEnter?.());
    shellEl.addEventListener('pointerleave', () => handlers.onPointerLeave?.());
    shellEl.addEventListener('pointermove', () => handlers.onUserActivity?.(), { passive: true });
    shellEl.addEventListener('input', () => handlers.onUserActivity?.(), true);
    shellEl.addEventListener('click', () => handlers.onUserActivity?.(), true);
    shellEl.addEventListener('dragenter', (ev) => { ev.preventDefault(); handlers.onUserActivity?.(); handlers.onDragEnter?.(ev); });
    shellEl.addEventListener('dragover', (ev) => { ev.preventDefault(); });
    shellEl.addEventListener('dragleave', (ev) => {
      if (ev.relatedTarget && shellEl.contains(ev.relatedTarget)) return;
      handlers.onDragLeave?.(ev);
    });
    shellEl.addEventListener('drop', (ev) => {
      ev.preventDefault();
      handlers.onUserActivity?.();
      const files = Array.from(ev.dataTransfer?.files || []);
      const text = ev.dataTransfer?.getData?.('text/plain') || '';
      const uriList = ev.dataTransfer?.getData?.('text/uri-list') || '';
      const links = uriList.split(/\r?\n/).filter(line => line && !line.startsWith('#'));
      handlers.onDrop?.({ files, text: links[0] || text });
    });
    shellEl.addEventListener('keydown', (ev) => {
      handlers.onUserActivity?.();
      if (ev.key === 'Escape') {
        ev.stopPropagation();
        if (!appearanceEl.hidden) closeAppearance();
        else handlers.onEscape?.();
      }
    });

    let lastBodySig = '';
    let lastRenderedContent = '';
    let lastLiveMsg = '';
    let intentInputRef = null;
    let selectedIntentIdx = 0;
    let chatSurface = null;
    let avatarSignature = '';
    let avatarPortrait = '';
    let avatarCaptureFailures = 0;
    let avatarCaptures = 0;
    let avatarCapturedAt = 0;
    function AxxOpticalSettings() { return typeof window !== 'undefined' ? window.AxxOpticalGlass?.get?.() : null; }

    function refreshAvatar(Axx, state) {
      if (!state.enabled) return;
      const renderer = Axx?.app?.renderer;
      if (!renderer?.captureIdentityPNG) return;
      if (state.physical === 'free' && avatarPortrait) return;
      const signature = JSON.stringify([renderer.settings?.form, renderer.settings?.palette, renderer.settings?.scale, renderer.finish, renderer.studio, state.dockEpoch, AxxOpticalSettings()]);
      if (signature === avatarSignature) {
        for (const img of document.querySelectorAll('.notch-avatar-portrait:not([src])')) { img.src = avatarPortrait; img.hidden = false; }
        return;
      }
      if (performance.now() - avatarCapturedAt < 180) return;
      avatarCapturedAt = performance.now();
      try {
        const portrait = renderer.captureIdentityPNG(192);
        if (!portrait?.startsWith('data:image/png')) return;
        avatarPortrait = portrait;
        avatarCaptures++;
        avatarSignature = signature;
        for (const img of document.querySelectorAll('.notch-avatar-portrait')) { img.src = portrait; img.hidden = false; }
      } catch { avatarCaptureFailures++; }
    }

    function setIdleFade(faded, opacityMode = 'subtle') {
      const level = opacityMode === 'invisible' ? '0.02' : opacityMode === 'ghost' ? '0.08' : opacityMode === 'dim' ? '0.42' : '0.22';
      shellEl.style.setProperty('--notch-idle-opacity', level);
      shellEl.setAttribute('data-idle-faded', faded ? 'true' : 'false');
    }

    function buildOrbitRail(projections, selectedId, pinnedId, privacyShield) {
      const rail = createEl('div', 'notch-orbit-rail', { role: 'tablist', 'aria-label': 'Actividades en Orbit' });
      rail.addEventListener('keydown', (ev) => {
        if (ev.key !== 'ArrowRight' && ev.key !== 'ArrowLeft') return;
        const buttons = [...rail.querySelectorAll('button')];
        const idx = buttons.indexOf(document.activeElement);
        if (idx < 0) return;
        const nextIdx = ev.key === 'ArrowRight' ? (idx + 1) % buttons.length : (idx - 1 + buttons.length) % buttons.length;
        buttons[nextIdx]?.focus();
        ev.preventDefault();
      });
      for (const p of projections) {
        const chip = createEl('button', 'notch-orbit-chip', {
          type: 'button',
          role: 'tab',
          'aria-selected': p.id === selectedId ? 'true' : 'false'
        });
        if (p.id === pinnedId) chip.append(icon('pin', 12));
        chip.append(createEl('span', '', { text: privacyShield && p.privacy === 'private' ? 'Privado' : p.title }));
        chip.addEventListener('click', () => handlers.onSelectActivity?.(p.id));
        rail.append(chip);
      }
      return rail;
    }

    function kindGlyph(kind) {
      return ({ timer: 'clock', media: 'media', agent: 'agents', voice: 'voice', transfer: 'portal', chat: 'chat', devpulse: 'terminal', approval: 'shield' })[kind] || 'orbit';
    }

    function buildActivityBlock(p, pinnedId, privacyShield) {
      const shielded = Boolean(privacyShield && p.privacy === 'private');
      const tone = p.status === 'awaiting_user' ? 'approval' : p.status === 'failed' ? 'error' : 'default';
      const box = createEl('article', 'notch-surface-block notch-activity-card', { 'data-tone': tone, 'data-activity-id': p.id });
      box.setAttribute('data-kind', p.kind || 'activity');
      const head = createEl('div', 'notch-row-between');
      const leftWrap = createEl('div', 'notch-activity-head');
      const emblem = createEl('span', 'notch-command-mark');
      emblem.append(icon(kindGlyph(p.kind), 16));
      const left = createEl('div', 'notch-activity-copy');
      left.append(createEl('div', 'notch-eyebrow', { text: ({ timer: 'TIEMPO', media: 'REPRODUCCIÓN', agent: 'AGENTE', voice: 'VOZ', transfer: 'TRANSFERENCIA', chat: 'CONVERSACIÓN', devpulse: 'DESARROLLO' })[p.kind] || 'ACTIVIDAD' }));
      left.append(
        createEl('div', (p.kind === 'timer' ? 'notch-timer-value' : 'notch-title-md') + (shielded ? ' notch-privacy-shield' : ''), {
          text: shielded ? 'Contenido oculto por privacidad' : p.kind === 'timer' ? (p.metric || p.title) : p.title
        }),
        createEl('div', 'notch-muted' + (shielded ? ' notch-privacy-shield' : ''), {
          text: shielded ? 'Desactiva Privacidad para mostrar detalles' : (p.subtitle || '')
        })
      );
      leftWrap.append(emblem, left);
      head.append(leftWrap);
      const rightCtrl = createEl('div', 'notch-actions-row');
      if (p.progress?.kind === 'determinate') {
        const pct = Math.round(Math.max(0, Math.min(1, p.progress.fraction)) * 100);
        rightCtrl.append(createEl('span', 'notch-primary-metric', { text: `${pct}%` }));
      }
      const isPinned = p.id === pinnedId;
      const pinBtn = createEl('button', 'notch-mode-link', {
        type: 'button',
        'aria-pressed': isPinned ? 'true' : 'false',
        title: isPinned ? 'Desfijar actividad' : 'Fijar en el carril principal',
        text: isPinned ? 'Fijada' : 'Fijar'
      });
      pinBtn.addEventListener('click', () => handlers.onTogglePin?.(isPinned ? null : p.id));
      rightCtrl.append(pinBtn);
      head.append(rightCtrl);
      box.append(head);

      if (p.progress?.kind === 'determinate') {
        const bar = createEl('div', 'notch-activity-progress', { 'aria-hidden': 'true' });
        const fill = createEl('span');
        fill.style.width = `${Math.round(Math.max(0, Math.min(1, p.progress.fraction)) * 100)}%`;
        bar.append(fill);
        box.append(bar);
      }

      const actionsRow = createEl('div', 'notch-actions-row');
      for (const act of p.actions || []) {
        const btn = createEl('button', 'notch-pill-btn', {
          type: 'button',
          text: act.label,
          ...(act.requiresApproval ? { 'data-primary': 'true' } : {}),
          ...(act.available === false ? { disabled: '' } : {}),
          ...(act.disabledReason ? { title: act.disabledReason } : {})
        });
        btn.addEventListener('click', () => handlers.onActivityAction?.(p, act));
        actionsRow.append(btn);
      }
      if (actionsRow.children.length) box.append(actionsRow);
      return box;
    }

    function buildApprovalInbox(ctx, privacyShield) {
      const op = ctx.commandOperation;
      if (!op || op.state !== 'awaiting_approval') return null;
      const box = createEl('article', 'notch-surface-block', { 'data-tone': 'approval', id: 'notch-approval-inbox' });
      const head = createEl('div', 'notch-row-between');
      head.append(
        createEl('div', 'notch-title-md', { text: 'Tu aprobación es necesaria' }),
        createEl('span', 'notch-muted', { text: op.command_id || 'comando' })
      );
      const sub = createEl('div', 'notch-muted' + (privacyShield ? ' notch-privacy-shield' : ''), {
        text: privacyShield ? 'Detalles ocultos por Privacidad' : (op.title || 'Revisa parámetros antes de aprobar.')
      });
      const row = createEl('div', 'notch-actions-row');
      const approveBtn = createEl('button', 'notch-pill-btn', {
        type: 'button',
        id: 'notch-approve-btn',
        'data-primary': 'true',
        text: 'Aprobar y ejecutar'
      });
      const rejectBtn = createEl('button', 'notch-pill-btn', {
        type: 'button',
        id: 'notch-reject-btn',
        'data-danger': 'true',
        text: 'Cancelar'
      });
      approveBtn.addEventListener('click', () => handlers.onApproveOperation?.(op));
      rejectBtn.addEventListener('click', () => handlers.onRejectOperation?.(op));
      row.append(approveBtn, rejectBtn);
      box.append(head, sub, row);
      return box;
    }

    function renderMediaView(mediaProj, ctx) {
      if (!mediaProj) {
        const empty = createEl('div', 'notch-media-empty');
        const orb = createEl('div', 'notch-media-orb');
        const portrait = createAvatarPortrait(); if (avatarPortrait) { portrait.src = avatarPortrait; portrait.hidden = false; }
        orb.append(portrait);
        empty.append(
          orb,
          createEl('div', 'notch-title-md', { text: 'Nada sonando ahora' }),
          createEl('div', 'notch-muted', { text: 'Inicia música en Windows o en AXX para controlarla desde aquí.' })
        );
        const playLocal = createEl('button', 'notch-pill-btn', { type: 'button', text: 'Reproducir en AXX' });
        playLocal.prepend(icon('play', 13));
        playLocal.addEventListener('click', () => handlers.onSubmitIntent?.('media toggle'));
        empty.append(playLocal);
        bodyEl.append(empty);
        return;
      }
      const meta = mediaProj.mediaMeta || {};
      const wrap = createEl('div', 'notch-media-stage', { id: 'notch-media-panoramic' });
      const topRow = createEl('div', 'notch-media-top');
      const art = createEl('div', 'notch-media-art', { 'data-playing': String(Boolean(meta.playing)) });
      const mediaPortrait = createAvatarPortrait();
      if (avatarPortrait) { mediaPortrait.src = avatarPortrait; mediaPortrait.hidden = false; }
      art.append(mediaPortrait);

      const info = createEl('div', 'notch-media-info');
      const shielded = Boolean(ctx.privacyShield && mediaProj.privacy === 'private');
      const titleRow = createEl('div', 'notch-media-title-row');
      const titleCol = createEl('div', 'notch-media-title-col');
      titleCol.append(
        createEl('div', 'notch-title-md' + (shielded ? ' notch-privacy-shield' : ''), {
          text: shielded ? 'Reproducción protegida' : mediaProj.title
        }),
        createEl('div', 'notch-muted' + (shielded ? ' notch-privacy-shield' : ''), {
          text: shielded ? 'Audio activo' : mediaProj.subtitle || 'Sesión de Windows'
        })
      );
      titleRow.append(titleCol);

      const statusBadge = createEl('div', 'notch-media-status', { 'data-playing': String(Boolean(meta.playing)) });
      if (meta.audioAvailable || meta.playing) {
        const eq = createEl('span', 'notch-peak-mini', { 'aria-hidden': 'true' });
        const pVal = meta.audioAvailable ? Math.max(0.14, Math.min(1, meta.peak || 0)) : 0.16;
        for (let i = 0; i < 4; i++) {
          const bar = createEl('i');
          bar.style.setProperty('--bar-h', String(meta.playing ? Math.max(0.2, pVal * (1 - i * 0.14)) : 0.12));
          eq.append(bar);
        }
        statusBadge.append(eq);
      }
      statusBadge.append(createEl('span', '', { text: meta.playing ? 'En vivo' : 'En pausa' }));
      titleRow.append(statusBadge);
      info.append(titleRow);

      if (meta.sessions && meta.sessions.length > 1) {
        const sessionsBar = createEl('div', 'notch-media-sessions', { id: 'notch-media-session-select', role: 'tablist', 'aria-label': 'Cambiar sesión multimedia' });
        for (const s of meta.sessions.slice(0, 3)) {
          const label = String(s.app || s.title || 'Sesión').replace(/\.exe$/i, '');
          const chip = createEl('button', 'notch-media-session-chip', {
            type: 'button',
            'aria-selected': String(s.id === meta.selectedId || (!meta.selectedId && s === meta.sessions[0])),
            title: s.title || label
          });
          if (s.playing) chip.append(createEl('span', 'notch-media-session-dot'));
          chip.append(document.createTextNode(label));
          chip.addEventListener('click', () => handlers.onSelectMediaSession?.(s.id));
          sessionsBar.append(chip);
        }
        info.append(sessionsBar);
      }

      topRow.append(art, info);
      wrap.append(topRow);

      if (meta.duration > 0) {
        const timelineWrap = createEl('div', 'notch-media-timeline');
        const pct = Math.max(0, Math.min(100, (100 * (meta.time || 0)) / Math.max(1, meta.duration)));
        const seek = createEl('input', 'notch-seek-slider', {
          type: 'range',
          min: '0',
          max: String(Math.round(meta.duration)),
          value: String(Math.round(meta.time || 0)),
          'aria-label': 'Posición multimedia',
          ...(meta.canSeek ? {} : { disabled: '' })
        });
        seek.style.setProperty('--seek-pct', `${pct.toFixed(1)}%`);
        if (meta.canSeek) {
          seek.addEventListener('change', () => handlers.onMediaSeek?.(Number(seek.value)));
        }
        const parts = String(mediaProj.metric || '').split('/').map(s => s.trim());
        const timeRow = createEl('div', 'notch-media-time');
        if (parts.length === 2) {
          timeRow.append(
            createEl('span', '', { 'data-media-time': '', text: parts[0] }),
            createEl('span', '', { text: parts[1] })
          );
        } else {
          timeRow.append(createEl('span', '', { 'data-media-time': '', text: mediaProj.metric || '' }));
        }
        timelineWrap.append(seek, timeRow);
        wrap.append(timelineWrap);
      }

      const ctrl = createEl('div', 'notch-media-controls');
      const [prevAct, toggleAct, nextAct] = mediaProj.actions || [];
      for (const [act, glyph] of [[prevAct, 'previous'], [toggleAct, meta.playing ? 'pause' : 'play'], [nextAct, 'next']]) {
        if (!act) continue;
        const btn = createEl('button', 'notch-media-btn', {
          type: 'button',
          'aria-label': act.label,
          title: act.disabledReason || act.label,
          ...(glyph === 'play' || glyph === 'pause' ? { 'data-primary': 'true' } : {}),
          ...(act.available === false ? { disabled: '' } : {})
        });
        btn.append(icon(glyph, glyph === 'play' || glyph === 'pause' ? 18 : 16));
        btn.addEventListener('click', () => handlers.onActivityAction?.(mediaProj, act));
        ctrl.append(btn);
      }
      wrap.append(ctrl);
      bodyEl.append(wrap);
    }

    function intentIconName(item) {
      const key = `${item.id || ''} ${item.title || ''} ${item.badge || ''}`.toLowerCase();
      if (/timer|temporiz/.test(key)) return 'clock';
      if (/focus|concentr/.test(key)) return 'moon';
      if (/media|reproduc|música|musica|spotify/.test(key)) return 'media';
      if (/voice|voz|dict/.test(key)) return 'voice';
      if (/magic|pen|anotar|captur/.test(key)) return 'pen';
      if (/telemetry|recurso|cpu|ram|sistema/.test(key)) return 'cpu';
      if (/chat|hilo|convers/.test(key)) return 'chat';
      if (/agent|studio|code/.test(key)) return 'agents';
      return 'terminal';
    }

    let sharedAudioCtx = null;
    function getAudioCtx() {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return null;
      if (!sharedAudioCtx || sharedAudioCtx.state === 'closed') sharedAudioCtx = new AudioCtx();
      if (sharedAudioCtx.state === 'suspended') void sharedAudioCtx.resume().catch(() => {});
      return sharedAudioCtx;
    }

    function playTactileChime(kind = 'click', force = false) {
      try {
        if (!force && appearancePrefs.soundEffectsEnabled === false) return;
        const ctx = getAudioCtx();
        if (!ctx) return;
        const profile = appearancePrefs.soundProfile || 'crystal';
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        const now = ctx.currentTime;
        const baseWave = profile === 'synth' ? 'triangle' : profile === 'mechanical' ? 'square' : 'sine';
        const freqMul = profile === 'soft' ? 0.78 : profile === 'mechanical' ? 1.35 : profile === 'synth' ? 1.12 : 1;
        const vol = profile === 'mechanical' ? 0.014 : profile === 'soft' ? 0.022 : 0.03;
        osc.type = baseWave;
        if (kind === 'dock') {
          osc.frequency.setValueAtTime(520 * freqMul, now);
          osc.frequency.exponentialRampToValueAtTime(840 * freqMul, now + 0.075);
          gain.gain.setValueAtTime(vol, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.09);
          osc.start(now);
          osc.stop(now + 0.09);
        } else if (kind === 'undock') {
          osc.frequency.setValueAtTime(760 * freqMul, now);
          osc.frequency.exponentialRampToValueAtTime(420 * freqMul, now + 0.075);
          gain.gain.setValueAtTime(vol * 0.9, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.085);
          osc.start(now);
          osc.stop(now + 0.085);
        } else {
          osc.frequency.setValueAtTime(880 * freqMul, now);
          osc.frequency.exponentialRampToValueAtTime(660 * freqMul, now + 0.032);
          gain.gain.setValueAtTime(vol * 0.75, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.038);
          osc.start(now);
          osc.stop(now + 0.038);
        }
      } catch {}
    }

    function renderIntentView(ctx) {
      const form = createEl('form', 'notch-intent-bar', { id: 'notch-intent-form' });
      const input = createEl('input', 'notch-intent-input', {
        type: 'text',
        id: 'notch-intent-input',
        autocomplete: 'off',
        value: ctx.intentQuery || '',
        placeholder: 'Buscar acciones o escribir una orden…',
        'aria-label': 'Comando o intención para AXX',
        role: 'combobox', 'aria-autocomplete': 'list', 'aria-controls': 'notch-intent-results', 'aria-expanded': 'true'
      });
      intentInputRef = input;
      const submit = createEl('button', 'notch-pill-btn', {
        type: 'submit',
        'data-primary': 'true',
        id: 'notch-intent-submit',
        text: 'Ir'
      });
      form.append(icon('search', 16), input, createEl('kbd', 'notch-kbd', { text: '↵' }), submit);
      bodyEl.append(form);

      let activeCategory = ctx.intentCategory || 'all';
      const filterChips = createEl('div', 'notch-filter-chips', { role: 'tablist', 'aria-label': 'Filtrar por categoría' });
      for (const [catId, catLabel] of [['all', 'Todos'], ['system', 'Sistema'], ['media', 'Multimedia'], ['voice', 'Voz'], ['agents', 'Agentes']]) {
        const chip = createEl('button', 'notch-filter-chip', { type: 'button', text: catLabel, 'data-cat': catId, 'aria-pressed': String(catId === activeCategory) });
        chip.addEventListener('click', () => {
          activeCategory = catId;
          playTactileChime('click');
          for (const c of filterChips.children) c.setAttribute('aria-pressed', String(c === chip));
          handlers.onIntentQueryChange?.(input.value, rebuildResults, activeCategory);
        });
        filterChips.append(chip);
      }
      bodyEl.append(filterChips);

      const resultsWrap = createEl('div', 'notch-intent-results', { id: 'notch-intent-results', role: 'listbox', 'aria-label': 'Capacidades compatibles' });
      const candidates = (ctx.intentResults || []).slice(0, 4);
      const rebuildResults = (items) => {
        resultsWrap.replaceChildren();
        items.slice(0, 4).forEach((item, idx) => {
          const btn = createEl('button', 'notch-intent-item', {
            type: 'button',
            role: 'option',
            'data-active': idx === selectedIntentIdx ? 'true' : 'false',
            'aria-selected': String(idx === selectedIntentIdx),
            'aria-disabled': String(item.available === false),
            id: `notch-intent-option-${idx}`
          });
          const mark = createEl('span', 'notch-command-mark');
          mark.append(icon(intentIconName(item), 15));
          const left = createEl('span', 'notch-command-label', { text: item.title || item.id });
          const right = createEl('span', 'notch-badge-chip', { text: item.badge || (item.available === false ? 'Bloqueado' : 'Local') });
          btn.append(mark, left, right);
          btn.addEventListener('click', () => {
            if (item.available === false) return;
            playTactileChime('click');
            if (item.hasParams) handlers.onSelectIntentCommand?.(item);
            else handlers.onRunIntentItem?.(item);
          });
          resultsWrap.append(btn);
        });
        input.setAttribute('aria-activedescendant', items.length ? `notch-intent-option-${Math.min(selectedIntentIdx, items.length - 1)}` : '');
        if (!items.length) resultsWrap.append(createEl('div', 'notch-empty-inline', { text: 'Sin coincidencias exactas. Pulsa Ir para enviarlo a AXX.' }));
      };
      rebuildResults(candidates);

      input.addEventListener('input', () => {
        selectedIntentIdx = 0;
        handlers.onIntentQueryChange?.(input.value, rebuildResults, activeCategory);
      });
      input.addEventListener('keydown', (ev) => {
        const rows = [...resultsWrap.querySelectorAll('.notch-intent-item')];
        if (ev.key === 'ArrowDown' && rows.length) {
          selectedIntentIdx = (selectedIntentIdx + 1) % rows.length;
          rows.forEach((r, i) => { r.setAttribute('data-active', String(i === selectedIntentIdx)); r.setAttribute('aria-selected', String(i === selectedIntentIdx)); });
          input.setAttribute('aria-activedescendant', rows[selectedIntentIdx].id);
          rows[selectedIntentIdx].scrollIntoView({ block: 'nearest' });
          ev.preventDefault();
        } else if (ev.key === 'ArrowUp' && rows.length) {
          selectedIntentIdx = (selectedIntentIdx - 1 + rows.length) % rows.length;
          rows.forEach((r, i) => { r.setAttribute('data-active', String(i === selectedIntentIdx)); r.setAttribute('aria-selected', String(i === selectedIntentIdx)); });
          input.setAttribute('aria-activedescendant', rows[selectedIntentIdx].id);
          rows[selectedIntentIdx].scrollIntoView({ block: 'nearest' });
          ev.preventDefault();
        }
      });
      form.addEventListener('submit', (ev) => {
        ev.preventDefault();
        const val = input.value.trim();
        if (!val) return;
        const selected = resultsWrap.querySelectorAll('.notch-intent-item')[selectedIntentIdx];
        if (selected) { selected.click(); return; }
        handlers.onSubmitIntent?.(val);
        input.value = '';
      });
      bodyEl.append(resultsWrap);

      if (ctx.lastReceipt) {
        const rec = createEl('div', 'notch-surface-block', {
          id: 'notch-receipt-lens',
          'data-tone': ctx.lastReceipt.state === 'failed' ? 'error' : 'default'
        });
        const recHead = createEl('div', 'notch-row-between');
        recHead.append(createEl('span', 'notch-title-md', { text: 'Receipt Lens' }));
        rec.append(recHead, createEl('div', 'notch-muted', { text: ctx.lastReceipt.summary || ctx.lastReceipt.error || ctx.lastReceipt.command_id || 'Operación registrada' }));
        bodyEl.append(rec);
      }

      const passport = createEl('div', 'notch-capability-ribbon', { id: 'notch-capability-passport', 'aria-label': 'Conexiones y capacidades reales' });
      for (const [label, ok] of [
        ['Backend', Boolean(ctx.backendReady)],
        ['LLM', Boolean(ctx.modelConnected)],
        ['Catálogo', Boolean(ctx.hasCommands)],
        ['Audio WinRT', Boolean(ctx.hasSystemMedia)]
      ]) {
        const pill = createEl('span', 'notch-cap-pill', { 'data-ok': String(ok) });
        pill.append(createEl('i', 'notch-cap-dot', { 'aria-hidden': 'true' }), createEl('span', '', { text: label }));
        passport.append(pill);
      }
      bodyEl.append(passport);
    }

    function portalItemIcon(item) {
      if (item.kind === 'link') return 'link';
      if (/\.(png|jpe?g|webp|gif|svg)$/i.test(item.name || '')) return 'image';
      return 'file';
    }

    function renderPortalView(state, ctx) {
      const zone = createEl('div', 'notch-portal-stage', {
        id: 'notch-portal-zone',
        'data-active': state.interaction === 'dragActive' || state.interaction === 'dragEnter' ? 'true' : 'false'
      });
      if (ctx.portalReceipt) {
        zone.dataset.received = 'true';
        const badge = createEl('div', 'notch-portal-receipt', { role: 'status' });
        badge.append(icon('check', 15), createEl('span', '', { text: ctx.portalReceipt }));
        zone.append(badge);
      }
      const head = createEl('div', 'notch-row-between');
      head.append(
        createEl('span', 'notch-title-md', {
          text: ctx.portalItems?.length ? `Smart Shelf (${ctx.portalItems.length})` : 'Portal · Recepción de contenido'
        }),
        createEl('span', 'notch-muted', { text: 'Archivos, imágenes, PDF o texto' })
      );
      zone.append(head);

      const empty = createEl('div', 'notch-drop-invitation', { 'data-compact': String(Boolean(ctx.portalItems?.length)) });
      const iconPlate = createEl('span', 'notch-drop-halo');
      iconPlate.append(icon('portal', ctx.portalItems?.length ? 18 : 24));
      empty.append(
        iconPlate,
        createEl('strong', '', { text: ctx.portalItems?.length ? 'Suelta o añade más elementos' : 'Suelta aquí tus archivos o imágenes' }),
        createEl('span', 'notch-muted', { text: 'Se ilumina y confirma al recibir · arrastra o elige desde tu equipo' })
      );
      zone.append(empty);

      if (ctx.portalItems?.length) {
        const list = createEl('div', 'notch-shelf-list');
        for (const item of ctx.portalItems) {
          const row = createEl('div', 'notch-shelf-item');
          const left = createEl('div', 'notch-shelf-item-main');
          const mark = createEl('span', 'notch-command-mark');
          mark.append(icon(portalItemIcon(item), 15));
          left.append(mark, createEl('span', '', {
            text: `${item.name || 'Elemento'} · ${item.kind === 'text' ? 'Texto' : item.kind === 'link' ? 'Enlace' : formatBytes(item.size)}`
          }));
          const rm = createEl('button', 'notch-mode-link', { type: 'button', text: 'Quitar' });
          rm.addEventListener('click', () => handlers.onPortalRemove?.(item.id));
          row.append(left, rm);
          list.append(row);
        }
        zone.append(list);
      }

      const paste = createEl('form', 'notch-portal-paste');
      const link = createEl('input', 'notch-field', { type: 'text', placeholder: 'Pega un enlace o un texto…', 'aria-label': 'Enlace o texto para Archivos', maxlength: '20000' });
      const add = createEl('button', 'notch-pill-btn', { type: 'submit', text: 'Añadir' });
      paste.append(link, add);
      paste.addEventListener('submit', ev => {
        ev.preventDefault();
        if (link.value.trim()) {
          handlers.onDrop?.({ text: link.value, files: [] });
          link.value = '';
        }
      });
      zone.append(paste);

      const actions = createEl('div', 'notch-portal-toolbar');
      const pickBtn = createEl('button', 'notch-pill-btn', {
        type: 'button',
        id: 'notch-portal-pick-btn',
        'data-primary': 'true',
        text: 'Elegir archivo…'
      });
      const fileInput = createEl('input', 'notch-sr-only', {
        type: 'file',
        multiple: '',
        id: 'notch-portal-file-input',
        'aria-label': 'Seleccionar archivos para Smart Shelf'
      });
      pickBtn.addEventListener('click', () => fileInput.click());
      fileInput.addEventListener('change', () => {
        const files = Array.from(fileInput.files || []);
        if (files.length) handlers.onDrop?.({ files, text: '' });
        fileInput.value = '';
      });
      actions.append(pickBtn, fileInput);

      if (!window.Axx?.companion?.audio?.enabled && window.Axx?.experience?.enableSounds) {
        const sound = createEl('button', 'notch-pill-btn', { type: 'button', text: 'Activar sonidos', 'aria-label': 'Activar los sonidos de AXX' });
        sound.prepend(icon('volume', 14));
        sound.addEventListener('click', async () => {
          await window.Axx.experience.enableSounds();
          handlers.onPreferencesChange?.({ soundEffectsEnabled: true });
          sound.textContent = 'Sonidos activos';
          sound.disabled = true;
        });
        actions.append(sound);
      }

      if (ctx.portalItems?.length) {
        const toChat = createEl('button', 'notch-pill-btn', { type: 'button', id: 'notch-portal-to-chat', text: 'Preparar en chat' });
        toChat.addEventListener('click', () => handlers.onPortalAction?.('chat'));
        actions.append(toChat);

        if (ctx.hasConverter && ctx.portalItems.some(i => /\.(png|jpe?g|pdf)$/i.test(i.name || ''))) {
          const toConv = createEl('button', 'notch-pill-btn', { type: 'button', id: 'notch-portal-to-converter', text: 'Convertir' });
          toConv.addEventListener('click', () => handlers.onPortalAction?.('converter'));
          actions.append(toConv);
        }
        if (ctx.hasTransfer) {
          const toPhone = createEl('button', 'notch-pill-btn', { type: 'button', id: 'notch-portal-to-transfer', text: 'Transferir' });
          toPhone.addEventListener('click', () => handlers.onPortalAction?.('transfer'));
          actions.append(toPhone);
        }
        const clearBtn = createEl('button', 'notch-pill-btn', { type: 'button', id: 'notch-portal-clear', 'data-danger': 'true', text: 'Vaciar' });
        clearBtn.addEventListener('click', () => handlers.onPortalAction?.('clear'));
        actions.append(clearBtn);
      }
      zone.append(actions);
      bodyEl.append(zone);
    }

    function renderAgentsView(ctx) {
      const agents = ctx.projections.filter(p => p.kind === 'agent' || p.kind === 'devpulse');
      if (!agents.length) {
        const empty = createEl('div', 'notch-surface-block notch-agent-showcase');
        const head = createEl('div', 'notch-row-between');
        const emblem = createEl('span', 'notch-command-mark notch-mark-lg');
        emblem.append(icon('agents', 20));
        const copy = createEl('div');
        copy.append(
          createEl('div', 'notch-title-md', { text: 'Axx Code Studio listo' }),
          createEl('div', 'notch-muted', { text: 'Supervisa subtareas, archivos editados, pruebas y aprobaciones en tiempo real.' })
        );
        head.append(emblem, copy);
        const btn = createEl('button', 'notch-pill-btn', { type: 'button', 'data-primary': 'true', text: 'Abrir Axx Code Studio' });
        btn.prepend(icon('stage', 15));
        btn.addEventListener('click', () => handlers.onOpenCodeStudio?.());
        empty.append(head, btn);
        bodyEl.append(empty);
        return;
      }
      for (const a of agents) {
        const block = buildActivityBlock(a, ctx.pinnedActivityId, ctx.privacyShield);
        if (Array.isArray(a.agentEvents) && a.agentEvents.length) {
          const tl = createEl('div', 'notch-agent-timeline');
          for (const ev of a.agentEvents) {
            const row = createEl('div', 'notch-agent-event');
            row.dataset.status = ev.status || '';
            row.append(
              createEl('span', '', { text: ev.tool || ev.phase || ev.type || 'evento' }),
              createEl('span', 'notch-badge-chip', { text: `#${ev.seq} · ${ev.status || ''}` })
            );
            tl.append(row);
          }
          block.append(tl);
        }
        bodyEl.append(block);
      }
    }

    function renderResourcesView(ctx) {
      const box = createEl('div', 'notch-surface-block', { id: 'notch-resource-lens' });
      const head = createEl('div', 'notch-row-between');
      head.append(
        createEl('span', 'notch-title-md', { text: 'Tu equipo, de un vistazo' }),
        createEl('span', 'notch-badge-chip', { text: ctx.telemetryPending ? 'Midiendo…' : ctx.telemetry?.updatedAt ? 'Medido ' + new Date(ctx.telemetry.updatedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Sin medir' })
      );
      const t = ctx.telemetry;
      box.append(head);

      const metrics = createEl('div', 'notch-resource-metrics');
      const freeDiskPct = t?.disk_total_gb ? (100 * t.disk_free_gb / t.disk_total_gb) : null;
      for (const [label, value, unit, ringPct, detail] of [
        ['CPU', t?.cpu_percent, '%', t?.cpu_percent, t?.cpu_count ? `${t.cpu_count} procesadores lógicos` : 'Carga del procesador'],
        ['RAM', t?.memory_percent, '%', t?.memory_percent, t?.memory_total_mb ? `${(t.memory_used_mb / 1024).toFixed(1)} de ${(t.memory_total_mb / 1024).toFixed(1)} GB en uso` : 'Memoria del equipo'],
        ['Disco libre', t?.disk_free_gb, 'GB', freeDiskPct, t?.disk_total_gb ? `de ${Math.round(t.disk_total_gb)} GB totales` : 'Almacenamiento local']
      ]) {
        const metric = createEl('div', 'notch-resource-metric');
        const valid = typeof value === 'number' && Number.isFinite(value);
        const tone = Number.isFinite(ringPct) && (label === 'Disco libre' ? ringPct < 15 : ringPct > 85) ? 'warning' : 'accent';
        const visual = createEl('div', 'notch-resource-visual');
        visual.append(createResourceRing(ringPct, tone));
        const readout = createEl('div', 'notch-resource-readout');
        readout.append(createEl('strong', '', { text: valid ? `${Math.round(value * 10) / 10}` : '—' }), createEl('span', 'notch-muted', { text: unit }));
        visual.append(readout);
        const stateText = !valid ? 'Pendiente' : tone === 'warning' ? 'Atención' : (label === 'Disco libre' ? ringPct > 35 : ringPct < 60) ? 'Óptimo' : 'Activo';
        const stateBadge = createEl('span', 'notch-resource-pill', { 'data-tone': tone, text: stateText });
        metric.append(createEl('span', 'notch-eyebrow', { text: label }), visual, stateBadge, createEl('small', 'notch-muted', { text: detail }));
        metrics.append(metric);
      }
      box.append(metrics);
      if (!t) box.append(createEl('div', 'notch-muted', { text: 'Pulsa «Medir este PC» para leer CPU, RAM y disco reales.' }));
      if (ctx.telemetryError) box.append(createEl('div', 'notch-muted', { role: 'status', text: ctx.telemetryError }));

      const btns = createEl('div', 'notch-actions-row');
      const pollBtn = createEl('button', 'notch-pill-btn', {
        type: 'button',
        id: 'notch-resource-poll-btn',
        'data-primary': 'true',
        text: ctx.telemetryPending ? 'Midiendo…' : t ? 'Actualizar medición' : 'Medir este PC',
        ...(ctx.backendReady && !ctx.telemetryPending ? {} : { disabled: '' })
      });
      pollBtn.addEventListener('click', () => handlers.onPollTelemetry?.());

      const freezeBtn = createEl('button', 'notch-pill-btn', {
        type: 'button',
        id: 'notch-context-freeze-btn',
        'aria-pressed': String(Boolean(ctx.contextFrozen)),
        text: ctx.contextFrozen ? 'Contexto pausado' : 'Pausar contexto'
      });
      freezeBtn.addEventListener('click', () => handlers.onToggleContextFreeze?.());

      const privBtn = createEl('button', 'notch-pill-btn', {
        type: 'button',
        id: 'notch-privacy-btn',
        'aria-pressed': String(Boolean(ctx.privacyShield)),
        text: ctx.privacyShield ? 'Privacidad activa' : 'Ocultar datos privados'
      });
      privBtn.prepend(icon('shield', 14));
      privBtn.addEventListener('click', () => handlers.onTogglePrivacy?.());

      btns.append(pollBtn, freezeBtn, privBtn);
      box.append(btns);
      bodyEl.append(box);
    }

    function renderVoiceView(ctx) {
      const voice = ctx.projections.find(p => p.kind === 'voice');
      const view = createEl('div', 'notch-voice-studio');
      const mark = createEl('div', 'notch-voice-mark', { 'data-listening': String(Boolean(voice)) });
      const voicePortrait = createAvatarPortrait();
      if (avatarPortrait) { voicePortrait.src = avatarPortrait; voicePortrait.hidden = false; }
      mark.append(createEl('span', 'notch-voice-ring', { 'aria-hidden': 'true' }), voicePortrait);
      view.append(
        mark,
        createEl('div', 'notch-title-md', { text: voice ? voice.title : 'Habla cuando estés listo' }),
        createEl('p', 'notch-muted', { text: voice?.subtitle || 'Activa Voz para dictar, revisar y conversar desde el mismo entorno.' })
      );
      if (voice) view.append(buildActivityBlock(voice, ctx.pinnedActivityId, ctx.privacyShield));
      else {
        const start = createEl('button', 'notch-pill-btn', { type: 'button', 'data-primary': 'true', text: 'Abrir Voz en Stage' });
        start.prepend(icon('voice', 15));
        start.addEventListener('click', () => handlers.onSubmitIntent?.('voice'));
        view.append(start);
      }
      bodyEl.append(view);
    }

    function renderRecallView(ctx) {
      const box = createEl('div', 'notch-surface-block', { id: 'notch-recall-threads' });
      box.append(createEl('div', 'notch-title-md', { text: 'Tus últimas conversaciones' }));
      const threads = ctx.recall?.threads || [];
      if (!threads.length) {
        box.append(createEl('div', 'notch-muted', { text: 'Tus conversaciones aparecerán aquí cuando el espacio de chat esté conectado.' }));
      } else {
        for (const th of threads) {
          const btn = createEl('button', 'notch-intent-item notch-recall-card', {
            type: 'button',
            'data-active': String(Boolean(th.active))
          });
          const mark = createEl('span', 'notch-command-mark');
          mark.append(icon('chat', 15));
          const label = createEl('span', 'notch-command-label', { text: ctx.privacyShield ? 'Hilo protegido' : th.title });
          const badge = createEl('span', 'notch-badge-chip', { text: th.active ? 'En vivo' : 'Abrir' });
          btn.append(mark, label, badge);
          btn.addEventListener('click', () => handlers.onOpenThread?.(th.id));
          box.append(btn);
        }
      }
      if (ctx.offlineQueue?.length) {
        const qBox = createEl('div', 'notch-surface-block', { id: 'notch-offline-queue' });
        qBox.append(createEl('div', 'notch-title-md', { text: `Safe Offline Queue (${ctx.offlineQueue.length})` }));
        for (const item of ctx.offlineQueue) {
          const row = createEl('div', 'notch-row-between');
          row.append(createEl('span', 'notch-muted', { text: item.text }));
          const replay = createEl('button', 'notch-pill-btn', {
            type: 'button',
            text: 'Reenviar ahora',
            ...(ctx.backendReady ? {} : { disabled: '' })
          });
          replay.addEventListener('click', () => handlers.onRetryOfflineItem?.(item.id));
          row.append(replay);
          qBox.append(row);
        }
        bodyEl.append(qBox);
      }
      bodyEl.append(box);
    }

    function renderBody(state, ctx) {
      if (state.content !== 'chat' || state.size !== 'expanded') chatSurface?.hide();
      bodyEl.innerHTML = '';
      if (state.size === 'compact' || state.size === 'ambient' || state.size === 'stage') return;

      if (state.size === 'expanded') {
        const meta = VIEW_META[state.content] || VIEW_META.orbit;
        const intro = createEl('div', 'notch-view-heading');
        if (state.content === 'orbit' || state.content === 'home') {
          const hour = new Date().getHours();
          const greeting = hour < 12 ? 'BUENOS DÍAS' : hour < 19 ? 'BUENAS TARDES' : 'BUENAS NOCHES';
          const statusBar = createEl('div', 'notch-hero-status');
          statusBar.append(
            createEl('span', 'notch-live-dot', { 'data-ok': String(Boolean(ctx.backendReady)), 'aria-hidden': 'true' }),
            createEl('span', 'notch-eyebrow', { text: `${greeting} · AXX ACTIVO` })
          );
          intro.append(statusBar, createEl('h2', '', { text: meta[0] }), createEl('p', 'notch-muted', { text: meta[1] }));
          intro.classList.add('notch-heading-identity');
          const stage = createEl('div', 'notch-avatar-stage notch-hero-pedestal');
          const portrait = createAvatarPortrait();
          if (avatarPortrait) { portrait.src = avatarPortrait; portrait.hidden = false; }
          stage.append(portrait);
          intro.append(stage);
        } else {
          intro.append(
            createEl('span', 'notch-eyebrow', { text: 'AXX · ' + (MODE_LINKS.find(m => m.id === state.content)?.label || 'TU ESPACIO').toLocaleUpperCase() }),
            createEl('h2', '', { text: meta[0] }),
            createEl('p', 'notch-muted', { text: meta[1] })
          );
        }
        bodyEl.append(intro);
      }

      if (state.content === 'chat') {
        if (!chatSurface && window.Axx?.notchChat) chatSurface = window.Axx.notchChat.createSurface();
        if (chatSurface) chatSurface.show(bodyEl);
        else bodyEl.append(createEl('p', 'notch-muted', { text: 'No se pudo cargar el acceso a tus chats. Vuelve a abrir AXX.' }));
      } else if (state.content === 'media') {
        const mediaProj = ctx.projections.find(p => p.kind === 'media') || null;
        renderMediaView(mediaProj, ctx);
      } else if (state.content === 'portal') {
        renderPortalView(state, ctx);
      } else if (state.content === 'intent') {
        renderIntentView(ctx);
      } else if (state.content === 'agents') {
        renderAgentsView(ctx);
      } else if (state.content === 'voice') {
        renderVoiceView(ctx);
      } else if (state.content === 'resources') {
        renderResourcesView(ctx);
      } else if (state.content === 'recall') {
        renderRecallView(ctx);
      } else if (state.content === 'parallel') {
        if (!ctx.projections.length) {
          bodyEl.append(createEl('div', 'notch-surface-block', { text: 'Sin actividades concurrentes en curso.' }));
        } else {
          const grid = createEl('div', 'notch-parallel-lanes');
          for (const p of ctx.projections) grid.append(buildActivityBlock(p, ctx.pinnedActivityId, ctx.privacyShield));
          bodyEl.append(grid);
        }
      } else {
        if (ctx.projections.length > 0) {
          if (state.size === 'expanded') {
            bodyEl.append(buildOrbitRail(ctx.projections, state.selectedActivityId || ctx.projections[0].id, ctx.pinnedActivityId, ctx.privacyShield));
          }
          const active = ctx.projections.find(p => p.id === state.selectedActivityId) || ctx.projections[0];
          if (active?.kind === 'media' && state.size === 'peek') {
            renderMediaView(active, ctx);
          } else if (active) {
            bodyEl.append(buildActivityBlock(active, ctx.pinnedActivityId, ctx.privacyShield));
          }
        } else {
          const minimal = createEl('div', 'notch-home');
          const row = createEl('div', 'notch-quick-actions');
          const sb = createEl('button', 'notch-quick-action notch-quick-primary', { type: 'button' });
          const primaryTop = createEl('div', 'notch-quick-head');
          const tagRow = createEl('div', 'notch-hero-tags');
          tagRow.append(
            createEl('span', 'notch-action-kicker', { text: 'CHAT DIRECTO' }),
            createEl('span', 'notch-hero-sep', { text: '·' }),
            createEl('span', 'notch-muted', { text: 'Codex, Claude y Antigravity' })
          );
          const arrowPlate = createEl('span', 'notch-arrow-orb');
          arrowPlate.append(icon('arrowUpRight', 15));
          primaryTop.append(tagRow, arrowPlate);
          sb.append(primaryTop, createEl('strong', '', { text: 'Abrir mis chats' }), createEl('span', 'notch-muted', { text: 'Continúa tu proyecto y conversación sin cambiar de ventana.' }));
          sb.addEventListener('click', () => { playTactileChime('click'); handlers.onSelectContent?.('chat'); });
          row.append(sb);

          for (const [id, lbl, subtitle, shortcut] of [
            ['intent', 'Acciones', 'Comandos y herramientas', '⌘K'],
            ['portal', 'Archivos', 'Soltar, pegar y enviar', 'Drop']
          ]) {
            const b = createEl('button', 'notch-quick-action', { type: 'button', 'data-tile': id });
            const tileHead = createEl('div', 'notch-quick-head');
            const cap = createEl('span', 'notch-command-mark notch-mark-minimal');
            cap.append(icon(id, 17));
            tileHead.append(cap, createEl('span', 'notch-hint-quiet', { text: shortcut }));
            b.append(tileHead, createEl('strong', '', { text: lbl }), createEl('span', 'notch-muted', { text: subtitle }));
            b.addEventListener('click', () => { playTactileChime('click'); handlers.onSelectContent?.(id); });
            row.append(b);
          }
          minimal.append(row);

          if (state.size === 'expanded') {
            const quickStrip = createEl('div', 'notch-mini-strip');
            for (const [id, label] of [['media', 'Música'], ['voice', 'Voz'], ['agents', 'Agentes'], ['resources', 'Sistema']]) {
              const chip = createEl('button', 'notch-mini-pill', { type: 'button', 'data-mod': id });
              chip.append(icon(id, 14), createEl('span', '', { text: label }));
              chip.addEventListener('click', () => { playTactileChime('click'); handlers.onSelectContent?.(id); });
              quickStrip.append(chip);
            }
            minimal.append(quickStrip);
          }
          bodyEl.append(minimal);
        }
      }

      if (state.size === 'expanded') {
        footerEl.innerHTML = '';
        const modes = createEl('nav', 'notch-mode-dots', { 'aria-label': 'Cambiar superficie contextual' });
        for (const m of MODE_LINKS.filter(m => ['orbit', 'intent', 'portal'].includes(m.id))) {
          const btn = createEl('button', 'notch-mode-link', {
            type: 'button',
            'aria-pressed': state.content === m.id ? 'true' : 'false'
          });
          btn.append(icon(m.id, 13), createEl('span', '', { text: m.label }));
          btn.addEventListener('click', () => handlers.onSelectContent?.(m.id));
          modes.append(btn);
        }
        const more = createEl('select', 'notch-view-select', { 'aria-label': 'Más apartados', id: 'notch-view-select' });
        more.add(new Option('Más', ''));
        for (const m of MODE_LINKS.filter(m => !['orbit', 'intent', 'portal'].includes(m.id))) more.add(new Option(m.label, m.id));
        more.add(new Option('Espacio completo', 'stage'));
        more.value = [...more.options].some(o => o.value === state.content) ? state.content : '';
        more.addEventListener('change', () => { if (more.value === 'stage') handlers.onToggleStage?.(); else if (more.value) handlers.onSelectContent?.(more.value); });
        more.hidden = true;
        const moreHost = createEl('div', 'notch-more-host');
        const moreButton = createEl('button', 'notch-mode-link', { type: 'button', text: 'Más', 'aria-expanded': 'false', 'aria-haspopup': 'menu', id: 'notch-more-btn' });
        const menu = createEl('div', 'notch-more-menu', { role: 'menu', 'aria-label': 'Más apartados', hidden: '' });
        const closeMenu = () => { menu.hidden = true; moreButton.setAttribute('aria-expanded', 'false'); };
        for (const option of [...MODE_LINKS.filter(m => !['orbit', 'intent', 'portal'].includes(m.id)), { id: 'stage', label: 'Espacio completo', hint: 'Axx Code Studio y sesión amplia' }]) {
          const item = createEl('button', 'notch-more-item', { type: 'button', role: 'menuitem', 'data-current': String(state.content === option.id), 'data-wide': String(option.id === 'stage') });
          const mark = createEl('span', 'notch-command-mark');
          mark.append(icon(option.id, 16));
          const copy = createEl('span', 'notch-more-copy');
          copy.append(createEl('strong', '', { text: option.label }), createEl('small', 'notch-muted', { text: option.hint || '' }));
          item.append(mark, copy);
          item.addEventListener('click', () => { closeMenu(); more.value = option.id; more.dispatchEvent(new Event('change')); });
          menu.append(item);
        }
        moreButton.addEventListener('click', () => { menu.hidden = !menu.hidden; moreButton.setAttribute('aria-expanded', String(!menu.hidden)); if (!menu.hidden) menu.querySelector('button')?.focus(); });
        moreHost.addEventListener('focusout', event => { if (!moreHost.contains(event.relatedTarget)) closeMenu(); });
        moreHost.addEventListener('keydown', event => {
          if (event.key === 'Escape' && !menu.hidden) { event.preventDefault(); event.stopPropagation(); closeMenu(); moreButton.focus(); }
          if (!menu.hidden && ['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) { event.preventDefault(); const items = [...menu.querySelectorAll('button')]; const index = items.indexOf(document.activeElement); items[event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus(); }
        });
        moreHost.append(moreButton, menu); modes.append(more, moreHost);

        const stageBtn = createEl('button', 'notch-mode-link', {
          type: 'button',
          id: 'notch-direct-chat-btn',
          'aria-label': state.stageOpen ? 'Cerrar conversación' : 'Abrir conversación',
          title: 'Abrir conversación',
          'aria-pressed': state.content === 'chat' ? 'true' : 'false'
        });
        stageBtn.textContent = 'Chat';
        stageBtn.addEventListener('click', () => handlers.onSelectContent?.('chat'));

        const customize = createEl('button', 'notch-mode-link', { type: 'button', id: 'notch-customize-btn', 'aria-label': 'Personalizar Notch', title: 'Ajustes del Notch', text: 'Ajustes' });
        customize.addEventListener('click', () => openAppearance(customize));
        const tools = createEl('div', 'notch-footer-tools');
        tools.append(stageBtn, customize);
        footerEl.append(modes, tools);
      } else {
        footerEl.innerHTML = '';
      }
    }

    function update({ Axx, state, layout, channels, context }) {
      appearancePrefs = context.preferences || {};
      chatSurface?.setPrivacy(context.privacyShield);
      for (const button of appearanceEl.querySelectorAll('[data-profile]')) {
        const profile = WORKSPACE_PROFILES.find(p => p.id === button.dataset.profile);
        button.setAttribute('aria-pressed', String(Object.entries(profile.values).every(([key, value]) => appearancePrefs[key] === value)));
      }
      for (const sw of appearanceEl.querySelectorAll('[data-swatch]')) {
        sw.setAttribute('aria-pressed', String((appearancePrefs.accent || 'avatar') === sw.dataset.swatch));
      }
      for (const seg of appearanceEl.querySelectorAll('[data-seg-key]')) {
        seg.setAttribute('aria-pressed', String(String(appearancePrefs[seg.dataset.segKey] ?? '') === seg.dataset.segVal));
      }
      for (const field of appearanceEl.querySelectorAll('[data-preference]')) {
        if (field.type === 'checkbox') field.checked = Boolean(appearancePrefs[field.dataset.preference]);
        else if (document.activeElement !== field) field.value = String(appearancePrefs[field.dataset.preference] ?? '');
      }
      for (const badge of appearanceEl.querySelectorAll('[data-slider-val]')) {
        const k = badge.dataset.sliderVal;
        badge.textContent = k === 'surfaceOpacity' ? `${appearancePrefs.surfaceOpacity ?? 96}%` : `${appearancePrefs.topOffsetPx ?? 0} px`;
      }
      syncLivePreview();
      refreshAvatar(Axx, state);
      const [palette1, palette2] = paletteColors(Axx);
      const neutral = context.styleDirection === 'neutral-monolith';
      const customHex = appearancePrefs.accent === 'custom' ? appearancePrefs.customAccentHex : null;
      const rawC1 = neutral ? '#d6d7dc' : (customHex || ACCENTS[appearancePrefs.accent] || palette1);
      const rawC2 = neutral ? '#b4b8c4' : (customHex ? customHex : (ACCENT_SECONDARIES[appearancePrefs.accent] || ACCENTS[appearancePrefs.accent] || palette2));
      const c1 = readableAccent(rawC1);
      const c2 = readableAccent(rawC2);
      rootEl.style.setProperty('--notch-accent', c1);
      rootEl.style.setProperty('--notch-accent-2', c2);
      rootEl.style.setProperty('--notch-accent-ring', c1 + '3d');
      rootEl.style.setProperty('--notch-surface-alpha', String(Math.max(0.65, Math.min(1, (appearancePrefs.surfaceOpacity ?? 96) / 100))));
      rootEl.style.setProperty('--notch-top-offset', `${Math.max(0, Math.min(24, Number(appearancePrefs.topOffsetPx) || 0))}px`);
      rootEl.setAttribute('data-style', context.styleDirection || 'identity-accent');
      rootEl.setAttribute('data-theme', appearancePrefs.surfaceTheme || 'obsidian');
      rootEl.setAttribute('data-accent', appearancePrefs.accent || 'avatar');
      for (const key of ['material', 'density', 'contrast']) rootEl.setAttribute(`data-${key}`, appearancePrefs[key] || '');
      rootEl.setAttribute('data-shape', appearancePrefs.surfaceShape || 'notch');
      rootEl.setAttribute('data-border-style', appearancePrefs.borderStyle || 'subtle');
      rootEl.setAttribute('data-align', appearancePrefs.horizontalAlign || 'center');
      rootEl.setAttribute('data-motion', appearancePrefs.motionIntensity || 'organic');
      rootEl.setAttribute('data-glow', appearancePrefs.glowIntensity || 'subtle');
      rootEl.setAttribute('data-font', appearancePrefs.fontPreset || 'system');
      rootEl.setAttribute('data-pulse', appearancePrefs.ambientPulse ? 'true' : 'false');
      rootEl.setAttribute('data-hide-avatar-bar', appearancePrefs.showAvatarInNotch === false ? 'true' : 'false');
      rootEl.setAttribute('data-hide-quick-chat', appearancePrefs.showQuickChatButton === false ? 'true' : 'false');
      shellEl.setAttribute('data-reduced-motion', String(appearancePrefs.motionIntensity === 'reduced' || Boolean(Axx?.app?.store?.data?.settings?.reducedMotion)));

      const showApproach = state.physical === 'approach' || state.physical === 'retracting';
      approachEl.setAttribute('data-active', showApproach ? 'true' : 'false');
      approachEl.setAttribute('aria-hidden', showApproach ? 'false' : 'true');
      approachEl.style.setProperty('--approach-pull', String(context.approachPull || 0));

      const visible = Boolean(layout?.visible);
      shellEl.hidden = !visible;
      if (!visible || state.content !== 'chat' || state.size !== 'expanded') chatSurface?.hide();
      else chatSurface?.tick();
      if (!visible || state.size !== 'expanded') closeAppearance(false);
      if (!visible) return;

      const w = Math.round(channels?.width?.value ?? layout.width ?? 220);
      const h = Math.round(channels?.height?.value ?? layout.height ?? 34);
      const r = Math.round(channels?.radius?.value ?? layout.radius ?? 17);
      shellEl.style.setProperty('--notch-w', `${w}px`);
      shellEl.style.setProperty('--notch-h', `${h}px`);
      shellEl.style.setProperty('--notch-r', `${r}px`);
      const targetHeight = Math.max(h, Number(layout.height) || h);
      const reveal = state.size === 'expanded' || state.size === 'peek' ? Math.max(0, Math.min(1, (h - 50) / Math.max(1, targetHeight - 60))) : 0;
      shellEl.style.setProperty('--notch-reveal', String(reveal));

      shellEl.setAttribute('data-size', state.size);
      shellEl.setAttribute('data-content', state.content);
      shellEl.setAttribute('data-attention', state.attention);
      shellEl.setAttribute('data-layout-mode', layout.layoutMode || 'minimal');
      shellEl.setAttribute('data-drag-target', state.interaction === 'dragActive' || state.interaction === 'dragEnter' ? 'true' : 'false');
      const nextApprovalSignature = `${state.size}:${context.commandOperation?.operation_id}:${context.commandOperation?.state}:${context.privacyShield}`;
      if (nextApprovalSignature !== approvalSignature) {
        approvalSignature = nextApprovalSignature;
        const approval = state.size === 'expanded' ? buildApprovalInbox(context, context.privacyShield) : null;
        approvalHost.replaceChildren(...(approval ? [approval] : [])); approvalHost.hidden = !approval;
      }

      const expanded = state.size === 'expanded';
      if (expandBtn.getAttribute('aria-expanded') !== String(expanded)) expandBtn.replaceChildren(icon(expanded ? 'collapse' : 'expand', 15));
      expandBtn.setAttribute('aria-expanded', expanded ? 'true' : 'false');

      const badgeLabel = BADGE_LABELS[state.attention] || '';
      badgeEl.hidden = !badgeLabel;
      if (badgeLabel) badgeEl.textContent = badgeLabel;

      const primary = context.projections.find(p => p.id === state.selectedActivityId) || context.projections[0] || null;
      const shieldedPrimary = Boolean(context.privacyShield && primary?.privacy === 'private');

      if (state.size === 'expanded') {
        titleEl.textContent = 'AXX';
        metricEl.textContent = state.content === 'chat' ? 'Chat directo' : MODE_LINKS.find(m => m.id === state.content)?.label || 'Inicio';
      } else if (state.content === 'portal') {
        titleEl.textContent = state.interaction === 'dragActive' ? 'Suelta aquí' : 'Portal AXX';
        metricEl.textContent = context.portalItems?.length ? `${context.portalItems.length}` : '';
      } else if (primary) {
        titleEl.textContent = shieldedPrimary ? 'Actividad privada' : primary.title;
        metricEl.textContent = shieldedPrimary
          ? ''
          : (primary.metric || (primary.progress?.kind === 'determinate' ? `${Math.round(primary.progress.fraction * 100)}%` : ''));
      } else if (state.attention === 'offline') {
        titleEl.textContent = 'AXX (sin backend)';
        metricEl.textContent = '';
      } else {
        const cm = appearancePrefs.compactMetrics || 'auto';
        const now = new Date();
        if (cm === 'minimal') {
          titleEl.textContent = '';
          metricEl.textContent = state.stageOpen ? 'Stage' : '';
        } else if (cm === 'clock') {
          titleEl.textContent = 'AXX';
          metricEl.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } else if (cm === 'clock-date') {
          titleEl.textContent = now.toLocaleDateString([], { weekday: 'short', day: 'numeric' });
          metricEl.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } else if (cm === 'stats') {
          titleEl.textContent = 'PC';
          metricEl.textContent = context.telemetry
            ? `CPU ${Math.round(context.telemetry.cpu_percent || 0)}% · RAM ${Math.round(context.telemetry.memory_percent || 0)}%`
            : 'Sistema listo';
        } else if (cm === 'studio') {
          const activeAgents = (context.projections || []).filter(p => p.kind === 'agent' || p.kind === 'devpulse').length;
          titleEl.textContent = 'Studio';
          metricEl.textContent = activeAgents > 0 ? `${activeAgents} en curso` : 'Listo';
        } else if (cm === 'greeting') {
          const hr = now.getHours();
          titleEl.textContent = hr < 12 ? 'Buenos días' : hr < 19 ? 'Buenas tardes' : 'Buenas noches';
          metricEl.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } else {
          titleEl.textContent = 'AXX';
          metricEl.textContent = state.stageOpen ? 'Stage' : '';
        }
      }

      const mediaItem = context.projections.find(p => p.kind === 'media');
      const showMiniPeak = Boolean(mediaItem?.mediaMeta?.playing && mediaItem?.mediaMeta?.audioAvailable);
      peakMiniEl.hidden = !showMiniPeak;
      if (showMiniPeak) {
        const peak = Math.max(0.1, Math.min(1, mediaItem.mediaMeta.peak || 0));
        [...peakMiniEl.children].forEach((bar, i) => {
          bar.style.setProperty('--bar-h', String(Math.max(0.15, peak * (1 - i * 0.16))));
        });
      }

      const overflow = Math.max(0, (context.projections.length || 0) - 1);
      overflowBtn.hidden = overflow <= 0;
      if (overflow > 0) overflowBtn.textContent = `+${overflow}`;

      if (primary?.progress?.kind === 'determinate') {
        progressTrack.hidden = false;
        progressFill.removeAttribute('data-indeterminate');
        progressFill.style.width = `${Math.round(Math.max(0, Math.min(1, primary.progress.fraction)) * 100)}%`;
      } else if (primary?.progress?.kind === 'indeterminate') {
        progressTrack.hidden = false;
        progressFill.setAttribute('data-indeterminate', 'true');
        progressFill.style.width = '34%';
      } else {
        progressTrack.hidden = true;
      }

      const liveText = `${badgeLabel ? badgeLabel + ' ' : ''}${titleEl.textContent}${metricEl.textContent ? ' ' + metricEl.textContent : ''}`;
      if (liveText !== lastLiveMsg && (state.attention === 'approval' || state.attention === 'error' || state.attention === 'completed')) {
        lastLiveMsg = liveText;
        liveEl.textContent = liveText;
      }

      const bodySig = JSON.stringify({
        size: state.size,
        content: state.content,
        selected: state.selectedActivityId,
        pinned: context.pinnedActivityId,
        frozen: context.contextFrozen,
        interaction: state.interaction,
        stageOpen: state.stageOpen,
        privacy: context.privacyShield,
        opState: context.commandOperation?.state || '',
        opId: context.commandOperation?.operation_id || '',
        receipt: ctxFingerprint(context.lastReceipt),
        portalItems: context.portalItems?.map(i => [i.id, i.name]),
        offlineCount: context.offlineQueue?.length || 0,
        intentCount: context.intentResults?.length || 0,
        telAt: context.telemetry?.updatedAt || 0,
        telemetryPending: context.telemetryPending, telemetryError: context.telemetryError, portalReceipt: context.portalReceipt,
        threads: context.recall?.threads?.map(t => [t.id, t.title, t.active]),
        proj: context.projections.map(p => [p.id, p.status, p.title, ['timer', 'media'].includes(p.kind) ? '' : p.metric, p.progress?.kind, p.actions, p.agentEvents, p.mediaMeta?.playing, p.mediaMeta?.sessions?.map(s => [s.id, s.title]), p.mediaMeta?.selectedId, p.mediaMeta?.canSeek])
      });

      const userTyping =
        state.content === 'intent' &&
        lastRenderedContent === 'intent' &&
        intentInputRef &&
        document.activeElement === intentInputRef;
      const focusedControl = bodyEl.contains(document.activeElement) && document.activeElement?.matches('input, select');
      const sameView = lastRenderedContent === state.content;
      const chatIsMounted = sameView && state.content === 'chat' && state.size === 'expanded' && chatSurface?.root?.isConnected;
      if (bodySig !== lastBodySig && !chatIsMounted && !userTyping && !(sameView && focusedControl && context.commandOperation?.state !== 'awaiting_approval')) {
        lastBodySig = bodySig;
        lastRenderedContent = state.content;
        renderBody(state, context);
        if (!sameView) bodyEl.scrollTop = 0;
        chatSurface?.setPrivacy(context.privacyShield);
        if (!sameView && appearancePrefs.motionIntensity !== 'reduced' && !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
          bodyEl.getAnimations().forEach(animation => animation.cancel());
          bodyEl.animate([{ opacity: 0.72, transform: 'translateY(6px)' }, { opacity: 1, transform: 'translateY(0)' }], { duration: 190, easing: 'cubic-bezier(.22,.8,.24,1)' });
        }
      }

      for (const p of context.projections) {
        if (p.kind !== 'timer') continue;
        const card = [...bodyEl.querySelectorAll('[data-activity-id]')].find(el => el.dataset.activityId === p.id);
        if (!card) continue;
        const sub = card.querySelector('.notch-muted');
        if (sub && sub.textContent !== p.subtitle) sub.textContent = p.subtitle || '';
        const pctEl = card.querySelector('.notch-primary-metric');
        const timer = card.querySelector('.notch-timer-value');
        if (timer && !context.privacyShield) timer.textContent = p.metric || p.title;
        if (pctEl && p.progress?.kind === 'determinate') {
          pctEl.textContent = `${Math.round(Math.max(0, Math.min(1, p.progress.fraction)) * 100)}%`;
        }
      }
      const media = context.projections.find(p => p.kind === 'media');
      const seek = bodyEl.querySelector('.notch-seek-slider');
      if (seek && document.activeElement !== seek && media?.mediaMeta?.duration > 0) {
        const cur = Math.round(media.mediaMeta.time || 0);
        seek.value = String(cur);
        seek.style.setProperty('--seek-pct', `${Math.max(0, Math.min(100, (100 * cur) / media.mediaMeta.duration)).toFixed(1)}%`);
      }
      const time = bodyEl.querySelector('[data-media-time]');
      if (time) time.textContent = context.privacyShield && media?.privacy === 'private' ? '' : media?.metric || '';
    }

    function ctxFingerprint(r) {
      if (!r) return '';
      return `${r.operation_id || ''}:${r.state || ''}`;
    }

    function mountSettingsCard(prefs, onPrefsChange, monitorsProvider) {
      const host = document.getElementById('view-settings');
      if (!host || document.getElementById('axx-notch-settings')) return null;

      const card = createEl('section', 'notch-settings-card', { id: 'axx-notch-settings' });
      const title = createEl('strong', '', { text: 'Tu AXX, también en el borde' });
      const desc = createEl('small', '', {
        text: 'El mismo personaje 3D y tus sesiones, en un notch limpio con desvanecimiento inteligente.'
      });

      const mkCheck = (id, labelText, key) => {
        const row = createEl('label', 'notch-settings-row');
        row.append(createEl('span', '', { text: labelText }));
        const chk = createEl('input', '', { type: 'checkbox', id });
        chk.checked = Boolean(prefs[key]);
        chk.addEventListener('change', () => onPrefsChange?.({ [key]: chk.checked }));
        row.append(chk);
        return { row, chk };
      };

      const mkSelect = (id, labelText, key, opts, asNumber = false) => {
        const row = createEl('label', 'notch-settings-row');
        row.append(createEl('span', '', { text: labelText }));
        const sel = createEl('select', '', { id });
        for (const [val, txt] of opts) {
          const opt = new Option(txt, val);
          if (String(prefs[key]) === String(val)) opt.selected = true;
          sel.add(opt);
        }
        sel.addEventListener('change', () => onPrefsChange?.({ [key]: asNumber ? Number(sel.value) : sel.value }));
        row.append(sel);
        return { row, sel };
      };

      const en = mkCheck('notch-pref-enabled', 'Activar modo Notch superior', 'enabled');
      const ife = mkCheck('notch-pref-idlefade', 'Desvanecer automáticamente al no usar', 'idleFadeEnabled');
      const ifs = mkSelect('notch-pref-idlesecs', 'Tiempo para desvanecer', 'idleFadeSeconds', IDLE_FADE_DELAY_OPTIONS, true);
      const ifo = mkSelect('notch-pref-idleopacity', 'Transparencia al desvanecer', 'idleFadeOpacity', IDLE_FADE_OPACITY_OPTIONS);
      const ad = mkCheck('notch-pref-autodock', 'Acoplar al arrastrar al borde superior', 'autoDockOnTopDrag');
      const hp = mkCheck('notch-pref-hoverpeek', 'Vista rápida (Peek) al pasar el cursor', 'hoverPeek');
      const avb = mkCheck('notch-pref-avatarbar', 'Mostrar retrato 3D en la barra compacta', 'showAvatarInNotch');
      const snd = mkCheck('notch-pref-sounds', 'Sonidos discretos en Archivos y acciones', 'soundEffectsEnabled');
      const fs = mkCheck('notch-pref-fullscreen', 'Ocultar automáticamente en pantalla completa', 'autoHideFullscreen');
      const gm = mkCheck('notch-pref-gaming', 'Suprimir durante juegos a pantalla completa', 'gamingSuppression');
      const pr = mkCheck('notch-pref-privacy', 'Cortina visual de privacidad', 'privacyCurtain');
      const sr = mkCheck('notch-pref-suspend', 'Suspender renderizado 3D al estar acoplado', 'suspendRendererWhenDocked');

      const sn = mkSelect('notch-pref-sensitivity', 'Sensibilidad de acoplamiento', 'dockSensitivity', [
        ['low', 'Baja (32 DIP)'],
        ['normal', 'Normal (48 DIP)'],
        ['high', 'Alta (68 DIP)']
      ]);
      const mon = mkSelect('notch-pref-monitor', 'Monitor preferido', 'preferredMonitor', [
        ['auto', 'Automático (donde estaba el avatar)'],
        ['primary', 'Monitor principal'],
        ['active', 'Monitor activo del cursor']
      ]);

      const btnRow = createEl('div', 'notch-actions-row');
      const toggleNowBtn = createEl('button', 'notch-pill-btn', {
        type: 'button',
        id: 'notch-pref-toggle-now',
        'data-primary': 'true',
        text: 'Alternar Avatar / Notch (Alt+Shift+N)'
      });
      toggleNowBtn.addEventListener('click', () => onPrefsChange?.({ toggleNow: true }));

      const resetBtn = createEl('button', 'notch-pill-btn', {
        type: 'button',
        id: 'notch-pref-reset',
        'data-danger': 'true',
        text: 'Restablecer ajustes del Notch'
      });
      resetBtn.addEventListener('click', () => onPrefsChange?.({ resetNotch: true }));
      btnRow.append(toggleNowBtn, resetBtn);

      const appearanceControls = APPEARANCE_FIELDS.map(([key, label, options]) => ({ key, ...mkSelect(`notch-pref-${key}`, label, key, options) }));
      const group = (label, rows, open = false) => {
        const detail = createEl('details', 'notch-settings-group', open ? { open: '' } : {});
        detail.append(createEl('summary', '', { text: label }), ...rows);
        return detail;
      };
      const preview = createEl('div', 'notch-settings-preview');
      const stage = createEl('div', 'notch-avatar-stage');
      const portrait = createAvatarPortrait();
      if (avatarPortrait) { portrait.src = avatarPortrait; portrait.hidden = false; }
      stage.append(portrait);
      preview.append(stage, createEl('span', '', { text: 'Tu personaje. Tu identidad.' }));
      card.append(
        title, desc, preview, en.row,
        group('Apariencia y movimiento', [...appearanceControls.map(c => c.row), avb.row], true),
        group('Desvanecimiento automático (Auto-Fade)', [ife.row, ifs.row, ifo.row], true),
        group('Comportamiento y sonidos', [ad.row, hp.row, sn.row, snd.row]),
        group('Pantallas', [mon.row]),
        group('Privacidad y atención', [fs.row, gm.row, pr.row]),
        group('Rendimiento', [sr.row]),
        btnRow
      );
      host.appendChild(card);

      if (typeof monitorsProvider === 'function') {
        void Promise.resolve(monitorsProvider()).then(list => {
          if (!Array.isArray(list)) return;
          for (const m of list) {
            if (!m?.id || [...mon.sel.options].some(o => o.value === m.id)) continue;
            mon.sel.add(new Option(`${m.primary ? '★ ' : ''}${m.id} (${Math.round((m.scaleFactor || 1) * 100)}%)`, m.id));
          }
          mon.sel.value = prefs.preferredMonitor || 'auto';
        }).catch(() => {});
      }

      return {
        sync(nextPrefs) {
          en.chk.checked = Boolean(nextPrefs.enabled);
          ife.chk.checked = Boolean(nextPrefs.idleFadeEnabled);
          ifs.sel.value = String(nextPrefs.idleFadeSeconds ?? 8);
          ifo.sel.value = nextPrefs.idleFadeOpacity || 'subtle';
          ad.chk.checked = Boolean(nextPrefs.autoDockOnTopDrag);
          hp.chk.checked = Boolean(nextPrefs.hoverPeek);
          avb.chk.checked = nextPrefs.showAvatarInNotch !== false;
          snd.chk.checked = nextPrefs.soundEffectsEnabled !== false;
          fs.chk.checked = Boolean(nextPrefs.autoHideFullscreen);
          gm.chk.checked = Boolean(nextPrefs.gamingSuppression);
          pr.chk.checked = Boolean(nextPrefs.privacyCurtain);
          sr.chk.checked = Boolean(nextPrefs.suspendRendererWhenDocked);
          for (const control of appearanceControls) control.sel.value = nextPrefs[control.key];
          sn.sel.value = nextPrefs.dockSensitivity || 'normal';
          mon.sel.value = nextPrefs.preferredMonitor || 'auto';
        }
      };
    }

    return {
      rootEl,
      shellEl,
      approachEl,
      update,
      setIdleFade,
      playTactileChime,
      mountSettingsCard,
      focusIntent() { intentInputRef?.focus(); },
      getInteractiveElements() {
        return shellEl.hidden ? [] : [shellEl];
      },
      getAvatarEvidence() { return { source: 'SoftwareRenderer.captureIdentityPNG', captures: avatarCaptures, failures: avatarCaptureFailures, hasPortrait: Boolean(avatarPortrait) }; }
    };
  }

  return { createNotchUI, readableAccent };
});
