"""Typed CDP access to an explicitly prepared loopback browser, never a default profile."""
from __future__ import annotations

from collections import deque
import hashlib
import json
import os
import re
import threading
import time
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler

MAX_RESPONSE = 8 * 1024 * 1024
MAX_NODES = 300


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('CDP endpoint redirects are not allowed')


def configuration():
    endpoint = os.environ.get('AXX_BROWSER_CDP_URL', '')
    label = os.environ.get('AXX_BROWSER_PROFILE_LABEL', '')
    if not endpoint or not label:
        raise ValueError('browser_unavailable: configure AXX_BROWSER_CDP_URL and AXX_BROWSER_PROFILE_LABEL for a prepared browser')
    url = urlsplit(endpoint)
    if (url.scheme != 'http' or url.hostname not in ('127.0.0.1', '::1') or not url.port
            or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment
            or not 1 <= len(label) <= 120 or any(ord(c) < 32 for c in label)):
        raise ValueError('Browser CDP configuration must be a literal loopback HTTP origin with an explicit port and profile label')
    return endpoint.rstrip('/'), label


def _document_url(raw, initial=False):
    if initial and raw == 'about:blank':
        return raw
    from .desktop import validate_url
    validate_url(raw)
    return raw


def _same_url(left, right):
    if left == right:
        return True
    def key(raw):
        url = urlsplit(raw)
        return url.scheme, url.hostname, url.port or (443 if url.scheme == 'https' else 80), url.path or '/', url.query, url.fragment
    return key(left) == key(right)


