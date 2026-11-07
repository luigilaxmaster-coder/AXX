"""Local-only Telegram account setup; run with python -m backend.telegram.setup."""
import asyncio
import logging
import queue
import re
import threading
import time
import tkinter as tk
from tkinter import ttk

from backend.telegram.config import GRANTS, account_lease, account_path, load_account, save_account, update_permissions


class SetupError(ValueError):
    pass


def setup_error(error):
    """Only fixed public diagnostics; exception text may contain account secrets."""
    messages = {
        'ApiIdInvalidError': ('API_ID_INVALID', 'Telegram rechazó API ID/API hash. Copia ambos de la misma aplicación en my.telegram.org.'),
        'ApiIdPublishedFloodError': ('API_ID_PUBLISHED_FLOOD', 'Telegram restringió estas credenciales de aplicación. Usa las de tu propia aplicación en my.telegram.org.'),
        'PhoneNumberInvalidError': ('PHONE_NUMBER_INVALID', 'Telegram rechazó el teléfono. Usa formato internacional con + y código de país.'),
        'PhoneNumberBannedError': ('PHONE_NUMBER_BANNED', 'Telegram indica que ese número está bloqueado. Revisa la cuenta en su aplicación oficial.'),
        'PhoneNumberUnoccupiedError': ('PHONE_NUMBER_UNOCCUPIED', 'Ese número no tiene una cuenta. Créala primero en la aplicación oficial de Telegram.'),
        'PhoneCodeInvalidError': ('PHONE_CODE_INVALID', 'Telegram rechazó el código. Introduce el último recibido para este inicio de sesión.'),
        'PhoneCodeExpiredError': ('PHONE_CODE_EXPIRED', 'El código caducó. Pulsa Enviar código para solicitar uno nuevo.'),
        'PhoneCodeEmptyError': ('PHONE_CODE_EMPTY', 'Introduce el código recibido para este inicio de sesión.'),
        'PhoneCodeHashEmptyError': ('PHONE_CODE_HASH_EMPTY', 'La solicitud del código ya no está disponible. Pulsa Enviar código de nuevo.'),
        'PasswordHashInvalidError': ('PASSWORD_HASH_INVALID', 'La contraseña de verificación en dos pasos es incorrecta. Corrígela e inténtalo de nuevo.'),
        'SessionPasswordNeededError': ('TWO_FACTOR_REQUIRED', 'Telegram requiere tu contraseña de verificación en dos pasos.'),
        'AuthRestartError': ('AUTH_RESTART', 'Telegram pidió reiniciar el acceso. Pulsa Enviar código de nuevo.'),
    }
    name = type(error).__name__
    if name in messages:
        return (*messages[name], 0)
    if name in ('FloodWaitError', 'FloodPremiumWaitError', 'PhoneNumberFloodError', 'PhonePasswordFloodError'):
        seconds = getattr(error, 'seconds', 0)
        seconds = seconds if type(seconds) is int and 0 < seconds <= 365*86400 else 0
        message = (f'Telegram exige esperar {seconds} segundos antes de reintentar.' if seconds else
                   'Telegram limitó los intentos. Espera antes de volver a solicitar un código.')
        return 'FLOOD_WAIT', message, seconds
    if isinstance(error, SetupError):
        local = {
            'TWO_FACTOR_REQUIRED': 'Introduce la contraseña de verificación en dos pasos.',
            'OWNER_IS_ACCOUNT': 'Estás conectando la misma cuenta que usarás para llamar. Conecta la cuenta dedicada de Axx.',
            'BOT_ACCOUNT': 'Se necesita una cuenta de usuario de Telegram para las llamadas privadas.',
            'ACCOUNT_UNAVAILABLE': 'Telegram no devolvió una cuenta de usuario autorizada.',
            'ACCOUNT_EXISTS': 'Ya existe una cuenta guardada. Cierra y vuelve a abrir esta ventana para editar sus permisos.',
            'AUTH_FLOW_UNSUPPORTED': 'Telegram solicitó un método de acceso que este conector todavía no admite. Comprueba el acceso en la aplicación oficial.',
        }
        code = error.args[0] if error.args else ''
        if code in local:
            return code, local[code], 0
    if isinstance(error, (ConnectionError, TimeoutError)):
        return 'NETWORK_ERROR', 'No se pudo conectar con Telegram. Revisa Internet, VPN o proxy e inténtalo después.', 0
    if isinstance(error, RuntimeError) and error.args == ('TELEGRAM_SESSION_IN_USE',):
        return 'SESSION_IN_USE', 'Otro proceso está usando la sesión. Cierra la otra ventana de alta o detén la prueba/conector.', 0
    if isinstance(error, RuntimeError) and error.args == ('TELEGRAM_CONFIG_IN_USE',):
        return 'CONFIG_IN_USE', 'La configuración se está guardando en otra ventana. Inténtalo de nuevo.', 0
    if isinstance(error, PermissionError):
        return 'STORAGE_DENIED', 'Windows no permitió guardar la configuración protegida. Revisa los permisos de la carpeta de Axx.', 0
    if isinstance(error, ModuleNotFoundError):
        return 'DEPENDENCY_MISSING', 'Falta una dependencia del inicio de sesión. Abre esta ventana con el runtime de Telegram de Axx.', 0
    if isinstance(error, OSError):
        return 'SYSTEM_ERROR', 'Falló una operación de red o almacenamiento local. No se confirmó el inicio de sesión.', 0
    return 'SETUP_ERROR', 'No se confirmó el inicio de sesión. Comunica únicamente este código y el paso donde ocurrió.', 0


