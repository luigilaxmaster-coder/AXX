const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../Axx.html'), 'utf8');
function actualClass(name) {
    const start = html.indexOf('    class ' + name + ' {');
    const end = html.indexOf('    Axx.' + name + ' = ' + name + ';', start);
    assert.ok(start >= 0 && end > start, name + ' must remain the actual application class');
    return html.slice(start, end) + '\nthis.' + name + ' = ' + name + ';';
}
function element() {
    return { children: [], hidden: false, textContent: '', append(...nodes) { this.children.push(...nodes); }, replaceChildren(...nodes) { this.children = nodes; } };
}
const nodes = new Map(['activity-list', 'unread-count'].map(id => [id, element()]));
const scopes = new Map(['A', 'B'].map(task_id => [task_id, { task_id, generation: 0 }]));
const contexts = new Map([['A', 'ctxA0'], ['B', 'ctxB0']]);
let serial = 0;
const Axx = { newId: () => 'event-' + ++serial, chatWorkspace: {
    captureMemoryScope(id) { const value = scopes.get(id); if (!value) throw Error('Unknown scope'); return { ...value }; },
    captureMemoryToken(id) { return { memory_context_id: contexts.get(id) }; }
} };
const context = vm.createContext({ Axx, Date, Intl, window: {}, node: id => nodes.get(id), document: { createElement: element } });
vm.runInContext(actualClass('InteractionOrchestrator'), context);
vm.runInContext(actualClass('Companion'), context);
const sounds = [], signals = [], opens = [];
const companion = Object.create(context.Companion.prototype);
Object.assign(companion, { orchestrator: new context.InteractionOrchestrator(), events: [], unread: 0,
    audio: { play(...args) { sounds.push(args); } },
    app: { stopDemo() { opens.push('stopDemo'); }, machine: { notify(...args) { signals.push(args); } } },
    stopTour() { opens.push('stopTour'); },
    speakReply() { throw Error('Activity must not narrate a second response'); },
    openChat() { throw Error('Polling must not open a surface'); },
    openFeature() { throw Error('Polling must not open a surface'); }
});
companion.orchestrator.subscribe(event => companion.presentEvent(event));
function group(overrides = {}) {
    return { mission_id: 'missionA', task_id: 'A', project_id: 'projectA', goal_revision: 1, plan_hash: 'hashA',
        category: 'progress', summary: 'Dos pasos verificados; objetivo pendiente.', memory_scope: { task_id: 'A', generation: 0 },
        memory_context_id: 'ctxA0', memory_dependencies: [], ...overrides };
}
function reset() { companion.orchestrator.clear(); companion.events = []; companion.unread = 0; sounds.length = signals.length = opens.length = 0; }

assert.equal(companion.updateMissionAttention(group()), true);
assert.equal(companion.updateMissionAttention(group({ summary: 'Tres pasos verificados; falta el criterio final.' })), true);
assert.equal(companion.events.length, 1);
assert.equal(companion.unread, 0);
assert.equal(nodes.get('activity-list').children.length, 1);
assert.equal(sounds.length + signals.length + opens.length, 0, 'Manual progress stays silent and does not change focus');
const decision = group({ category: 'decision', summary: 'Revisa el destino antes de continuar.', attention_key: 'attentionA' });
assert.equal(companion.updateMissionAttention(decision), true);
assert.equal(companion.unread, 0);
assert.equal(companion.updateMissionAttention(decision, { notify: true }), true);
assert.equal(companion.unread, 1, 'A claim after manual hydration still marks its one group unread');
companion.updateMissionAttention(decision);
assert.equal(companion.unread, 1);
assert.equal(companion.events.length, 1);
assert.equal(sounds.length, 0, 'A pro-active card does not add an extra audio cue');
companion.updateMissionAttention(group({ category: 'done', summary: 'Objetivo verificado.', attention_key: 'doneA', goal_revision: 2 }));
assert.equal(companion.unread, 0, 'An old decision cannot remain pending after the current result replaces it');
assert.equal(companion.updateMissionAttention(decision, { notify: true }), false, 'Older goal revisions cannot restore the old decision');
assert.equal(companion.events[0].text, 'Objetivo verificado.');
companion.updateMissionAttention(group({ goal_revision: 2, plan_hash: 'repairedA', category: 'decision', summary: 'Revisa la reparación.' }));
assert.equal(companion.events[0].mission.plan_hash, 'repairedA', 'A legitimate repair is not ordered by hash or by success status');
const independent = group({ task_id: 'B', project_id: 'projectB', mission_id: 'missionB', plan_hash: 'hashB',
    memory_scope: { task_id: 'B', generation: 0 }, memory_context_id: 'ctxB0', category: 'problem', summary: 'B requiere conciliación.', attention_key: 'attentionB' });