def validate_inputs(kind, inputs):
    if not isinstance(inputs, dict):
        raise ValueError('Browser parameters must be an object')
    keys = set() if kind == 'tabs' else {'tab_id', 'expected_url', 'browser_session'}
    if kind == 'navigate':
        keys |= {'document_id', 'url'}
    if kind not in ('tabs', 'inspect', 'navigate') or set(inputs) != keys:
        raise ValueError('Browser operation requires exactly its typed fields')
    if kind != 'tabs':
        if not isinstance(inputs['tab_id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', inputs['tab_id']):
            raise ValueError('Invalid observed tab ID')
        if not isinstance(inputs['browser_session'], str) or not re.fullmatch(r'[a-f0-9]{64}', inputs['browser_session']):
            raise ValueError('A browser_session from current tab discovery is required')
        _document_url(inputs['expected_url'], initial=True)
    if kind == 'navigate':
        if not isinstance(inputs['document_id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', inputs['document_id']):
            raise ValueError('A document_id from current inspection is required')
        _document_url(inputs['url'])


def _json(endpoint, path):
    with build_opener(ProxyHandler({}), _NoRedirect()).open(endpoint + path, timeout=4) as response:
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError('CDP discovery response exceeds the limit')
    return json.loads(data)


def _socket_url(raw, endpoint, path):
    if not isinstance(raw, str):
        raise ValueError('Browser did not advertise a WebSocket target')
    url, origin = urlsplit(raw), urlsplit(endpoint)
    if (url.scheme != 'ws' or url.hostname != origin.hostname or url.port != origin.port
            or url.username or url.password or url.query or url.fragment or not re.fullmatch(path, url.path)):
        raise ValueError('Advertised CDP target does not belong to the configured browser')
    return raw


def discover():
    endpoint, label = configuration()
    version = _json(endpoint, '/json/version')
    socket_url = _socket_url(version.get('webSocketDebuggerUrl'), endpoint, r'/devtools/browser/[A-Za-z0-9_-]+')
    rows = _json(endpoint, '/json/list')
    if not isinstance(rows, list) or len(rows) > 200:
        raise ValueError('Browser tab inventory is invalid or exceeds 200 targets')
    tabs = []
    for row in rows:
        if not isinstance(row, dict) or row.get('type') != 'page':
            continue
        tab_id = row.get('id')
        if not isinstance(tab_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', tab_id):
            raise ValueError('Browser advertised an invalid tab identity')
        try:
            _document_url(row.get('url'), initial=True)
        except (ValueError, TypeError):
            continue
        target = _socket_url(row.get('webSocketDebuggerUrl'), endpoint, '/devtools/page/' + re.escape(tab_id))
        tabs.append({'tab_id': tab_id, 'title': str(row.get('title', ''))[:500], 'url': row['url'], '_socket': target})
    return {'browser_session': hashlib.sha256(socket_url.encode()).hexdigest(),
            'configured_profile_label': label, 'browser_version': str(version.get('Browser', 'unknown'))[:120],
            'tabs': tabs, 'observed_at': time.time(), 'scope': 'explicitly_configured_cdp_browser'}


class _Connection:
    def __init__(self, url, cancelled, timeout=15):
        import websocket
        self.cancelled, self.deadline, self.sequence = cancelled, time.monotonic() + timeout, 0
        self.events = deque(maxlen=100)
        self.socket = websocket.create_connection(url, timeout=1, suppress_origin=True,
                                                  http_no_proxy=['127.0.0.1', '::1'], enable_multithread=True)

    def close(self):
        try:
            self.socket.close(timeout=1)
        except OSError:
            pass

    def _receive(self):
        import websocket
        while time.monotonic() < self.deadline:
            if self.cancelled.is_set():
                raise ValueError('Browser operation cancelled')
            try:
                raw = self.socket.recv()
            except websocket.WebSocketTimeoutException:
                continue
            if not isinstance(raw, str) or len(raw) > MAX_RESPONSE:
                raise ValueError('Browser response is unavailable or exceeds the bounded response size')
            message = json.loads(raw)
            if not isinstance(message, dict):
                raise ValueError('Invalid CDP message')
            if 'method' in message:
                self.events.append(message)
            return message
        raise TimeoutError('Browser operation exceeded its deadline')

    def call(self, method, params=None):
        if self.cancelled.is_set():
            raise ValueError('Browser operation cancelled')
        self.sequence += 1
        self.socket.send(json.dumps({'id': self.sequence, 'method': method, 'params': params or {}}))
        while True:
            result = self._receive()
            if result.get('id') == self.sequence:
                if 'error' in result:
                    raise ValueError('CDP rejected ' + method + ': ' + str(result['error'].get('message', 'unknown'))[:300])
                return result.get('result', {})


def _frame(connection):
    frame = connection.call('Page.getFrameTree').get('frameTree', {}).get('frame', {})
    if not frame.get('id') or not frame.get('loaderId') or not frame.get('url'):
        raise ValueError('Browser document identity is unavailable')
    return frame


class BrowserBridgeTool:
    version = '1.0.0'

    def __init__(self, kind):
        if kind not in ('tabs', 'inspect', 'navigate'):
            raise ValueError('Unsupported typed browser operation')
        self.kind, self.name = kind, 'browser_' + kind
        self.description = 'Prepared local browser: ' + kind + ', pinned to observed session, tab and document'

    def verify_preconditions(self, inputs):
        try:
            validate_inputs(self.kind, inputs)
            configuration()
            import websocket
            return True, 'Typed browser target and configured transport validated'
        except (ValueError, TypeError, ImportError) as exc:
            return False, str(exc)

    def execute(self, inputs):
        return self.execute_cancellable(inputs, None, threading.Event())

    def execute_in_workspace(self, inputs, workspace_root):
        return self.execute(inputs)

    def execute_cancellable(self, inputs, workspace_root, cancelled):
        from .tools import ToolResult
        connection, dispatched, output = None, False, None
        try:
            validate_inputs(self.kind, inputs)
            if cancelled.is_set():
                raise ValueError('Browser operation cancelled before observation')
            inventory = discover()
            if self.kind == 'tabs':
                output = {**inventory, 'tabs': [{k: v for k, v in row.items() if k != '_socket'} for row in inventory['tabs']]}
                return ToolResult(True, output=output, evidence={'verification': 'configured_browser_inventory'})
            if inventory['browser_session'] != inputs['browser_session']:
                raise ValueError('Browser session changed; discover tabs again')
            targets = [row for row in inventory['tabs'] if row['tab_id'] == inputs['tab_id']]
            if len(targets) != 1 or not _same_url(targets[0]['url'], inputs['expected_url']):
                raise ValueError('Observed tab or URL changed; inspect the current target')
            connection = _Connection(targets[0]['_socket'], cancelled)
            before = _frame(connection)
            if not _same_url(before['url'], inputs['expected_url']):
                raise ValueError('Document navigated before dispatch')
            output = {'browser_session': inventory['browser_session'], 'configured_profile_label': inventory['configured_profile_label'],
                      'tab_id': inputs['tab_id'], 'url': before['url'], 'document_id': before['loaderId'], 'observed_at': time.time()}
            if self.kind == 'inspect':
                nodes = connection.call('Accessibility.getFullAXTree', {'depth': 5, 'frameId': before['id']}).get('nodes', [])
                after = _frame(connection)
                if before['loaderId'] != after['loaderId'] or before['url'] != after['url']:
                    raise ValueError('Document changed during accessibility observation')
                readable = [node for node in nodes if not node.get('ignored')]
                observed_ids = {node.get('nodeId') for node in nodes}
                depth_limited = any(child not in observed_ids for node in nodes for child in node.get('childIds', []))
                output.update(elements=[{'role': node.get('role', {}).get('value', ''),
                                         'name': str(node.get('name', {}).get('value', ''))[:500],
                                         'value': str(node.get('value', {}).get('value', ''))[:500],
                                         'backend_node_id': node.get('backendDOMNodeId')}
                                        for node in readable[:MAX_NODES]],
                              truncated=len(readable) > MAX_NODES or depth_limited, tree_depth=5, trust='observed_content_untrusted')
                return ToolResult(True, output=output, evidence={'verification': 'stable_document_accessibility', 'document_id': before['loaderId']})
            if before['loaderId'] != inputs['document_id']:
                raise ValueError('Document identity changed; inspect again before navigation')
            connection.call('Page.enable')
            connection.call('Page.setLifecycleEventsEnabled', {'enabled': True})
            current = _frame(connection)
            if current['loaderId'] != before['loaderId'] or current['url'] != before['url']:
                raise ValueError('Document changed at navigation dispatch boundary')
            dispatched = True
            result = connection.call('Page.navigate', {'url': inputs['url'], 'frameId': before['id']})
            if result.get('errorText') or result.get('isDownload'):
                raise ValueError(result.get('errorText') or 'Navigation initiated a download; its file has not been verified')
            loader_id = result.get('loaderId')
            if not loader_id:
                raise ValueError('No new document identity returned; navigation effect requires inspection')
            while True:
                loaded = any(event.get('method') == 'Page.lifecycleEvent' and event.get('params', {}).get('loaderId') == loader_id
                             and event.get('params', {}).get('name') == 'DOMContentLoaded' for event in connection.events)
                if loaded:
                    break
                connection._receive()
            after = _frame(connection)
            output.update(url=after['url'], document_id=after['loaderId'])
            if after['loaderId'] != loader_id or not _same_url(after['url'], inputs['url']):
                raise ValueError('Navigation redirected or document changed; requested destination not confirmed')
            return ToolResult(True, output=output, evidence={'verification': 'browser_document_navigation', 'expected_url': inputs['url'],
                              'document_id': loader_id, 'dom_content_loaded': True})
        except Exception as exc:
            return ToolResult(False, output=output, error=str(exc)[:600], evidence={'cancelled': cancelled.is_set(),
                              'effect_uncertain': dispatched, 'dispatch_status': 'unknown' if dispatched else 'rejected',
                              'effect_status': 'unknown' if dispatched else 'not_observed'})
        finally:
            if connection:
                connection.close()

    def verify_postconditions(self, inputs, result):
        if not result.success:
            return False, result.error or 'Browser operation failed'
        valid = self.kind != 'navigate' or (result.evidence.get('dom_content_loaded') is True
                and _same_url(result.output.get('url', ''), inputs['url'])
                and result.output.get('document_id') == result.evidence.get('document_id'))
        return bool(valid), 'Observed browser state verified' if valid else 'Navigation outcome not confirmed'
