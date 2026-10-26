"""Source acceptance: real Edge renderer, MCP transport, Windows cursor readback; no clicks."""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.mobile.control import RemoteControl
from backend.mcp_host.native_bridge import NativeMcpBridge
from playwright.sync_api import sync_playwright


def main():
    edge = Path(os.environ['PROGRAMFILES(X86)']) / 'Microsoft/Edge/Application/msedge.exe'
    user = C.WinDLL('user32', use_last_error=True)
    user.SetProcessDPIAware()
    point = W.POINT()
    with sync_playwright() as playwright, tempfile.TemporaryDirectory() as folder:
        browser = playwright.chromium.launch(executable_path=str(edge), headless=True)
        page = browser.new_page()
        page.goto((ROOT/'1.AXX/Axx.html').as_uri())
        page.wait_for_function('() => Boolean(window.Axx?.app?.renderer?.materialTable)', timeout=20000)
        assert page.locator('#mcp-connections').count() == 1
        assert page.locator('#mcp-token').get_attribute('type') == 'password'
        material = page.evaluate('''() => {
            const renderer=Axx.app.renderer, source=renderer.materialTable(), bytes=new Uint8Array(128*128*4);
            for(let y=0;y<128;y++)for(let x=0;x<128;x++){
                const i=(Math.round(y*511/127)*512+Math.round(x*511/127))*4;
                bytes.set(source.subarray(i,i+4),(y*128+x)*4);
            }
            let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
            return {key:renderer.lutKey,table:btoa(binary),reduced:true,size:48,intensity:.9,glow:.12};
        }''')
        executor = ActionExecutor(Path(folder)/'state.db', folder)
        commands, control, bridge = CommandService(executor), RemoteControl(None), NativeMcpBridge()
        executor.input_control, executor.native_bridge = control, bridge
        receipts = []
        original = None
        try:
            bridge._start()
            assert user.GetCursorPos(C.byref(point))
            original = {'x': point.x, 'y': point.y}
            # Use the source renderer's real material through the normal broker admission.
            control.material(material)
            target = {'x': point.x + (12 if point.x < user.GetSystemMetrics(0)-20 else -12), 'y': point.y}
            for identifier, position in [('mcp-pointer-move', target), ('mcp-pointer-restore', original)]:
                control.material(material)
                request = commands.prepare('axx.desktop.pointer.move', position, operation_id=identifier)
                result = commands.execute(request['operation_id'], approved=True)
                receipts.append(result)
                assert result['state'] == 'succeeded', result
                assert result['evidence']['transport'] == 'mcp_streamable_http', result
            assert user.GetCursorPos(C.byref(point))
            assert (point.x, point.y) == (original['x'], original['y'])
            report = {'test': 'native MCP cursor round trip', 'source_only': True, 'renderer': 'source Edge headless',
                      'original': original, 'target': target, 'restored': True, 'receipts': receipts}
            destination = ROOT/'evidence/mcp-expansion-20261026'
            destination.mkdir(exist_ok=True, parents=True)
            (destination/'native-cursor.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({'pass': True, 'restored': True, 'operations': len(receipts), 'installed_verified': False}))
        finally:
            bridge.close(); control.close(); commands.close(); executor.close(); browser.close()


if __name__ == '__main__': main()
