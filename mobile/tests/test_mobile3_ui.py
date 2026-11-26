"""Playwright UI contract tests for AXX Mobile 3.0 live sync, Action Brain, input queues, IME and telemetry."""
import unittest
from playwright.sync_api import sync_playwright
from mobile.tests.test_ui import ROOT, NATIVE_FIXTURE
from mobile.tests.test_control_ui import CONTROL_FIXTURE


LIVE_EVENTS_FIXTURE = NATIVE_FIXTURE + '''
window.liveCursor = 10;
window.queuedEvents = [];
window.eventResolvers = [];
window.pushLiveEvent = (ev) => {
  window.liveCursor++;
  const payload = { ...ev, cursor: window.liveCursor };
  if (window.eventResolvers.length) {
    const resolve = window.eventResolvers.shift();
    resolve({ data: { server_epoch: 'epoch-1', cursor: window.liveCursor, events: [payload], resync_required: false } });
  } else {
    window.queuedEvents.push(payload);
  }
};
window.liveSnapshot = {
  conversation_id: 'shared-live',
  cursor: 10,
  server_epoch: 'epoch-1',
  chat_available: true,
  chat_blocked_reason: null,
  model_status: 'ready',
  always_on: false,
  messages: [{ id: 'm-init', role: 'user', text: 'Inicio', source: 'desktop' }],
  appearance: { settings: { form: 3, palette: 1, scale: 1 }, studio: { living: true }, camera: [0, 0], finish: 'prism' },
  pc_name: 'Mi PC',
  scopes: ['query', 'tools.control', 'input.control'],
  inference: { model: 'qwen3', selection_mode: 'manual' },
  capabilities: { avatar_customization: true, events_stream: true, live_sync: true, action_brain: true }
};
Capacitor.Plugins.AxxTransport.profile = async () => ({
  paired: true, device_id: 'dev-1', endpoint: 'https://192.168.0.10:4443', fingerprint: 'a'.repeat(64), scopes: window.liveSnapshot.scopes
});
const origReq = Capacitor.Plugins.AxxTransport.request;
Capacitor.Plugins.AxxTransport.request = async (args) => {
  if (args.path === '/v1/snapshot') return { data: structuredClone(window.liveSnapshot) };
  if (args.path.startsWith('/v1/events')) {
    if (window.queuedEvents.length) {
      const batch = window.queuedEvents.splice(0, window.queuedEvents.length);
      return { data: { server_epoch: 'epoch-1', cursor: window.liveCursor, events: batch, resync_required: false } };
    }
    return new Promise((resolve) => window.eventResolvers.push(resolve));
  }
  return origReq(args);
};
'''


class Mobile3UITests(unittest.TestCase):
    def _route(self, page):
        page.route('https://axx.test/**', lambda route: route.fulfill(path=str(ROOT / (route.request.url.split('https://axx.test/', 1)[1] or 'index.html'))))

    def test_incremental_events_patch_dom_in_place_and_stream_deltas(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={'width': 390, 'height': 844}, reduced_motion='reduce')
            self._route(page)
            page.add_init_script(LIVE_EVENTS_FIXTURE)
            page.goto('https://axx.test/')
            page.locator('#sync-status[data-state=complete]').wait_for()
            page.locator('[data-pane=chat]').click()
            page.locator('[data-message-id="m-init"]').wait_for()
            # Tag existing DOM node so we verify it is NOT replaced when new messages arrive
            page.evaluate('window.__initNode = document.querySelector(\'[data-message-id="m-init"]\')')
            page.evaluate('pushLiveEvent({ type: "operation.changed", data: { phase: "executing", state: "running", summary: "axx.system.telemetry" } })')
            page.wait_for_function('() => document.querySelector("#command-state").textContent.includes("Ejecutando")')
            page.evaluate('pushLiveEvent({ type: "chat.delta", data: { conversation_id: "shared-live", message_id: "m-stream", delta: "Hola " } })')
            page.evaluate('pushLiveEvent({ type: "chat.delta", data: { conversation_id: "shared-live", message_id: "m-stream", delta: "mundo" } })')
            page.wait_for_function('() => document.querySelector(\'[data-message-id="m-stream"]\')?.textContent.includes("Hola mundo")')
            self.assertTrue(page.evaluate('document.querySelector(\'[data-message-id="m-init"]\') === window.__initNode'))
            self.assertIn('Mantener conexión', page.locator('#connection-detail').inner_text())
            browser.close()

    def test_control_separated_queues_extra_keys_live_ime_telemetry_and_avatar_pause(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={'width': 390, 'height': 844}, reduced_motion='reduce')
            self._route(page)
            page.add_init_script(NATIVE_FIXTURE + CONTROL_FIXTURE)
            page.goto('https://axx.test/')
            page.locator('[data-pane=pc]').click()
            page.locator('#control-open-pad').click()
            page.locator('#control-acquire').click()
            page.locator('#control-stop').wait_for()
            # Avatar pauses while input control is active
            self.assertTrue(page.evaluate('axxAvatarTelemetry().paused_for_input'))
            # Move + immediate click preserves order: move flushed before button down/up
            box = page.locator('#control-pad').bounding_box()
            page.locator('#control-pad').dispatch_event('pointerdown', {'pointerId': 7, 'clientX': box['x'] + 40, 'clientY': box['y'] + 40})
            page.locator('#control-pad').dispatch_event('pointermove', {'pointerId': 7, 'clientX': box['x'] + 60, 'clientY': box['y'] + 50})
            page.locator('#control-left').click()
            page.wait_for_function('() => inputPackets.length >= 1')
            events = page.evaluate('inputPackets.flatMap(p => p.events)')
            types = [e['type'] for e in events]
            self.assertIn('move', types)
            self.assertIn('button', types)
            self.assertLess(types.index('move'), types.index('button'))
            # Extra function key F5 works
            page.locator('[data-control-mode=keyboard]').click()
            page.locator('#control-extra-keys summary').click()
            page.locator('[data-extra-key=F5]').click()
            page.wait_for_function('() => inputPackets.some(p => p.events.some(e => e.key === "F5"))')
            # Live IME commits composed Unicode text cleanly
            page.locator('#control-live-ime').check()
            page.evaluate('''() => {
              const ta = document.querySelector('#control-text');
              ta.dispatchEvent(new Event('compositionstart'));
              ta.value = 'acción';
              ta.dispatchEvent(new Event('input'));
              ta.dispatchEvent(new Event('compositionend'));
            }''')
            page.wait_for_function('() => inputPackets.some(p => p.events.some(e => e.type === "text" && e.text === "acción"))')
            # Telemetry records samples
            telemetry = page.evaluate('axxControlTelemetry()')
            self.assertGreaterEqual(telemetry['count'], 3)
            page.locator('#control-stop').click()
            self.assertFalse(page.evaluate('axxAvatarTelemetry().paused_for_input'))
            browser.close()


if __name__ == '__main__':
    unittest.main()
