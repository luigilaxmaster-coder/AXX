// Group/context regression (phase 6, P0-01). Real chat-workspace.js against the real HTTP + SQLite fixture
// (backend.tests.chat_http_fixture). The server rotates the conversation context id whenever a group is created,
// assigned or deleted; the client must adopt that context BEFORE any further save. Not native visual acceptance.
const path = require('path'), assert = require('node:assert/strict'), { spawn } = require('child_process');
let chromium;
try { ({ chromium } = require('playwright')); }
catch { ({ chromium } = require(require('module').createRequire(path.join(process.env.USERPROFILE || '', '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json')).resolve('playwright'))); }
(async () => {
  const child = spawn('python', ['-m', 'backend.tests.chat_http_fixture'], { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  let browser;
  const failures = [];
  try {
    const config = await new Promise((resolve, reject) => {
      let output = ''; child.stdout.on('data', d => { output += d; if (output.includes('\n')) resolve(JSON.parse(output.split('\n')[0])); });
      child.on('exit', code => reject(Error('fixture exited ' + code)));
    });
    browser = await chromium.launch({ headless: true, executablePath: process.env.AXX_TEST_CHROMIUM || undefined });
    const page = await browser.newPage(); page.setDefaultTimeout(10000);
    const pageErrors = []; page.on('pageerror', e => pageErrors.push(e.message));
    await page.exposeFunction('backend', async (method, url, body) => {
      const r = await fetch('http://127.0.0.1:' + config.port + url, { method, headers: { Authorization: 'Bearer ' + config.token, 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
      const data = await r.json();
      if (!r.ok) { failures.push({ url, status: r.status, body: data }); throw Error(JSON.stringify(data)); }
      return data;
    });
    await page.route('http://chat.test/', route => route.fulfill({ contentType: 'text/html', body: '<section id="view-chat"><div id="chat-log"></div><textarea id="chat-input"></textarea><button id="chat-new"></button></section><input id="keep-history" type="checkbox" checked>' }));
    const boot = async () => {
      await page.goto('http://chat.test/');
      await page.evaluate(() => {
        window.cancelled = 0;
        window.Axx = { isNative: () => true, newId: () => crypto.randomUUID(), backendRequest: (m, u, b) => window.backend(m, u, b) };
        const data = { messages: [], draft: '', prefs: { keepHistory: true } };
        Axx.companion = { data, save() { localStorage.setItem('legacy', JSON.stringify(this.data)); }, renderChat() {}, cancelRequest() { window.cancelled++; }, stopDictation() {}, stopSpeech() {}, renderAttachment() {}, sayStatus() {}, send() {}, exportChat() {}, brain: { async chat(p, m) { return m; } } };
        Axx.commandLibrary = { renderOperation() {}, request: window.backend };
      });
      await page.addScriptTag({ path: '1.AXX/scripts/chat-workspace.js' });
      await page.waitForFunction(() => Axx.chatWorkspace?.ready && Axx.chatWorkspace.active);
    };
    const open = () => page.evaluate(() => document.querySelectorAll('#view-chat details').forEach(d => { d.open = true; }));
    const settled = () => page.waitForFunction(() => !Axx.chatWorkspace.busy);
    const row = id => page.evaluate(id => Axx.backendRequest('GET', '/axx-api/chat/conversations?id=' + id), id);
    const noError = async label => { assert.equal(await page.locator('#cw-error').isHidden(), true, label + ': error visible: ' + await page.locator('#cw-error').textContent()); };
    await boot();
    await page.click('#cw-browse'); await open();

    // 1. create a group with a pending draft: the UI adopts the new context and the draft survives.
    const first = await page.evaluate(() => Axx.chatWorkspace.active.id);
    const stale = await page.evaluate(() => { const t = Axx.chatWorkspace.captureMemoryToken(); return { memory_scope: t.memory_scope, memory_context_id: t.memory_context_id }; });
    await page.locator('#chat-input').fill('Borrador A');
    await page.fill('#cw-group-name', 'Grupo A'); await page.click('#cw-create-group');
    await page.waitForFunction(() => Axx.chatWorkspace.active.group_id && !Axx.chatWorkspace.busy);
    await noError('create group');
    const groupA = await page.evaluate(() => Axx.chatWorkspace.active.group_id);
    const serverRow = await row(first);
    assert.equal(serverRow.group_id, groupA, 'server persisted the group');
    assert.equal(await page.evaluate(() => Axx.chatWorkspace.active.connect_id), serverRow.connect_id, 'UI adopted the rotated context');
    assert.notEqual(serverRow.connect_id, stale.memory_context_id, 'context really rotated');
    assert.equal(await page.locator('#cw-group').inputValue(), groupA, 'selector shows the current group');
    assert.match(await page.locator('#cw-context-open').textContent(), /Grupo A/);
    assert.equal(await page.locator('#chat-input').inputValue(), 'Borrador A', 'draft preserved');
    await page.evaluate(() => Axx.chatWorkspace.flush());
    assert.equal((await row(first)).draft, 'Borrador A', 'draft saved under the new context');

    // 2. the chat uses the updated context (group note).
    await page.click('#cw-context-open'); await page.fill('#cw-note', 'Nota del grupo A'); await page.click('#cw-add-note');
    await page.waitForFunction(() => Axx.chatWorkspace.active.context?.length === 1);
    await noError('group note');
    const sent = await page.evaluate(() => Axx.companion.brain.chat({}, [{ role: 'user', content: 'Pregunta' }]));
    assert.match(JSON.stringify(sent), /Nota del grupo A/, 'chat request carries the new group context');

    // 3. an older request/save carrying the previous context is still rejected by the server and the token is stale.
    assert.equal(await page.evaluate(t => Axx.chatWorkspace.isMemoryTokenCurrent({ memory_scope: t.memory_scope, memory_context_id: t.memory_context_id, epoch: 0 }), stale), false);
    const before = failures.length;
    await assert.rejects(page.evaluate(({ id, stale }) => Axx.backendRequest('POST', '/axx-api/chat/save', { id, messages: [], draft: 'viejo', attachment: null, ...stale }), { id: first, stale }), /contexto/i);
    assert.equal(failures.length, before + 1); assert.equal(failures.at(-1).status, 400);
    assert.notEqual((await row(first)).draft, 'viejo', 'stale write did not land');

    // 4. second conversation + second group: switching groups never mixes conversations or context.
    await page.click('#cw-new'); await page.waitForFunction(id => Axx.chatWorkspace.active.id !== id && !Axx.chatWorkspace.busy, first);
    const second = await page.evaluate(() => Axx.chatWorkspace.active.id);
    await page.click('#cw-browse'); await open();
    await page.fill('#cw-group-name', 'Grupo B'); await page.click('#cw-create-group');
    await page.waitForFunction(g => Axx.chatWorkspace.active.group_id && Axx.chatWorkspace.active.group_id !== g && !Axx.chatWorkspace.busy, groupA);
    const groupB = await page.evaluate(() => Axx.chatWorkspace.active.group_id);
    assert.notEqual(groupA, groupB);
    await noError('second group');
    const mixed = await page.evaluate(() => Axx.companion.brain.chat({}, [{ role: 'user', content: 'Pregunta' }]));
    assert.doesNotMatch(JSON.stringify(mixed), /Nota del grupo A/, 'group B chat does not see group A context');
    await page.selectOption('#cw-filter', groupA); await page.waitForFunction(() => document.querySelectorAll('#cw-list .cw-thread').length === 1);
    const listed = await page.evaluate(() => Axx.backendRequest('GET', '/axx-api/chat/conversations'));
    assert.deepEqual(listed.conversations.filter(c => c.group_id === groupA).map(c => c.id), [first]);
    assert.deepEqual(listed.conversations.filter(c => c.group_id === groupB).map(c => c.id), [second]);

    // 5. assign an existing chat through the selector while a debounced save is pending (concurrent operations).
    await page.selectOption('#cw-filter', '');
    await page.evaluate(id => Axx.chatWorkspace.select(id), first); await settled();
    await page.evaluate(() => { const i = document.querySelector('#chat-input'); i.value = 'Escrito durante el cambio'; i.dispatchEvent(new Event('input')); Axx.companion.save(); });
    await page.click('#cw-browse'); await open();
    await page.evaluate(() => { const i = document.querySelector('#chat-input'); i.value = 'Escrito durante el cambio'; i.dispatchEvent(new Event('input')); Axx.companion.save(); });
    await page.selectOption('#cw-group', groupB);
    await page.waitForFunction(g => Axx.chatWorkspace.active.group_id === g && !Axx.chatWorkspace.busy, groupB);
    await noError('assign during pending save');
    assert.equal(await page.locator('#chat-input').inputValue(), 'Escrito durante el cambio');
    await page.evaluate(() => Axx.chatWorkspace.flush());
    assert.equal((await row(first)).draft, 'Escrito durante el cambio');
    assert.equal((await row(first)).group_id, groupB);
    assert.equal(await page.evaluate(() => Axx.chatWorkspace.active.connect_id), (await row(first)).connect_id);

    // 6. external rotation followed by select() of the same chat (the pattern of the older fixture) must not fail.
    await page.evaluate(async g => { await Axx.backendRequest('POST', '/axx-api/chat/update', { id: Axx.chatWorkspace.active.id, group_id: g }); await Axx.chatWorkspace.select(Axx.chatWorkspace.active.id); }, groupA);
    await noError('external rotation');
    assert.equal(await page.evaluate(() => Axx.chatWorkspace.active.group_id), groupA);

    // 6b. the next chat request after an unadopted rotation (profile save rotates every context) starts from the
    // server's current context instead of being aborted or answered with HTTP 400.
    const failuresBefore = failures.length;
    await page.evaluate(() => Axx.backendRequest('POST', '/axx-api/chat/profile', { name: 'Axx Test', instructions: 'Responde breve' }));
    const profiled = await page.evaluate(() => Axx.companion.brain.chat({}, [{ role: 'user', content: 'Continuar' }]));
    assert.match(JSON.stringify(profiled), /Responde breve/, 'request used the refreshed profile/context');
    assert.equal(failures.length, failuresBefore, 'no HTTP error for the request after rotation');
    assert.equal(await page.evaluate(() => Axx.chatWorkspace.active.connect_id), (await row(first)).connect_id);

    // 7. a rejected mutation is shown, not hidden, and does not change the active context.
    const activeBefore = await page.evaluate(() => ({ g: Axx.chatWorkspace.active.group_id, c: Axx.chatWorkspace.active.connect_id }));
    await page.click('#cw-browse'); await open(); await page.waitForTimeout(500); // let the browse-time refresh rebuild the options first
    await page.evaluate(() => { document.querySelector('#cw-group').add(new Option('Fantasma', 'no-existe')); });
    await page.selectOption('#cw-group', 'no-existe');
    await page.waitForFunction(() => !document.querySelector('#cw-error').hidden);
    assert.deepEqual(await page.evaluate(() => ({ g: Axx.chatWorkspace.active.group_id, c: Axx.chatWorkspace.active.connect_id })), activeBefore);

    // 8. delete the group: members move to "no group" and the UI adopts the rotated context.
    await page.evaluate(() => { window.confirm = () => true; });
    await page.click('#cw-context-open'); await page.click('#cw-group-delete');
    await page.waitForFunction(() => !Axx.chatWorkspace.active.group_id && !Axx.chatWorkspace.busy);
    assert.equal(await page.evaluate(() => Axx.chatWorkspace.active.connect_id), (await row(first)).connect_id);

    // 9. "restart": a new page over the same persisted database keeps every assignment.
    await boot();
    const after = await page.evaluate(() => Axx.backendRequest('GET', '/axx-api/chat/conversations'));
    assert.equal(after.conversations.find(c => c.id === second).group_id, groupB);
    assert.equal(after.conversations.find(c => c.id === first).group_id ?? null, null);
    assert.deepEqual(pageErrors, []);
    assert.equal(failures.length, 2, 'only the deliberate stale write and the deliberate invalid group were rejected: ' + JSON.stringify(failures));
    console.log(JSON.stringify({ result: 'PASS', checks: 9, rejected_by_design: failures.map(f => f.body.error.message) }));
  } catch (e) {
    console.error(e && e.stack || e); console.error(JSON.stringify(failures)); process.exitCode = 1;
  } finally { if (browser) await browser.close(); child.kill(); }
})();
