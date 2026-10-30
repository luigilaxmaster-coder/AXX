"""Local-only bot setup; credentials never go to the Axx conversation."""
from __future__ import annotations

import argparse
import queue
import re
import threading
import tkinter as tk
from tkinter import ttk
import webbrowser

from backend.mobile.network import tailscale_status
from backend.telegram.bot import BotApiError, bot_request
from backend.telegram.bot_config import load_bot, save_bot, validate_bot
from backend.telegram.config import load_account

SAFE_CODES = {'TOKEN_REJECTED', 'OWNER_CHAT_NOT_STARTED', 'OWNER_BLOCKED_BOT', 'MINIAPP_URL_REJECTED',
              'RATE_LIMITED', 'NETWORK_ERROR', 'BOT_IDENTITY_INVALID', 'BOT_REQUEST_REJECTED', 'BOT_RESPONSE_INVALID', 'SETUP_ERROR'}


def safe_code(code):
    return code if code in SAFE_CODES else 'SETUP_ERROR'


def discover_url():
    try:
        status = tailscale_status()
        if status.get('BackendState') != 'Running':
            return ''
        own = status.get('Self') or {}
        if not own.get('Online'):
            return ''
        hostname = (own.get('DNSName') or status.get('SelfDNSName') or '').rstrip('.')
        if not isinstance(hostname, str) or not re.fullmatch(r'[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+', hostname):
            return ''
        return 'https://' + hostname + '/'
    except Exception:
        return ''


def configure(token, url, enabled, data_dir=None):
    if not token:
        token = load_bot(data_dir)['token']
    value = validate_bot({'token': token, 'enabled': enabled, 'public_url': url.strip()})
    account = load_account(data_dir)
    me = bot_request(token, 'getMe', {})
    if not isinstance(me, dict) or me.get('is_bot') is not True:
        raise BotApiError('BOT_IDENTITY_INVALID')
    username = me.get('username')
    if isinstance(username, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}', username):
        value['username'] = username
    save_bot(value, data_dir)
    result = {'local_saved': True, 'account_enabled': account['enabled'],
              'menu_configured': False, 'error_code': None, 'retry_after': 0}
    if value['public_url']:
        try:
            menu_ok = bot_request(token, 'setChatMenuButton', {'chat_id': account['owner_id'], 'menu_button': {
                'type': 'web_app', 'text': 'Abrir Axx', 'web_app': {'url': value['public_url']}}})
            if menu_ok is not True:
                raise BotApiError('BOT_REQUEST_REJECTED')
            commands_ok = bot_request(token, 'setMyCommands', {'scope': {'type': 'chat', 'chat_id': account['owner_id']},
                'commands': [{'command': 'start', 'description': 'Abrir menú de Axx'},
                             {'command': 'menu', 'description': 'Mostrar menú de Axx'},
                             {'command': 'estado', 'description': 'Consultar el estado'}]})
            if commands_ok is not True:
                raise BotApiError('BOT_REQUEST_REJECTED')
            result['menu_configured'] = True
        except BotApiError as exc:
            result.update(error_code=safe_code(exc.code), retry_after=exc.retry_after)
        except Exception:
            result['error_code'] = 'BOT_REQUEST_REJECTED'
    return result


def diagnostic(code, retry=0):
    messages = {
        'TOKEN_REJECTED': 'Telegram rechazó el token. Copia el token vigente desde BotFather.',
        'OWNER_CHAT_NOT_STARTED': 'Abre tu bot desde tu cuenta personal de Telegram y envía /start; después vuelve a guardar.',
        'OWNER_BLOCKED_BOT': 'Telegram rechazó el acceso al chat. Desbloquea el bot y envía /start desde tu cuenta personal.',
        'MINIAPP_URL_REJECTED': 'Telegram rechazó la URL de la MiniApp. Revisa que sea HTTPS y esté configurada correctamente.',
        'RATE_LIMITED': 'Telegram limitó los intentos.' + (f' Espera {retry} segundos.' if retry else ' Espera antes de volver a intentar.'),
        'NETWORK_ERROR': 'No se pudo conectar con Telegram. Comprueba la conexión.',
        'BOT_IDENTITY_INVALID': 'Telegram no confirmó que el token pertenezca a un bot.',
    }
    return messages.get(code, 'No se confirmó la operación. Revisa la cuenta, el token, la URL y la conexión.')