companion.updateMissionAttention(independent, { notify: true });
assert.equal(companion.events.length, 2);
assert.equal(companion.events.find(row => row.mission.mission_id === 'missionA').mission.category, 'decision');
assert.equal(companion.unread, 1);

reset();
companion.updateMissionAttention(decision, { solicited: true });
assert.equal(sounds[0][0], 'approval');
assert.equal(signals[0][0], 'approval');
assert.equal(companion.unread, 1);
companion.updateMissionAttention(decision);
assert.equal(sounds.length, 1, 'Polling after a requested response cannot replay its cue');
companion.updateMissionAttention(group({ summary: 'Pausa solicitada.' }), { solicited: true });
assert.equal(sounds.length, 1, 'A voluntary pause is not an execution error');
companion.updateMissionAttention(group({ category: 'done', summary: '<img src=x onerror=alert(1)>' }), { solicited: true });
assert.equal(sounds.at(-1)[0], 'success');
assert.equal(nodes.get('activity-list').children[0].children[1].textContent, '<img src=x onerror=alert(1)>', 'Summary remains plain text');

reset();
const causal = group({ ...independent, mission_id: 'dependentB', memory_dependencies: [{ task_id: 'A', generation: 0 }] });
companion.updateMissionAttention(group()); companion.updateMissionAttention(causal); companion.updateMissionAttention(independent);
causal.memory_dependencies[0].generation = 99;
assert.equal(companion.events.find(row => row.mission.mission_id === 'dependentB').mission.memory_dependencies[0].generation, 0, 'Caller mutation cannot alter stored provenance');
scopes.set('A', { task_id: 'A', generation: 1 }); contexts.set('A', 'ctxA1');
companion.invalidateMissionAttention('A');
assert.equal(companion.events.length, 1);
assert.equal(companion.events[0].mission.mission_id, 'missionB', 'Independent B survives forgetting A');
assert.equal(companion.orchestrator.history.length, 1);
assert.equal(companion.updateMissionAttention(group(), { notify: true }), false, 'Late A0 is rejected');
assert.equal(companion.updateMissionAttention(group({ ...independent, mission_id: 'dependentB', memory_dependencies: [{ task_id: 'A', generation: 0 }] })), false, 'B cannot reuse revoked A through a current own scope');
assert.equal(companion.updateMissionAttention(group({ ...independent, memory_dependencies: [{ task_id: 'B', generation: 0, context_id: 'ctxBold' }] })), false, 'Captured context references must also remain current');
reset();
const unopened = group({ ...independent, memory_dependencies: [{ task_id: 'unopened-source', generation: 0 }] });
let referenceChecks = 0;
Axx.chatWorkspace.allowsMemoryReference = ref => { referenceChecks++; return ref.task_id === 'unopened-source'; };
assert.equal(companion.updateMissionAttention(unopened), true, 'A server-validated dependency does not require opening its source chat locally');
assert.equal(referenceChecks, 1);
companion.invalidateMissionAttention('unopened-source');
Axx.chatWorkspace.allowsMemoryReference = () => false;
assert.equal(companion.updateMissionAttention(unopened), false, 'Known local revocation still rejects that dependency');
assert.equal(companion.events.length, 0);
delete Axx.chatWorkspace.allowsMemoryReference;

