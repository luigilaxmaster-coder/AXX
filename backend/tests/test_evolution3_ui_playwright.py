"""Playwright DOM and UI controller test for AXX Evolution 3.0 in 1.AXX/Axx.html."""
from __future__ import annotations

import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class Evolution3UiPlaywrightTests(unittest.TestCase):
    @unittest.skipUnless(PLAYWRIGHT_AVAILABLE, 'playwright is not installed')
    def test_axx_html_loads_all_evolution3_controllers_and_theme_without_avatar_regression(self) -> None:
        root_dir = Path(__file__).resolve().parents[2]
        html_file = root_dir / '1.AXX' / 'Axx.html'
        self.assertTrue(html_file.is_file(), f'Axx.html not found at {html_file}')

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={'width': 1280, 'height': 800})
                page.goto(html_file.resolve().as_uri(), wait_until='domcontentloaded')

                res = page.evaluate("""() => {
                    const Axx = window.Axx;
                    if (!Axx || !Axx.evolution3) {
                        return { error: 'Axx.evolution3 missing' };
                    }
                    const formsCount = Array.isArray(Axx.FORMS) ? Axx.FORMS.length : 0;
                    const palettesCount = Array.isArray(Axx.PALETTES) ? Axx.PALETTES.length : 0;
                    const originalForm = Axx.app?.store?.data?.settings?.form || 'Core';

                    const ctrl = Axx.evolution3.controllers || {};
                    const controllerKeys = Object.keys(ctrl).filter((k) => Boolean(ctrl[k]));

                    const themeLink = document.getElementById('axx-evolution-theme-link');

                    // Mount Agent Designer preview
                    const host = document.createElement('div');
                    document.body.appendChild(host);
                    const designer = ctrl.agentDesigner.createAgentDesigner({ container: host });
                    designer.mount({
                        agent_id: 'ui-test-agent',
                        name: 'UI Test Agent',
                        role: 'coder',
                        appearance: { form_id: 0, palette_id: 0, material_preset: 'obsidian' },
                    });
                    const tabCount = host.querySelectorAll('[role="tab"]').length;
                    designer.setAppearanceDraft(17, 5, 'optical_glass');
                    const previewBtn = [...host.querySelectorAll('button')].find((b) => b.textContent === 'Previsualizar');
                    if (previewBtn) previewBtn.click();
                    const previewActive = designer.isPreviewActive();
                    const globalFormDuringPreview = Axx.app?.store?.data?.settings?.form || 'Core';
                    const discardBtn = [...host.querySelectorAll('button')].find((b) => b.textContent === 'Descartar');
                    if (discardBtn) discardBtn.click();
                    designer.unmount();

                    // Mount Diagram Editor
                    const diagEditor = ctrl.diagramEditor.createDiagramEditor({ container: host });
                    diagEditor.mount({
                        style_template: 'obsidian_spatial',
                        nodes: [{ id: 'n1', label: 'Node 1', bounds: [0.1, 0.1, 0.2, 0.1] }],
                        edges: [],
                    });
                    diagEditor.selectNode('n1');
                    const moved = diagEditor.moveSelectedNode(0.04, 0.02);
                    diagEditor.unmount();

                    // Mount Code Workspace
                    ctrl.codeWorkspace.mount();
                    const tab = ctrl.codeWorkspace.openDocumentTab({
                        path: 'src/main.py',
                        project_id: 'p1',
                        sha256: 'a'.repeat(64),
                        encoding: 'utf-8',
                        line_ending: 'LF',
                        content: 'print("hello")\\n',
                    });
                    ctrl.codeWorkspace.updateTabContent('src/main.py', 'print("updated")\\n');
                    const tabDirty = tab.dirty;
                    ctrl.codeWorkspace.unmount();

                    host.remove();

                    return {
                        ok: true,
                        formsCount,
                        palettesCount,
                        originalForm,
                        globalFormDuringPreview,
                        controllerCount: controllerKeys.length,
                        tabCount,
                        previewActive,
                        movedOk: Boolean(moved),
                        tabDirty,
                        hasTheme: Boolean(themeLink),
                    };
                }""")

                self.assertTrue(res.get('ok'), res.get('error'))
                self.assertEqual(res['formsCount'], 24, 'Avatar must retain all 24 canonical forms')
                self.assertEqual(res['palettesCount'], 9, 'Avatar must retain all 9 canonical palettes')
                self.assertEqual(res['originalForm'], res['globalFormDuringPreview'], 'Previewing agent appearance must never mutate global avatar settings')
                self.assertEqual(res['controllerCount'], 21, 'All 21 evolution controllers must be registered')
                self.assertEqual(res['tabCount'], 10, 'Agent designer must provide all 10 specification tabs')
                self.assertTrue(res['previewActive'])
                self.assertTrue(res['movedOk'])
                self.assertTrue(res['tabDirty'])
                self.assertTrue(res['hasTheme'], 'Aesthetic Apple x Google Design x100 theme link must be active in DOM')
            finally:
                browser.close()
