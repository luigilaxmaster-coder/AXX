// Deterministic instrumentation only: no model, microphone, network or audio playback.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync('1.AXX/scripts/prompt-contracts.js', 'utf8');
const plain = value => JSON.parse(JSON.stringify(value));
function fixture() {
    let now = 0, respond;
    const Axx = {isNative: () => true, backendRequest: async (method, path, body) => ({
        text: 'PRIVATE POLICY', version: 'contracts-1', mode: body.mode, characters: 14,
        sha256: (body.mode === 'voice' ? 'a' : 'b').repeat(64)
    })};
    Axx.companion = {brain: {chat: async (p, messages, signal, delta) => {
        await Axx.promptContracts.prepare({...p}, messages, signal);
        return respond(p, signal, delta);
    }}};
    vm.runInNewContext(source, {window: {Axx}, DOMException, performance: {now: () => now}});
    Axx.promptContracts.instrument();
    return {Axx, clock: value => now = value, response: value => respond = value,
        run: (p = {}, signal) => Axx.companion.brain.chat(p, [{role: 'user', content: 'PRIVATE REQUEST'}], signal),
        summary: () => plain(Axx.promptContracts.timingSummary())};
}
(async () => {
    const f = fixture();
    assert.deepEqual(f.summary(), {sample_limit: 128, sample_count: 0, percentile_method: 'nearest_rank', groups: []});
    f.response((p, signal, delta) => {
        f.clock(3); delta(''); delta('PRIVATE RESPONSE');
        f.clock(7); delta('PRIVATE RESPONSE AGAIN'); f.clock(10);
        return {reason: 'stop', text: 'PRIVATE RESPONSE', route: {provider: 'actual-route', identity: 'reported', model: 'actual-model'}};
    });
    await f.run({prompt_mode: 'voice', provider: 'requested-route', model: 'requested-model', personalityNotes: 'PRIVATE NOTE', apiKey: 'PRIVATE KEY'});
    const first = f.summary().groups[0];
    assert.equal(first.prompt_sha256, 'a'.repeat(64));
    assert.equal(first.prompt_version, 'contracts-1');
    assert.equal(first.provider, 'actual-route');
    assert.equal(first.reported_model, 'actual-model');
    assert.equal(first.requested_model, 'requested-model');
    assert.equal(first.count, 1);
    assert.deepEqual(first.first_text_ms, {count: 1, p50: 3, p95: 3});
    assert.deepEqual(first.total_ms, {count: 1, p50: 10, p95: 10});
    assert.ok(!JSON.stringify(f.summary()).includes('PRIVATE'));
    assert.deepEqual(Object.keys(f.Axx.promptContracts.lastTiming).sort(), ['first_text_ms', 'mode', 'outcome', 'total_ms']);

    const concurrent = fixture(), waiting = new Map();
    concurrent.response((p, signal, delta) => new Promise(resolve => waiting.set(p.prompt_mode, {delta, resolve})));
    const voice = concurrent.run({prompt_mode: 'voice'}), chat = concurrent.run({prompt_mode: 'conversation'});
    for (let turn = 0; waiting.size < 2 && turn < 20; turn++) await Promise.resolve();
    assert.equal(waiting.size, 2, 'Both requests must reach the controlled response');
    concurrent.clock(5); waiting.get('voice').delta('Voice');
    concurrent.clock(8); waiting.get('conversation').delta('Chat');
    concurrent.clock(10); waiting.get('conversation').resolve({reason: 'stop'}); await chat;
    concurrent.clock(12); waiting.get('voice').resolve({reason: 'stop'}); await voice;
    const groups = concurrent.summary().groups;
    assert.equal(groups.find(row => row.mode === 'voice').prompt_sha256, 'a'.repeat(64));
    assert.equal(groups.find(row => row.mode === 'conversation').prompt_sha256, 'b'.repeat(64));
    assert.equal(groups.find(row => row.mode === 'voice').first_text_ms.p50, 5);
    assert.equal(groups.find(row => row.mode === 'conversation').first_text_ms.p50, 8);

    const cancelled = fixture(), controller = new AbortController();
    let lateDelta;
    cancelled.response((p, signal, delta) => {
        lateDelta = delta; controller.abort(); delta('late text');
        throw new DOMException('cancelled', 'AbortError');
    });
    await assert.rejects(cancelled.run({prompt_mode: 'voice'}, controller.signal), {name: 'AbortError'});
    cancelled.clock(50); lateDelta('later text');
    assert.equal(cancelled.summary().sample_count, 1);
    assert.equal(cancelled.summary().groups[0].outcome, 'cancelled');
    assert.deepEqual(cancelled.summary().groups[0].first_text_ms, {count: 0, p50: null, p95: null});

    const bounded = fixture();
    bounded.response(() => ({reason: 'stop', route: {provider: 'gateway', model: 'configured-only', identity: 'unverified_profile'}}));
    for (let i = 0; i < 130; i++) await bounded.run({prompt_mode: 'voice', model: 'requested'});
    const limited = bounded.summary();
    assert.equal(limited.sample_count, 128);
    assert.equal(limited.groups[0].count, 128);
    assert.equal(limited.groups[0].reported_model, null);
    assert.equal(limited.groups[0].requested_model, 'requested');
    assert.deepEqual(limited.groups[0].first_text_ms, {count: 0, p50: null, p95: null});
    limited.groups[0].count = 999;
    assert.equal(bounded.summary().groups[0].count, 128);
    bounded.Axx.promptContracts.instrument();
    await bounded.run({prompt_mode: 'voice', model: 'requested'});
    assert.equal(bounded.summary().sample_count, 128);

    const percentiles = fixture();
    let end = 0;
    for (const duration of [1, 2, 3, 4]) {
        percentiles.clock(end);
        percentiles.response(() => {end += duration; percentiles.clock(end); return {reason: 'stop'};});
        await percentiles.run();
    }
    assert.deepEqual(percentiles.summary().groups[0].total_ms, {count: 4, p50: 2, p95: 4});
    percentiles.Axx.companion.brain = {chat: async () => ({reason: 'stop'})};
    percentiles.Axx.promptContracts.instrument();
    percentiles.Axx.promptContracts.instrument();
    await percentiles.run({model: 'different'});
    assert.equal(percentiles.summary().sample_count, 5);
    assert.equal(percentiles.summary().groups.at(-1).prompt_version, null);

    const outcomes = fixture();
    outcomes.response(() => ({reason: 'length'})); await outcomes.run();
    outcomes.response(() => {throw Error('PRIVATE ERROR');}); await assert.rejects(outcomes.run());
    assert.deepEqual(outcomes.summary().groups.map(row => row.outcome), ['partial', 'failed']);
    assert.ok(!JSON.stringify(outcomes.summary()).includes('PRIVATE ERROR'));
    console.log('Prompt timings: PASS (bounded cohorts, percentiles, request identity, privacy and cancellation)');
})().catch(error => {console.error(error); process.exitCode = 1;});
