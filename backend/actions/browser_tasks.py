"""Small native workflows over the existing application routes and input owner."""
import math
import re
import time
from urllib.parse import urlencode

from . import windows_automation as uia
from .desktop import plain


def select_video(links, query):
    words = [w for w in re.findall(r'\w+', plain(query)) if w not in {'la', 'el', 'de', 'del', 'una', 'un', 'cancion', 'tema', 'video'}]
    candidates = [row for row in links if row.get('video_id') and words
                  and all(w in re.sub(r'\W+', '', plain(row['title'])) for w in words)]
    # Prefer a uniquely labelled official recording; ties require user selection.
    official = [row for row in candidates if re.search(r'\b(?:official|oficial)\b', plain(row['title']))
                and not re.search(r'\b(?:live|cover|remix|karaoke|lyrics|lyric)\b', plain(row['title']))]
    candidates = official or candidates
    if len(candidates) != 1:
        raise ValueError('No hay un vídeo único que coincida con la canción. Indica el título o la versión exacta.')
    return candidates[0]


def player_position(observed):
    if observed.get('truncated') or any(re.match(r'^(?:anuncio|ad|saltar anuncios|skip ad|visitar anunciante)\b', plain(row.get('name', '')))
                                      for row in observed.get('controls', []) if not row.get('offscreen')):
        return None
    sliders = [row for row in observed.get('controls', []) if row.get('control_type') == 'ControlType.Slider'
               and not row.get('offscreen') and re.search(r'(?:progreso|progress|seek|tiempo)', plain(row.get('name', '')))
               and 'RangeValue' in row.get('state', {})]
    pause = any(row.get('control_type') == 'ControlType.Button' and not row.get('offscreen')
                and re.match(r'^(?:pausa|pausar|pause)\b', plain(row.get('name', ''))) for row in observed.get('controls', []))
    value = sliders[0]['state']['RangeValue']['value'] if len(sliders) == 1 and pause else None
    return value if type(value) in (int,float) and math.isfinite(value) else None


def execute(tool, inputs, workspace, cancelled, runtime):
    from .application_tools import _window_rows, _select_window, _observe, _input
    from .tools import DesktopTool, ToolResult
    profile, rows = _window_rows(inputs['application'])
    owner = getattr(runtime, 'input_control', None)
    if owner is None:
        raise ValueError('El broker compartido de entrada no está conectado.')
    if not rows and tool.kind in ('browse', 'youtube'):
        from ..application_catalog import resolve_application
        app = resolve_application(inputs['application'])['app']
        opened = DesktopTool('installed_app').execute_with_control({'app_id': app['app_id']}, workspace, cancelled, owner)
        if not opened.success or not opened.output.get('ready_for_action'):
            raise ValueError(opened.error or 'No se confirmó la ventana del navegador.')
    profile, window = _select_window(inputs)
    bound = dict(inputs, window_id=window['window_id'], pid=window['pid'])
    with owner.automation(cancelled) as control:
        uia.focus_window(window['window_id'], window['pid'], control=control)
        _, current = _select_window(bound)
        if current['process_started'] != window['process_started']:
            raise ValueError('Cambió el proceso antes de actuar.')
        def content():
            control.renew()
            _, current = _select_window(bound)
            if current['process_started'] != window['process_started']:
                raise ValueError('Cambió el proceso durante la tarea.')
            return uia.read_window_content(current['window_id'], current['pid'], current['title'], cancelled=control)
        if tool.kind == 'hover':
            observed = content()
            if observed.get('truncated'):
                raise ValueError('La observación está incompleta; no puedo resolver una etiqueta única.')
            matches = [row for row in observed['controls'] if not row.get('offscreen') and row.get('enabled')
                       and plain(row.get('name', '')).strip() == plain(inputs['name']).strip()
                       and row.get('bounds', {}).get('width', 0) > 0 and row['bounds'].get('height', 0) > 0]
            if len(matches) != 1:
                raise ValueError('No encuentro un elemento visible y único llamado «' + inputs['name'] + '».')
            rect = matches[0]['bounds']
            return ToolResult(**_input(window, observed, 'move', control,
                x=rect['x'] + rect['width']//2, y=rect['y'] + rect['height']//2))
        commands = [c for c in profile['commands'] if c['kind'] == 'navigate']
        if len(commands) != 1:
            raise ValueError('No hay una ruta única de navegación para esta aplicación.')
        def navigate(url):
            control.renew()
            _, current = _select_window(bound)
            if current['process_started'] != window['process_started']:
                raise ValueError('Cambió el proceso antes de navegar.')
            return tool._navigate_url(dict(inputs, url=url), commands[0], current, _observe(current, control, browser=True), control)
        if tool.kind == 'browse':
            return navigate(inputs['url'])
        search_url = 'https://www.youtube.com/results?' + urlencode({'search_query': inputs['query']})
        navigate(search_url)
        deadline = time.monotonic() + 25
        observed = None
        while time.monotonic() < deadline and not control.is_set():
            observed = content()
            if any(row.get('video_id') for row in observed.get('links', [])):
                break
            control.wait(.4)
        if control.is_set():
            raise ValueError('Reproducción cancelada antes de elegir un resultado.')
        if not observed or observed.get('truncated'):
            raise ValueError('Los resultados de YouTube no se pudieron observar completamente.')
        video = select_video(observed.get('links', []), inputs['query'])
        navigate(video['url'])
        # Navigation is already an effect: failures from here require inspection, never blind retries.
        try:
            start = None
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and not control.is_set():
                observed = content()
                title = plain(observed.get('window_title', ''))
                if plain(video['title']) not in title:
                    control.wait(.5)
                    continue
                position = player_position(observed)
                if position is not None:
                    if start is not None and position > start:
                        return ToolResult(True, output={'query': inputs['query'], 'video_id': video['video_id'],
                            'video_title': video['title'], 'url': video['url'], 'playing': True,
                            'position_before': start, 'position_after': position},
                            evidence={'verification': 'youtube_player_progress', 'accepted': True})
                    start = position
                else:
                    start = None
                    play = [r for r in observed.get('controls', []) if r.get('control_type') == 'ControlType.Button'
                            and r.get('supports_invoke_pattern') and r.get('enabled') and not r.get('offscreen')
                            and re.match(r'^(?:reproducir|play)\s*\(k\)', plain(r.get('name', '')))]
                    if len(play) == 1:
                        uia.invoke_control(window['window_id'], window['pid'], play[0]['control_id'],
                            observed['window_title'], play[0]['name'], cancelled=control)
                control.wait(.6)
            raise ValueError('El vídeo se abrió, pero no confirmé el avance del reproductor; revisa anuncios, permisos o bloqueos.')
        except (ValueError, OSError, KeyError) as exc:
            raise uia.UncertainEffect(str(exc)) from exc
