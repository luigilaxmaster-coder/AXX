"""PC-only Telegram management; the native host checks authentication first."""
from backend.telegram.bot import bot_request
from backend.telegram.bot_config import load_bot, save_bot
from backend.telegram.config import load_account


class TelegramHTTP:
    def __init__(self, handler):
        self.h = handler

    def _services(self):
        manager = getattr(self.h, 'telegram_desktop', None)
        pairing = getattr(self.h, 'telegram_pairing', None)
        if manager is None or pairing is None:
            raise ValueError('TELEGRAM_MANAGEMENT_UNAVAILABLE')
        return manager, pairing

    def get(self, path):
        if path not in ('/axx-api/telegram/desktop/status', '/axx-api/telegram/pairing/status'):
            return False
        manager, pairing = self._services()
        if path.endswith('/desktop/status'):
            result = manager.status()
        else:
            try:
                account = load_account(manager.data_dir)
                result = pairing.status(account) if account['enabled'] else {'pending': [], 'bindings': []}
            except FileNotFoundError:
                result = {'pending': [], 'bindings': []}
        self.h._send_json(200, result)
        return True

    def post(self, path, body):
        if not (path.startswith('/axx-api/telegram/desktop/') or path.startswith('/axx-api/telegram/pairing/')):
            return False
        if not isinstance(body, dict):
            raise ValueError('Invalid Telegram management request')
        manager, pairing = self._services()
        action = path.rsplit('/', 1)[-1]
        if path.startswith('/axx-api/telegram/desktop/'):
            if action in ('pause', 'update_permissions'):
                if action == 'pause' and body:
                    raise ValueError('Unsupported Telegram management fields')
                if action == 'update_permissions':
                    value = manager.validate_permissions(body)
                account = load_account(manager.data_dir)
                changed = action == 'pause' or value['enabled'] != account['enabled'] or value['grants'] != account['grants']
                if account['enabled'] and changed:
                    pairing.revoke_all(account)
            with_body = {'configure_app': manager.configure_app, 'start_qr': manager.start_qr,
                         'configure_confirmations': manager.configure_confirmations,
                         'password': manager.password, 'configure_bot': manager.configure_bot,
                         'update_permissions': manager.update_permissions}
            without_body = {'cancel': manager.cancel, 'pause': manager.pause, 'resume': manager.resume}
            if action in with_body:
                result = with_body[action](body)
            elif action in without_body and not body:
                result = without_body[action]()
            else:
                raise ValueError('Unsupported Telegram management action')
        else:
            account = load_account(manager.data_dir)
            if action == 'create' and not body:
                bot = load_bot(manager.data_dir)
                if not bot['enabled']:
                    raise ValueError('TELEGRAM_BOT_DISABLED')
                if not bot.get('username'):
                    me = bot_request(bot['token'], 'getMe', {})
                    if not isinstance(me, dict) or me.get('is_bot') is not True:
                        raise ValueError('TELEGRAM_BOT_NOT_VERIFIED')
                    bot['username'] = me.get('username')
                    save_bot(bot, manager.data_dir)
                result = pairing.create_pairing(account, bot['username'])
            elif action == 'revoke' and set(body) == {'binding_id'}:
                result = {'revoked': pairing.revoke(account, body['binding_id'])}
            elif action == 'revoke_all' and not body:
                result = {'revoked': pairing.revoke_all(account)}
            else:
                raise ValueError('Unsupported Telegram pairing action')
        self.h._send_json(200, result)
        return True
