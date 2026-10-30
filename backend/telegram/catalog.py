"""Small phrase guide backed by the PC's executable command catalog."""
import unicodedata


EXAMPLES = (
    ('calculator', 'axx.desktop.open_app', 'Abrir Calculadora', 'abre calculadora', 'Aplicaciones'),
    ('notepad', 'axx.desktop.open_app', 'Abrir Bloc de notas', 'abre bloc de notas', 'Aplicaciones'),
    ('explorer', 'axx.desktop.open_app', 'Abrir Explorador', 'abre explorador', 'Aplicaciones'),
    ('paint', 'axx.desktop.open_app', 'Abrir Paint', 'abre paint', 'Aplicaciones'),
    ('windows', 'axx.desktop.list_windows', 'Ver ventanas abiertas', 'mis ventanas', 'Consultas'),
    ('apps', 'axx.desktop.list_apps', 'Ver aplicaciones instaladas', 'aplicaciones instaladas', 'Consultas'),
    ('system', 'axx.system.telemetry', 'Consultar el sistema', 'información del sistema', 'Consultas'),
    ('close', 'axx.desktop.window.close', 'Cerrar una ventana', 'cierra Spotify', 'Ventanas'),
)


def is_catalog_request(text):
    value = ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))
    return ' '.join(value.strip(' ¿?!.').split()) in {
        '/comandos', 'comandos', 'ver comandos', 'ver los comandos', 'que puedes hacer', 'que puedo hacer'}


def phrase_catalog(catalog, *, pc_commands, remote_confirmations):
    if not isinstance(catalog, dict) or not isinstance(catalog.get('commands'), list):
        return {'items': [], 'text': 'No se pudo consultar el catálogo de tu PC. Actualiza el estado e inténtalo de nuevo.'}
    registered = {item['id']: item for item in catalog['commands']
                  if isinstance(item, dict) and isinstance(item.get('id'), str)
                  and item.get('source_kind') == 'local_adapter' and item.get('execution_enabled') is True}
    items = []
    for key, command_id, title, example, category in EXAMPLES:
        command = registered.get(command_id)
        if command is None:
            continue
        safe = command.get('requires_approval') is False and (
            command.get('risk') in ('read', 'desktop_open')
            or command_id == 'axx.desktop.window.close' and command.get('risk') == 'local_state')
        available = pc_commands is True and remote_confirmations is True and safe
        reason = ('Activa Acciones en esta PC desde Axx.' if pc_commands is not True else
                  'Activa Confirmar comandos desde Telegram en Axx.' if remote_confirmations is not True else
                  'Esta orden requiere aprobación en la PC.' if not safe else
                  'La ventana debe estar abierta. Revisarás el título antes de decidir.' if key == 'close' else
                  'Revisa la tarjeta y elige Aprobar una vez o Denegar.')
        description = ('Puedes sustituir Spotify por el nombre de una ventana abierta. No se fuerza su cierre.'
                       if key == 'close' else command.get('description', 'Orden del catálogo de tu PC.'))
        items.append({'id': key, 'command_id': command_id, 'title': title, 'example': example,
                      'description': description, 'category': category, 'available': available, 'reason': reason})
    lines = ['Comandos de Axx', 'Escribe una de estas frases en este chat:']
    lines.extend(('• ' if item['available'] else '• [Requiere configuración] ') + item['example'] for item in items)
    if not items:
        lines = ['No hay comandos compatibles disponibles en el catálogo de tu PC.']
    elif not pc_commands or not remote_confirmations:
        lines.append('Activa Acciones en esta PC y Confirmar comandos desde Telegram en Axx.')
    else:
        lines.append('Cada petición se comprueba en tu PC. Revisa su tarjeta para aprobar o denegar. Cerrar requiere una ventana abierta.')
    return {'items': items, 'text': '\n'.join(lines)}
