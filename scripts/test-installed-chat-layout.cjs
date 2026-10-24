// Real stored histories in the installed WebView; no injected styles or fake rows.
const fs = require('fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.USERPROFILE + '/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async () => {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9224');
  const page = browser.contexts()[0].pages().find(p => p.url().includes('Axx.html'));
  const receipt = { kind: 'INSTALLED_LONG_CHAT_HISTORY', cases: [] }, created = [];
  const api = (method, route, body) => page.evaluate(args => Axx.backendRequest(...args), [method, route, body]);
  let saved;
  try {
    await page.waitForFunction(() => Axx.chatWorkspace?.ready && !Axx.chatWorkspace.busy);
    saved = await page.evaluate(() => ({ id: Axx.chatWorkspace.active.id, search: document.getElementById('cw-search').value, filter: document.getElementById('cw-filter').value, theme: Axx.interfaceTheme.value, view: Axx.companion.dock.selected }));
    await page.evaluate(() => Axx.chatWorkspace.flush());
    for (let index = 0; index < 18; index++) created.push((await api('POST', '/axx-api/chat/create', { title: 'Aceptación · historial largo ' + index })).id);
    await page.evaluate(async id => { Axx.resident.summon(false); await Axx.companion.openChat(); await Axx.chatWorkspace.select(id); await Axx.chatWorkspace.refresh(); }, created[0]);
    if (await page.locator('#cw-browse').isVisible()) await page.locator('#cw-browse').click();
    await page.locator('#cw-filter').selectOption('');
    await page.locator('#cw-search').fill('Aceptación · historial largo');
    await page.waitForFunction(() => document.querySelectorAll('#cw-list .cw-thread').length === 18);
    for (const theme of ['light', 'dark']) {
      await page.evaluate(theme => { Axx.interfaceTheme.apply(theme); document.getElementById('cw-browser').scrollTop = 0; }, theme);
      const bounds = await page.evaluate(() => {
        const list = document.getElementById('cw-list'), sidebar = document.getElementById('cw-browser');
        return { lastBottom: list.lastElementChild.getBoundingClientRect().bottom, organizeTop: sidebar.querySelector('.cw-organize').getBoundingClientRect().top, scrollHeight: sidebar.scrollHeight, height: sidebar.clientHeight };
      });
      receipt.cases.push({ theme, ...bounds });
      assert(bounds.organizeTop >= bounds.lastBottom, 'History rows overlap the group controls: ' + JSON.stringify(bounds));
      assert(bounds.scrollHeight > bounds.height, 'A long history must be scrollable');
      await page.locator('#cw-browser .cw-organize').scrollIntoViewIfNeeded();
      await page.locator('#panel').screenshot({ path: 'build/chat-0.21.4/installed-long-history-' + theme + '.png' });
    }
    receipt.runtime = await page.evaluate(() => Axx.nativeInvoke('native_status'));
    receipt.result = 'PASS';
  } catch (error) { receipt.result = 'FAIL'; receipt.error = error.stack; throw error; }
  finally {
    try {
      if (saved) {
        await page.locator('#cw-search').fill(saved.search);
        await page.locator('#cw-filter').selectOption(saved.filter);
        await page.evaluate(id => Axx.chatWorkspace.select(id), saved.id);
      }
      for (const id of created) await api('POST', '/axx-api/chat/delete', { id });
      if (saved) await page.evaluate(async prior => { await Axx.chatWorkspace.refresh(); Axx.interfaceTheme.apply(prior.theme); await Axx.companion.openFeature(prior.view || 'chat'); }, saved);
    } catch (error) { receipt.cleanup_error = error.message; }
    fs.writeFileSync('build/chat-0.21.4/installed-chat-layout.json', JSON.stringify(receipt, null, 2));
    await browser.close();
  }
  console.log(receipt.result, '18 stored chats in both themes');
})().catch(error => { console.error(error); process.exitCode = 1; });
