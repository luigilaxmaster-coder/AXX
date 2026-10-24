// Native regression: opening chat must not redirect search keystrokes into a draft.
const fs = require('fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.USERPROFILE + '/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

(async () => {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9224');
  const page = browser.contexts()[0].pages().find(p => p.url().includes('Axx.html'));
  const receipt = { kind: 'INSTALLED_CHAT_FOCUS', cases: [] };
  let original, scratch;
  try {
    await page.waitForFunction(() => Axx.chatWorkspace?.ready && !Axx.chatWorkspace.busy);
    original = await page.evaluate(() => Axx.chatWorkspace.active.id);
    await page.evaluate(() => Axx.chatWorkspace.flush());
    scratch = await page.evaluate(() => Axx.backendRequest('POST', '/axx-api/chat/create', { title: 'Aceptación · foco del buscador' }));
    await page.evaluate(id => { Axx.resident.summon(false); Axx.companion.openChat(); return Axx.chatWorkspace.select(id); }, scratch.id);
    await page.locator('#chat-input').fill('Este borrador debe conservarse íntegro.');
    await page.evaluate(() => Axx.chatWorkspace.flush());
    if (await page.locator('#cw-browse').isVisible()) await page.locator('#cw-browse').click();
    await page.locator('#cw-search').waitFor({ state: 'visible' });
    for (let index = 0; index < 8; index++) {
      if (index >= 6) await page.evaluate(() => Axx.companion.openFeature('settings'));
      await page.evaluate(() => Axx.companion.openChat());
      await page.locator('#cw-search').focus();
      await page.keyboard.press('Control+A');
      await page.keyboard.press('Backspace');
      await page.keyboard.type('Aceptación');
      // Inspect after both former 50/70ms timers would have fired, without
      // delaying the initial keyboard input that exposed the race.
      await page.waitForTimeout(180);
      const state = await page.evaluate(() => ({
        search: document.getElementById('cw-search').value,
        focus: document.activeElement.id,
        draft: document.getElementById('chat-input').value,
      }));
      receipt.cases.push({ index, transition: index >= 6, ...state });
      assert.equal(state.search, 'Aceptación');
      assert.equal(state.focus, 'cw-search');
      assert.equal(state.draft, 'Este borrador debe conservarse íntegro.');
    }
    receipt.runtime = await page.evaluate(() => Axx.nativeInvoke('native_status'));
    receipt.result = 'PASS';
  } catch (error) {
    receipt.result = 'FAIL'; receipt.error = error.stack; throw error;
  } finally {
    try {
      await page.locator('#cw-search').fill('');
      if (original) await page.evaluate(id => Axx.chatWorkspace.select(id), original);
      if (scratch) await page.evaluate(id => Axx.backendRequest('POST', '/axx-api/chat/delete', { id }), scratch.id);
    } catch (error) { receipt.cleanup_error = error.message; }
    fs.writeFileSync('build/chat-0.21.4/installed-chat-focus.json', JSON.stringify(receipt, null, 2));
    await browser.close();
  }
  console.log(receipt.result, receipt.cases.length, 'native focus cases');
})().catch(error => { console.error(error); process.exitCode = 1; });