class Setup:
    def __init__(self, root):
        self.root = root
        self.loop = asyncio.new_event_loop()
        self.events = queue.Queue()
        self.client = None
        self.lease = None
        self.code_hash = None
        self.need_password = False
        self.pending = None
        self.busy = False
        self.active = None
        self.closed = False
        self.retry_at = 0
        self.stage = ''
        threading.Thread(target=self._run_loop, daemon=True, name='telegram-setup').start()
        root.title('Conectar Telegram a Axx · Diagnóstico')
        frame = ttk.Frame(root, padding=16)
        frame.grid(sticky='nsew')
        self.fields = {}
        for row, (name, label, hidden) in enumerate((
                ('api_id', 'API ID', False), ('api_hash', 'API hash', True),
                ('phone', 'Teléfono de la cuenta de Axx', False), ('owner_id', 'ID numérico de tu cuenta', False),
                ('code', 'Código recibido', True), ('password', 'Contraseña de Telegram (verificación en dos pasos)', True))):
            caption = ttk.Label(frame, text=label)
            caption.grid(row=row, column=0, sticky='w', pady=3)
            entry = ttk.Entry(frame, width=40, show='*' if hidden else '')
            entry.grid(row=row, column=1, sticky='ew', pady=3)
            self.fields[name] = entry
            if name == 'password':
                self.password_label = caption
                caption.grid_remove()
                entry.grid_remove()
        self.grants = {}
        labels = {'conversation': 'Conversación', 'voice_notes': 'Notas de voz', 'files': 'Archivos',
                  'pc_commands': 'Acciones en la PC', 'private_calls': 'Llamadas privadas'}
        for i, key in enumerate(GRANTS, start=6):
            var = tk.BooleanVar(value=key == 'conversation')
            ttk.Checkbutton(frame, text=labels[key], variable=var).grid(row=i, column=0, columnspan=2, sticky='w')
            self.grants[key] = var
        self.enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text='Activar canal al guardar', variable=self.enabled).grid(row=11, column=0, columnspan=2, sticky='w')
        self.send_button = ttk.Button(frame, text='Enviar código', command=self.send_code)
        self.send_button.grid(row=12, column=0, sticky='ew', pady=8)
        self.sign_button = ttk.Button(frame, text='Iniciar sesión y guardar', command=self.sign_in, state='disabled')
        self.sign_button.grid(row=12, column=1, sticky='ew', pady=8)
        self.save_button = ttk.Button(frame, text='Guardar permisos', command=self.save_permissions)
        self.status = tk.StringVar(value='Los datos se guardan protegidos en esta PC.')
        ttk.Label(frame, textvariable=self.status, wraplength=440).grid(row=13, column=0, columnspan=2, sticky='w')
        self.existing = False
        if account_path().exists():
            try:
                self._show_existing(load_account())
            except Exception:
                self.status.set('No se pudo abrir la cuenta protegida; no se modificó.')
                self.send_button.configure(state='disabled')
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self._poll)

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
        self.loop.close()

    def _submit(self, coroutine, success, stage):
        self.busy = True
        self.stage = stage
        self.send_button.configure(state='disabled')
        self.sign_button.configure(state='disabled')
        self.save_button.configure(state='disabled')
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        self.active = future
        future.add_done_callback(lambda f: self.events.put((f, success)))

    def _poll(self):
        if self.closed:
            return
        try:
            while True:
                future, success = self.events.get_nowait()
                self.active = None
                self.busy = False
                try:
                    success(future.result())
                except Exception as error:
                    code, message, wait = setup_error(error)
                    if code in ('PHONE_CODE_EXPIRED', 'PHONE_CODE_HASH_EMPTY', 'AUTH_RESTART'):
                        self.code_hash = None
                        self.need_password = False
                    self.retry_at = time.monotonic() + wait
                    self.status.set(f'{self.stage}: {message} [{code}]')
                self.save_button.configure(state='normal' if self.existing else 'disabled')
        except queue.Empty:
            pass
        waiting = self.busy or time.monotonic() < self.retry_at
        if self.need_password and not self.existing:
            self.password_label.grid()
            self.fields['password'].grid()
            self.sign_button.configure(text='Verificar contraseña y guardar')
        else:
            self.password_label.grid_remove()
            self.fields['password'].grid_remove()
            self.sign_button.configure(text='Iniciar sesión y guardar')
        self.send_button.configure(state='disabled' if waiting or self.existing else 'normal')
        self.sign_button.configure(state='normal' if self.code_hash and not self.existing and not waiting else 'disabled')
        self.root.after(100, self._poll)

    def send_code(self):
        if self.busy or time.monotonic() < self.retry_at:
            return
        try:
            api_id = int(self.fields['api_id'].get())
            owner_id = int(self.fields['owner_id'].get())
            api_hash, phone = self.fields['api_hash'].get().strip(), self.fields['phone'].get().strip()
            if not 0 < api_id <= 2147483647 or not 0 < owner_id <= 9223372036854775807 or not re.fullmatch(r'[0-9a-fA-F]{32}', api_hash):
                raise ValueError()
            if not re.fullmatch(r'\+[1-9][0-9]{5,14}', phone):
                self.status.set('Usa el teléfono en formato internacional: +, código de país y número. [PHONE_FORMAT]')
                return
            if account_path().exists():
                self.status.set('Ya existe una cuenta configurada; no se sobrescribirá.')
                return
        except (ValueError, KeyError):
            self.status.set('Revisa API ID, API hash, teléfono e ID del propietario.')
            return
        self.pending = (api_id, api_hash, phone, owner_id)
        self.code_hash = None
        self.need_password = False
        self.status.set('Solicitando código…')
        self._submit(self._send_code(), self._sent, 'Enviar código')

    async def _send_code(self):
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        if self.client:
            await self.client.disconnect()
            self.client = None
        self._release_lease()
        lease = account_lease()
        lease.__enter__()
        self.lease = lease
        api_id, api_hash, phone, _ = self.pending
        try:
            self.client = TelegramClient(StringSession(), api_id, api_hash)
            await self.client.connect()
            sent = await self.client.send_code_request(phone)
            code_hash = getattr(sent, 'phone_code_hash', None)
            if not isinstance(code_hash, str) or not code_hash:
                raise SetupError('AUTH_FLOW_UNSUPPORTED')
            return code_hash
        except BaseException:
            if self.client:
                await self.client.disconnect()
                self.client = None
            self._release_lease()
            raise

    def _release_lease(self):
        if self.lease:
            lease, self.lease = self.lease, None
            lease.__exit__(None, None, None)

    def _sent(self, code_hash):
        self.code_hash = code_hash
        self.status.set('Introduce el código recibido en Telegram para esta solicitud. Solo se pedirá contraseña si Telegram exige verificación en dos pasos.')

    def sign_in(self):
        if self.busy or not self.code_hash or time.monotonic() < self.retry_at:
            return
        code, password = self.fields['code'].get().strip(), self.fields['password'].get()
        if not code and not self.need_password:
            self.status.set('Introduce el código recibido.')
            return
        grants = {key: var.get() for key, var in self.grants.items()}
        self.status.set('Comprobando cuenta…')
        self._submit(self._sign_in(code, password, grants, self.enabled.get()), self._saved, 'Iniciar sesión')

    async def _sign_in(self, code, password, grants, enabled):
        from telethon.errors import SessionPasswordNeededError
        api_id, api_hash, phone, owner_id = self.pending
        if not self.need_password:
            try:
                await self.client.sign_in(phone=phone, code=code, phone_code_hash=self.code_hash)
            except SessionPasswordNeededError:
                self.need_password = True
        if self.need_password:
            if not password:
                raise SetupError('TWO_FACTOR_REQUIRED')
            await self.client.sign_in(password=password)
        me = await self.client.get_me()
        if not me or not getattr(me, 'id', None):
            raise SetupError('ACCOUNT_UNAVAILABLE')
        if getattr(me, 'bot', False):
            raise SetupError('BOT_ACCOUNT')
        if me.id == owner_id:
            raise SetupError('OWNER_IS_ACCOUNT')
        if account_path().exists():
            raise SetupError('ACCOUNT_EXISTS')
        account = {'api_id': api_id, 'api_hash': api_hash, 'session': self.client.session.save(),
                   'account_id': me.id, 'owner_id': owner_id, 'enabled': enabled, 'grants': grants}
        save_account(account, create_only=True)
        await self.client.disconnect()
        self.client = None
        self._release_lease()
        return None

    def _saved(self, _):
        self.code_hash = None
        for field in self.fields.values():
            field.delete(0, 'end')
        self._show_existing(load_account())
        self.status.set('Cuenta guardada localmente. La conexión y las llamadas requieren verificación separada.')

    def _show_existing(self, account):
        self.existing = True
        for field in self.fields.values():
            field.configure(state='disabled')
        self.send_button.configure(state='disabled')
        self.sign_button.configure(state='disabled')
        self.send_button.grid_remove()
        self.sign_button.grid_remove()
        for key, var in self.grants.items():
            var.set(account['grants'][key])
        self.enabled.set(account['enabled'])
        self.save_button.grid(row=12, column=0, columnspan=2, sticky='ew', pady=8)
        self.status.set('Cuenta local configurada. Ajusta los permisos y guarda.')

    def save_permissions(self):
        if self.busy or not self.existing:
            return
        grants = {key: var.get() for key, var in self.grants.items()}
        enabled = self.enabled.get()
        self.status.set('Guardando permisos…')
        self._submit(self._save_permissions(grants, enabled),
                     lambda _: self.status.set('Permisos guardados localmente.'), 'Guardar permisos')

    async def _save_permissions(self, grants, enabled):
        update_permissions(enabled, grants)

    def close(self):
        if self.closed:
            return
        self.closed = True
        async def cleanup():
            try:
                if self.client:
                    await self.client.disconnect()
            finally:
                self._release_lease()
        if self.active:
            self.active.cancel()
        future = asyncio.run_coroutine_threadsafe(cleanup(), self.loop)
        future.add_done_callback(lambda _: self.loop.call_soon_threadsafe(self.loop.stop))
        self.root.destroy()


def main():
    # Telethon errors may include request details; setup never logs credentials.
    logging.disable(logging.CRITICAL)
    root = tk.Tk()
    Setup(root)
    root.mainloop()


if __name__ == '__main__':
    main()
