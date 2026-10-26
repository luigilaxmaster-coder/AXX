import os
from pathlib import Path
import unittest


@unittest.skipUnless(os.environ.get('AXX_TEST_BROWSER_NATIVE') == '1', 'requires isolated native Edge')
class McpUiTests(unittest.TestCase):
    def test_existing_dock_entry_configuration_and_untrusted_catalog(self):
        from playwright.sync_api import sync_playwright
        root = Path(__file__).resolve().parents[2]
        edge = Path(os.environ['PROGRAMFILES(X86)'])/'Microsoft/Edge/Application/msedge.exe'
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=str(edge), headless=True)
            try:
                page = browser.new_page(viewport={'width':1280, 'height':900})
                page.goto((root/'1.AXX/Axx.html').as_uri())
                page.wait_for_function('() => Boolean(Axx.mcpConnections)')
                page.evaluate('''() => {
                    window.mcpFixture={calls:[],connections:[]}; Axx.isNative=()=>true;
                    Axx.backendRequest=async (method,path,body)=>{
                        const f=mcpFixture; f.calls.push({method,path,body:structuredClone(body)});
                        if(path.endsWith('/add')) f.connections.push({id:'fixture', name:'<img src=x onerror="window.injected=true">',
                            context:'UI contract fixture', endpoint:body.url, status:'disconnected', tools:[]});
                        return {connections:f.connections,native_windows:{mode:'gateway',state:'verified'}};
                    };
                    Axx.mcpConnections.open();
                }''')
                self.assertEqual(page.evaluate('Axx.companion.dock.selected'), 'mcp')
                page.wait_for_function('() => document.getElementById("mcp-native-status").textContent.includes("última operación comprobada")')
                self.assertEqual(page.locator('#mcp-name').evaluate('(e)=>getComputedStyle(e.parentElement).display'), 'grid')
                self.assertGreater(page.locator('#mcp-name').bounding_box()['width'], 250)
                page.locator('#mcp-name').fill('Fixture')
                page.locator('#mcp-context').fill('UI contract fixture')
                page.locator('#mcp-url').fill('https://example.test/mcp')
                page.locator('#mcp-token').fill('test-only-input-not-an-authenticated-credential')
                page.locator('#mcp-add').click()
                page.wait_for_function('() => document.getElementById("mcp-list").textContent.includes("<img")')
                self.assertEqual(page.locator('#mcp-token').input_value(), '')
                self.assertEqual(page.locator('#mcp-list img').count(), 0)
                self.assertFalse(page.evaluate('Boolean(window.injected)'))
                self.assertFalse(page.evaluate('mcpFixture.calls.some(c=>c.path.endsWith("/probe"))'))
                page.evaluate('''() => { Axx.backendRequest=async()=>{throw new Error('fixture rejection')}; }''')
                page.locator('#mcp-token').fill('test-only-input')
                page.locator('#mcp-add').click()
                page.wait_for_function('() => document.getElementById("mcp-status").textContent.includes("fixture rejection")')
                self.assertEqual(page.locator('#mcp-token').input_value(), '')
            finally: browser.close()
