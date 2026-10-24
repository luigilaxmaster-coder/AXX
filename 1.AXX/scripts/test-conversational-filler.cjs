const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const nodes = [];
const parameter = () => ({ kind: 'parameter', value: 0, setValueAtTime(value) { this.value = value; }, linearRampToValueAtTime(value) { this.value = value; }, cancelScheduledValues() {}, setTargetAtTime() {} });
const createNode = type => {
    const node = { kind: 'node', nodeType: type, targets: [], started: false, stopped: false,
        connect(target) { this.targets.push(target); }, disconnect() { this.targets = []; },
        start() { this.started = true; }, stop() { this.stopped = true; } };
    if (type === 'gain') node.gain = parameter();
    if (type === 'oscillator' || type === 'filter') node.frequency = parameter();
    nodes.push(node);
    return node;
};
const bus = { kind: 'node', type: 'state-bus' };
const context = { state: 'running', currentTime: 0, createGain: () => createNode('gain'), createOscillator: () => createNode('oscillator'), createBiquadFilter: () => createNode('filter') };
const audio = { enabled: false, allMuted: false, profile: 'discreet', capture: false, ctx: context, buses: { state: bus } };
const Axx = { AudioManager: { shared: audio } };
let finishFade;
vm.runInNewContext(fs.readFileSync(path.join(__dirname, 'conversational-filler.js'), 'utf8'),
    { window: { Axx }, document: { hidden: false }, setTimeout: callback => { finishFade = callback; } });

Axx.startLoadingAudio();
assert.equal(nodes.length, 0, 'No effect may start before sound consent');
audio.enabled = true;
audio.allMuted = true;
Axx.startLoadingAudio();
assert.equal(nodes.length, 0, 'Mute blocks loading sound');
audio.allMuted = false;
Axx.startLoadingAudio();
const oscillators = nodes.filter(node => node.nodeType === 'oscillator');
assert.equal(oscillators.length, 5);
assert(oscillators.every(node => node.started && node.targets.every(target => target.kind === 'node')), 'Oscillators must feed bounded audio nodes');
assert.equal(nodes.filter(node => node.targets.includes(bus)).length, 1, 'Only the shared consent-controlled bus receives output');
Axx.stopLoadingAudio();
finishFade();
assert(oscillators.every(node => node.stopped), 'Stop releases every oscillator');

let previous = '';
for (let i = 0; i < 20; i++) {
    const next = Axx.selectConversationalFiller('Explica esto', 'es');
    assert.notEqual(next, previous, 'Adjacent voice turns must not repeat a filler');
    previous = next;
}
console.log('PASS: consent and mute gate the shared audio bus; modulation is bounded; stop releases nodes; phrases rotate');
