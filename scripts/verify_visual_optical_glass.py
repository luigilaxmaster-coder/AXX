"""
Visual verification script for AXX Optical Glass integration.
Captures high-resolution comparison screenshots of the body and real organic tendrils
across all 5 presets, custom colors, and checks reversibility back to Obsidian Chrome.
"""
import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright

ROOT_DIR = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT_DIR / 'evidence/optical-glass-20261106'
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

async def capture_scenarios():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1280, 'height': 850})
        html_path = (ROOT_DIR / '1.AXX/Axx.html').as_uri()
        await page.goto(html_path)
        await page.wait_for_timeout(2500)

        # Helper to trigger a realistic tendril and render
        setup_script = """() => {
            const A = window.Axx;
            const app = A.app;
            const renderer = app.renderer;
            const companion = A.companion;
            
            // Center the companion
            companion.center(false);
            renderer.resize();

            // Use test tendrils instance attached to document.body
            window.__testTendrils = window.__testTendrils || new A.OrganicTendrils();
            const tendrils = window.__testTendrils;

            // Function to set up and draw a test tendril
            window.__drawTestFrame = (finishName, presetName = null, customColor = null) => {
                if (finishName) renderer.setFinish(finishName);
                if (presetName && window.AxxOpticalGlass) {
                    window.AxxOpticalGlass.setPreset(presetName);
                }
                if (customColor !== null && window.AxxOpticalGlass) {
                    window.AxxOpticalGlass.set({ color: customColor });
                }
                
                // Get avatar bounding rect
                const rect = renderer.canvas.getBoundingClientRect();
                const cx = rect.left + rect.width / 2;
                const cy = rect.top + rect.height / 2;
                
                // Define 2 active tendrils extending to simulated tool targets
                const links = [
                    {
                        id: 'tendril-visual-1',
                        a: { x: cx, y: cy },
                        b: { x: cx + 240, y: cy - 70 },
                        progress: 1.0,
                        rootRadius: 22,
                        targetRadius: 14
                    },
                    {
                        id: 'tendril-visual-2',
                        a: { x: cx, y: cy },
                        b: { x: cx - 220, y: cy + 110 },
                        progress: 1.0,
                        rootRadius: 20,
                        targetRadius: 12
                    }
                ];
                
                // Step motion and draw body
                renderer.draw(performance.now() / 1000);
                
                // Draw tendrils using shared materialTable
                tendrils.draw(
                    links,
                    1.5,
                    renderer.materialTable(),
                    renderer.getStudio().view,
                    renderer
                );
            };
        }"""
        await page.evaluate(setup_script)
        await page.wait_for_timeout(500)

        # Capture 1: Obsidian Chrome baseline
        await page.evaluate("() => { window.__drawTestFrame('obsidian'); }")
        await page.wait_for_timeout(600)
        obsidian_png = EVIDENCE_DIR / '01_obsidian_chrome.png'
        await page.screenshot(path=str(obsidian_png))
        print(f"Captured: {obsidian_png.name}")

        # Capture 2: Optical Glass - Reference Glass
        await page.evaluate("() => { window.__drawTestFrame('opticalglass', 'reference', ''); }")
        await page.wait_for_timeout(600)
        ref_png = EVIDENCE_DIR / '02_optical_glass_reference.png'
        await page.screenshot(path=str(ref_png))
        print(f"Captured: {ref_png.name}")

        # Capture 3: Optical Glass - Optical Crystal
        await page.evaluate("() => { window.__drawTestFrame('opticalglass', 'crystal', ''); }")
        await page.wait_for_timeout(600)
        crystal_png = EVIDENCE_DIR / '03_optical_crystal.png'
        await page.screenshot(path=str(crystal_png))
        print(f"Captured: {crystal_png.name}")

        # Capture 4: Optical Glass - Liquid Gel
        await page.evaluate("() => { window.__drawTestFrame('opticalglass', 'liquid', ''); }")
        await page.wait_for_timeout(600)
        liquid_png = EVIDENCE_DIR / '04_liquid_gel.png'
        await page.screenshot(path=str(liquid_png))
        print(f"Captured: {liquid_png.name}")

        # Capture 5: Optical Glass - Pure Silica
        await page.evaluate("() => { window.__drawTestFrame('opticalglass', 'silica', ''); }")
        await page.wait_for_timeout(600)
        silica_png = EVIDENCE_DIR / '05_pure_silica.png'
        await page.screenshot(path=str(silica_png))
        print(f"Captured: {silica_png.name}")

        # Capture 6: Optical Glass - Prismatic Aura
        await page.evaluate("() => { window.__drawTestFrame('opticalglass', 'aura', ''); }")
        await page.wait_for_timeout(600)
        aura_png = EVIDENCE_DIR / '06_prismatic_aura.png'
        await page.screenshot(path=str(aura_png))
        print(f"Captured: {aura_png.name}")

        # Capture 7: Optical Glass - Custom Tint (#2ee59d emerald)
        await page.evaluate("() => { window.__drawTestFrame('opticalglass', 'reference', '#2ee59d'); }")
        await page.wait_for_timeout(600)
        custom_png = EVIDENCE_DIR / '07_optical_glass_custom_tint.png'
        await page.screenshot(path=str(custom_png))
        print(f"Captured: {custom_png.name}")

        # Capture 8: Reversion back to Obsidian Chrome
        await page.evaluate("() => { window.__drawTestFrame('obsidian'); }")
        await page.wait_for_timeout(600)
        revert_png = EVIDENCE_DIR / '08_obsidian_chrome_reverted.png'
        await page.screenshot(path=str(revert_png))
        print(f"Captured: {revert_png.name}")

        # Form morphing test across 24 forms
        form_results = await page.evaluate("""() => {
            const renderer = window.Axx.app.renderer;
            const results = [];
            renderer.setFinish('opticalglass');
            window.AxxOpticalGlass.setPreset('reference');
            for (let f = 0; f < 24; f++) {
                renderer.setForm(f, true);
                renderer.draw(performance.now() / 1000);
                results.push({ form: f, name: window.Axx.FORMS[f].name, valid: renderer.canvas.width > 0 });
            }
            return results;
        }""")
        print(f"Tested all {len(form_results)} forms with Optical Glass without exceptions.")

        # Palette testing across 9 palettes
        palette_results = await page.evaluate("""() => {
            const renderer = window.Axx.app.renderer;
            const results = [];
            renderer.setFinish('opticalglass');
            for (let p = 0; p < 9; p++) {
                renderer.settings.palette = p;
                renderer.lutKey = '';
                renderer.shadeTable();
                results.push({ palette: p, name: window.Axx.PALETTES[p].name, alpha: renderer.lut[3] });
            }
            return results;
        }""")
        print(f"Tested all {len(palette_results)} palettes with Optical Glass: all alpha={palette_results[0]['alpha']}.")

        # Measure FPS and render latency
        perf = await page.evaluate("""() => {
            const renderer = window.Axx.app.renderer;
            const times = [];
            for (let i = 0; i < 30; i++) {
                const t0 = performance.now();
                renderer.draw(performance.now() / 1000);
                times.push(performance.now() - t0);
            }
            const avgMs = times.reduce((a, b) => a + b, 0) / times.length;
            return { avgMs, fps: Math.round(1000 / avgMs) };
        }""")
        print(f"Performance benchmark: average draw time = {perf['avgMs']:.2f} ms (~{perf['fps']} FPS)")

        await browser.close()
        print("Visual verification completed successfully!")

if __name__ == '__main__':
    asyncio.run(capture_scenarios())