reset();
for (const invalid of [{ memory_scope: null }, { memory_dependencies: {} }, { goal_revision: false }, { goal_revision: 0 }, { category: 'success' }, { summary: 'x'.repeat(2001) }])
    assert.equal(companion.updateMissionAttention(group({ memory_scope: { task_id: 'A', generation: 1 }, memory_context_id: 'ctxA1', ...invalid })), false);
assert.equal(companion.events.length, 0);
for (let i = 0; i < 90; ++i)
    companion.updateMissionAttention(group({ mission_id: 'bounded-' + i, category: 'decision', summary: 'Revisión ' + i,
        memory_scope: { task_id: 'A', generation: 1 }, memory_context_id: 'ctxA1', attention_key: 'key-' + i }), { notify: true });
assert.equal(companion.events.length, 50); assert.equal(companion.orchestrator.history.length, 80); assert.equal(companion.unread, 40);
assert.equal(companion.orchestrator.emit({ id: 'timer-current', origin: 'real', type: 'processing', at: Date.now(), taskId: 'timer', revision: 2 }), true);
assert.equal(companion.orchestrator.emit({ id: 'timer-old', origin: 'real', type: 'processing', at: Date.now(), taskId: 'timer', revision: 1 }), false);
assert.equal(sounds.length, 1, 'Only the explicit legacy timer event adds its existing sound');
const requested = Object.create(context.Companion.prototype), replies = [], messages = [];
Object.assign(requested, { data: { prefs: { voiceRead: true } }, renderChat() {}, save() {},
    message(role, text) { const row = { role, text }; messages.push(row); return row; }, read(text) { replies.push(text); } });
assert.equal(requested.speakReply(''), false);
requested.localNotice('Resultado solicitado en Discreto.', 'explicit-operation');
assert.equal(replies.length, 1); assert.equal(messages[0].operation_id, 'explicit-operation');
requested.data.prefs.voiceRead = false;
requested.localNotice('Respuesta escrita.');
assert.equal(replies.length, 1, 'Explicit replies retain the saved voice preference');
assert.equal(requested.speakReply('Lectura desactivada.'), false);
requested._forceVoiceReplyOnce = true;
requested.localNotice('Respuesta de voz solicitada.'); requested.localNotice('Siguiente respuesta escrita.');
assert.equal(replies.length, 2); assert.equal(requested._forceVoiceReplyOnce, false);
requested.data.prefs.mutedAll = true; requested._forceVoiceReplyOnce = true;
assert.equal(requested.speakReply('La salida global permanece silenciada.'), false);
assert.equal(replies.length, 2); assert.equal(requested._forceVoiceReplyOnce, false);
const cleanStart = html.indexOf('    function speechReplyText(value) {'), cleanEnd = html.indexOf('    Axx.speechReplyText = speechReplyText;', cleanStart);
assert.ok(cleanStart > 0 && cleanEnd > cleanStart);
vm.runInContext(html.slice(cleanStart, cleanEnd), context);
const reader = Object.create(context.Companion.prototype), readerToasts = [], synthesized = [];
Object.assign(reader, { data: { prefs: {} }, app: { toast(text) { readerToasts.push(text); }, stopAudio() {} }, stopSpeech() {}, stopDictation() {} });
assert.equal(reader.read('Una lectura sin motor disponible.'), false);
nodes.set('sound-all-muted', { checked: true });
context.speechSynthesis = { getVoices: () => [], speak: value => synthesized.push(value) };
context.window.speechSynthesis = context.speechSynthesis;
context.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
assert.equal(reader.read('Salida silenciada.'), false);
nodes.get('sound-all-muted').checked = false;
assert.equal(reader.read('Solicitud al lector local.'), true);
assert.equal(synthesized.length, 1, 'Reader acceptance is distinct from physical playback');
reader.voiceDelegate = { read: () => false };
assert.equal(reader.read('Delegado no disponible.'), false);
console.log('PASS: actual Activity and orchestrator group missions, preserve requested cues, bound history and reject revoked provenance');
