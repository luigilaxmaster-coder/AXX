"""Small browser check for the Convertidor entry and panel."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import io

from playwright.sync_api import sync_playwright
from PIL import Image


root = Path(__file__).resolve().parents[1]
server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(root)))
thread = Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(f'http://127.0.0.1:{server.server_port}/Axx.html')
        page.wait_for_function('window.Axx?.converter && window.Axx?.flow')
        page.evaluate("Axx.flow.showQuick()")
        assert page.locator('#flow-fan [data-quick="converter"]').count() == 1
        boxes = page.locator('#flow-fan [data-quick]').evaluate_all("nodes => nodes.map(node => {const box=node.getBoundingClientRect();return {x:box.x,y:box.y,width:box.width,height:box.height};})")
        for index, left in enumerate(boxes):
            for right in boxes[index + 1:]:
                assert left['x'] + left['width'] <= right['x'] or right['x'] + right['width'] <= left['x'] or left['y'] + left['height'] <= right['y'] or right['y'] + right['height'] <= left['y']
        page.evaluate("Axx.flow.select('converter')")
        assert page.locator('#view-converter').is_visible()
        assert page.locator('#cv-run').is_disabled()
        page.evaluate("""() => {
            Axx.isNative = () => true;
            window.cvCalls = [];
            Axx.backendRequest = async (_, path, body) => {
                cvCalls.push({path, body});
                if (path.endsWith('/new')) return {id:'a'.repeat(32), state:'uploading', output_directory:'C:/Axx/converter/job'};
                if (path.endsWith('/upload')) return {received:body.offset + atob(body.data).length};
                if (path.endsWith('/probe')) return {id:'a'.repeat(32), state:'ready', output_directory:'C:/Axx/converter/job', info:[{name:'sample.png',kind:'png',width:2,height:1,sha256:'f'.repeat(64)}]};
                if (path.endsWith('/run')) return {id:'a'.repeat(32), state:'running', stage:'Convirtiendo'};
                if (path.endsWith('/status')) return {id:'a'.repeat(32), state:'done', stage:'Resultado verificado', result:{name:'convertido.jpg',path:'C:/Axx/converter/job/convertido.jpg',size:600,sha256:'e'.repeat(64)}};
            };
        }""")
        image = io.BytesIO()
        Image.new('RGBA', (2, 1), (0, 0, 255, 0)).save(image, format='PNG')
        page.locator('#cv-files').set_input_files({'name':'sample.png', 'mimeType':'image/png', 'buffer':image.getvalue()})
        page.wait_for_function("document.querySelector('#cv-run').disabled === false")
        page.locator('#cv-run').click()
        page.wait_for_function("document.querySelector('#cv-result').hidden === false")
        assert page.evaluate("cvCalls.some(call => call.path.endsWith('/upload'))")
        assert not errors, errors
        browser.close()
finally:
    server.shutdown()
    server.server_close()