class BotSetup:
    def __init__(self, root, data_dir=None):
        self.root, self.data_dir = root, data_dir
        self.events = queue.Queue()
        root.title('Configurar bot de Telegram para Axx · Diagnóstico')
        frame = ttk.Frame(root, padding=16)
        frame.grid(sticky='nsew')
        ttk.Label(frame, text='En Telegram, abre BotFather y usa /newbot. Copia aquí el token; no lo envíes al chat de Codex.', wraplength=480).grid(row=0, column=0, columnspan=2, sticky='w')
        ttk.Button(frame, text='Abrir BotFather', command=lambda: webbrowser.open('https://t.me/BotFather')).grid(row=1, column=0, columnspan=2, sticky='w', pady=8)
        ttk.Label(frame, text='Token del bot').grid(row=2, column=0, sticky='w')
        self.token = ttk.Entry(frame, width=45, show='*')
        self.token.grid(row=2, column=1, sticky='ew')
        ttk.Label(frame, text='URL HTTPS de MiniApp').grid(row=3, column=0, sticky='w')
        self.url = ttk.Entry(frame, width=45)
        self.url.grid(row=3, column=1, sticky='ew')
        self.enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text='Activar bot al guardar', variable=self.enabled).grid(row=4, column=0, columnspan=2, sticky='w')
        self.save_button = ttk.Button(frame, text='Validar y guardar', command=self.save)
        self.save_button.grid(row=5, column=0, columnspan=2, sticky='w', pady=8)
        self.status = tk.StringVar(value='Los secretos se guardan protegidos en Windows. La cuenta y sus permisos no cambian.')
        ttk.Label(frame, textvariable=self.status, wraplength=480).grid(row=6, column=0, columnspan=2, sticky='w')
        self.had_saved = False
        try:
            existing = load_bot(data_dir)
            self.url.insert(0, existing['public_url'])
            self.enabled.set(existing['enabled'])
            self.had_saved = True
            self.status.set('Deja el token vacío para conservar el guardado. La cuenta y sus permisos no cambian.')
        except FileNotFoundError:
            pass
        except Exception:
            self.status.set('No se pudo leer la configuración protegida. No se modificó.')
        if not self.had_saved:
            threading.Thread(target=self._discover, daemon=True).start()
        root.after(100, self._poll)

    def _discover(self):
        self.events.put(('url', discover_url()))

    def save(self):
        token, url, enabled = self.token.get().strip(), self.url.get().strip(), bool(self.enabled.get())
        self.save_button.configure(state='disabled')
        self.status.set('Validando con Telegram y guardando de forma protegida…')
        def work():
            try:
                self.events.put(('saved', configure(token, url, enabled, self.data_dir)))
            except BotApiError as exc:
                self.events.put(('error', (safe_code(exc.code), exc.retry_after)))
            except Exception:
                self.events.put(('error', ('SETUP_ERROR', 0)))
        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'url':
                    if value and not self.url.get():
                        self.url.insert(0, value)
                elif kind == 'saved':
                    self.save_button.configure(state='normal')
                    if value['local_saved']:
                        self.token.delete(0, 'end')
                    if value['error_code']:
                        self.status.set('Bot guardado localmente; menú no confirmado [' + value['error_code'] + ']. ' + diagnostic(value['error_code'], value['retry_after']))
                    elif not value['account_enabled']:
                        self.status.set('Bot guardado. Activa también la cuenta dedicada en Axx para usarlo; sus permisos no cambiaron.')
                    elif value['menu_configured']:
                        self.status.set('Bot y menú configurados. Verifica la MiniApp y la conexión real desde Telegram.')
                    else:
                        self.status.set('Bot guardado. No se configuró una URL de MiniApp.')
                else:
                    self.save_button.configure(state='normal')
                    code, retry = value
                    self.status.set('No se guardó [' + code + ']. ' + diagnostic(code, retry))
        except queue.Empty:
            pass
        self.root.after(100, self._poll)


def main():
    parser = argparse.ArgumentParser(description='Configurar el bot de Telegram localmente')
    parser.add_argument('--data-dir')
    args = parser.parse_args()
    root = tk.Tk()
    BotSetup(root, args.data_dir)
    root.mainloop()


if __name__ == '__main__':
    main()
