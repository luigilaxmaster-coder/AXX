const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

console.log('================================================================');
console.log('=== EMPIRICAL CHALLENGER: MILESTONE 2 COMPREHENSIVE SUITE    ===');
console.log('================================================================\n');

const htmlPath = path.resolve(__dirname, '../1.AXX/Axx.html');
const htmlSource = fs.readFileSync(htmlPath, 'utf8');

// -------------------------------------------------------------
// EXTRACT EXACT ResidentDesktop CLASS CODE FROM 1.AXX/Axx.html
// -------------------------------------------------------------
const startMarker = 'class ResidentDesktop {';
const startIndex = htmlSource.indexOf(startMarker);
assert(startIndex !== -1, 'Could not find "class ResidentDesktop {" in 1.AXX/Axx.html');

let braceCount = 0;
let endIndex = -1;
let inString = false;
let stringChar = '';
let inComment = false;

for (let i = startIndex; i < htmlSource.length; i++) {
    const char = htmlSource[i];
    const nextChar = htmlSource[i + 1];

    if (!inString && !inComment) {
        if (char === '/' && nextChar === '/') {
            inComment = 'single';
            i++;
            continue;
        }
        if (char === '/' && nextChar === '*') {
            inComment = 'multi';
            i++;
            continue;
        }
        if (char === '"' || char === "'" || char === '`') {
            inString = true;
            stringChar = char;
            continue;
        }
        if (char === '{') {
            braceCount++;
        } else if (char === '}') {
            braceCount--;
            if (braceCount === 0) {
                endIndex = i + 1;
                break;
            }
        }
    } else if (inComment === 'single') {
        if (char === '\n') inComment = false;
    } else if (inComment === 'multi') {
        if (char === '*' && nextChar === '/') {
            inComment = false;
            i++;
        }
    } else if (inString) {
        if (char === '\\') {
            i++;
        } else if (char === stringChar) {
            inString = false;
        }
    }
}

assert(endIndex !== -1, 'Could not locate closing brace of ResidentDesktop class');
const residentDesktopCode = htmlSource.slice(startIndex, endIndex);
console.log(`[INIT] Extracted ResidentDesktop class from Axx.html (${residentDesktopCode.length} bytes, lines ~18131 to ~18711)`);

// -------------------------------------------------------------
// SIMULATE REALISTIC DOM & RUNTIME ENVIRONMENT
// -------------------------------------------------------------
class MockElement {
    constructor(tagName, id = '', className = '') {
        this.tagName = tagName.toUpperCase();
        this.id = id;
        this.classList = {
            _classes: new Set(),
            add: (c) => this.classList._classes.add(c),
            remove: (c) => this.classList._classes.delete(c),
            contains: (c) => this.classList._classes.has(c),
            toggle: (c, force) => {
                if (force === undefined) {
                    if (this.classList.contains(c)) { this.classList.remove(c); return false; }
                    else { this.classList.add(c); return true; }
                }
                if (force) this.classList.add(c); else this.classList.remove(c);
                return force;
            }
        };
        this.className = className;
        this.dataset = {};
        this.attributes = new Map();
        this.style = {
            _props: new Map(),
            setProperty: (k, v) => this.style._props.set(k, v),
            getPropertyValue: (k) => this.style._props.get(k) || '',
            removeProperty: (k) => this.style._props.delete(k)
        };
        this.children = [];
        this.parentNode = null;
        this.hidden = false;
        this.offsetWidth = 420;
        this.offsetHeight = 560;
        this._capturedPointerId = null;
        this._listeners = new Map();
        this.textContent = '';
    }

    set innerHTML(val) {
        this._innerHTML = val;
        // Parse simple tags like <div>, <strong>
        const regex = /<([a-z0-9]+)([^>]*)>(?:(.*?)<\/\1>)?/gi;
        let match;
        while ((match = regex.exec(val)) !== null) {
            const tag = match[1];
            const attrs = match[2];
            const child = new MockElement(tag);
            const idM = attrs.match(/id="([^"]+)"/);
            if (idM) child.id = idM[1];
            const classM = attrs.match(/class="([^"]+)"/);
            if (classM) {
                child.className = classM[1];
                classM[1].split(/\s+/).forEach(c => child.classList.add(c));
            }
            this.appendChild(child);
        }
    }
    get innerHTML() { return this._innerHTML || ''; }

    set className(val) {
        this._className = val;
        if (this.classList && this.classList._classes) {
            this.classList._classes.clear();
            if (val) String(val).split(/\s+/).forEach(c => { if (c) this.classList._classes.add(c); });
        }
    }
    get className() { return this._className || ''; }

    addEventListener(evt, fn, capture) {
        if (!this._listeners.has(evt)) this._listeners.set(evt, []);
        this._listeners.get(evt).push({ fn, capture });
    }

    dispatchEvent(eventObj) {
        const listeners = this._listeners.get(eventObj.type) || [];
        for (const item of listeners) {
            item.fn(eventObj);
        }
    }

    setAttribute(k, v) { this.attributes.set(k, v); }
    getAttribute(k) { return this.attributes.get(k); }
    hasAttribute(k) { return this.attributes.has(k); }

    appendChild(child) {
        child.parentNode = this;
        this.children.push(child);
        return child;
    }

    append(...children) {
        for (const child of children) {
            if (child instanceof MockElement) this.appendChild(child);
        }
    }

    prepend(child) {
        child.parentNode = this;
        this.children.unshift(child);
        return child;
    }

    insertBefore(newNode, refNode) {
        newNode.parentNode = this;
        const idx = this.children.indexOf(refNode);
        if (idx === -1) this.children.push(newNode);
        else this.children.splice(idx, 0, newNode);
        return newNode;
    }

    after(newNode) {
        if (!this.parentNode) return;
        const idx = this.parentNode.children.indexOf(this);
        if (idx !== -1) {
            newNode.parentNode = this.parentNode;
            this.parentNode.children.splice(idx + 1, 0, newNode);
        }
    }

    matches(selector) {
        const parts = selector.split(',').map(s => s.trim());
        for (const part of parts) {
            if (part === '#' + this.id) return true;
            if (part.startsWith('.') && this.classList.contains(part.slice(1))) return true;
            if (part.toUpperCase() === this.tagName) return true;
            if (part.startsWith('[data-')) {
                const key = part.slice(6, -1);
                if (key.includes('=')) {
                    const [k, v] = key.split('=');
                    const cleanV = v.replace(/['"]/g, '');
                    const camelK = k.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
                    if (this.dataset[camelK] === cleanV) return true;
                } else {
                    const camelK = key.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
                    if (this.dataset[camelK] !== undefined) return true;
                }
            }
            if (part === '[contenteditable="true"]' && this.getAttribute('contenteditable') === 'true') return true;
            if (part === '[role=button]' && this.getAttribute('role') === 'button') return true;
        }
        return false;
    }

    closest(selector) {
        let curr = this;
        while (curr) {
            if (curr instanceof MockElement && curr.matches(selector)) return curr;
            curr = curr.parentNode;
        }
        return null;
    }

    querySelector(selector) {
        for (const child of this.children) {
            if (child instanceof MockElement) {
                if (child.matches(selector)) return child;
                const found = child.querySelector(selector);
                if (found) return found;
            }
        }
        return null;
    }

    querySelectorAll(selector) {
        const results = [];
        const traverse = (el) => {
            for (const child of el.children) {
                if (child instanceof MockElement) {
                    if (child.matches(selector)) results.push(child);
                    traverse(child);
                }
            }
        };
        traverse(this);
        return results;
    }

    getClientRects() {
        return this.hidden ? [] : [{ x: 0, y: 0, width: this.offsetWidth, height: this.offsetHeight }];
    }

    getBoundingClientRect() {
        return { x: 100, y: 100, width: this.offsetWidth, height: this.offsetHeight, right: 100 + this.offsetWidth, bottom: 100 + this.offsetHeight };
    }

    setPointerCapture(id) { this._capturedPointerId = id; }
    hasPointerCapture(id) { return this._capturedPointerId === id; }
    releasePointerCapture(id) { if (this._capturedPointerId === id) this._capturedPointerId = null; }
}

// -------------------------------------------------------------
// BUILD TEST HARNESS ENVIRONMENT IN VM
// -------------------------------------------------------------
function createHarness() {
    const documentListeners = new Map();
    const windowListeners = new Map();
    const storage = new Map();
    const ipcLog = [];

    const docEl = new MockElement('html');
    const docBody = new MockElement('body');
    docEl.appendChild(docBody);

    // Build standard Axx DOM tree:
    const stage = new MockElement('div', 'stage');
    const avatar = new MockElement('div', 'avatar');
    const a11MainBtn = new MockElement('button', 'a11-main-button');
    avatar.appendChild(a11MainBtn);
    stage.appendChild(avatar);
    docBody.appendChild(stage);

    // #panel -> .panel-head, .panel-view
    const panel = new MockElement('div', 'panel');
    const panelHead = new MockElement('div', '', 'panel-head');
    const panelTitle = new MockElement('h2', '', 'panel-title');
    panelHead.appendChild(panelTitle);
    const panelCloseBtn = new MockElement('button', 'flow-detail-close', 'icon-button');
    panelHead.appendChild(panelCloseBtn);

    const panelView = new MockElement('div', 'view-chat', 'panel-view');
    const chatInput = new MockElement('input', 'chat-input');
    const chatTextarea = new MockElement('textarea', 'chat-textarea');
    const chatSendBtn = new MockElement('button', 'chat-send');
    const chatConversation = new MockElement('div', 'chat-messages', 'conversation');
    const codeSnippet = new MockElement('code', '', 'hljs');
    const preSnippet = new MockElement('pre');
    preSnippet.appendChild(codeSnippet);
    chatConversation.appendChild(preSnippet);
    panelView.appendChild(chatConversation);
    panelView.appendChild(chatInput);
    panelView.appendChild(chatTextarea);
    panelView.appendChild(chatSendBtn);

    panel.appendChild(panelHead);
    panel.appendChild(panelView);
    docBody.appendChild(panel);

    // Settings panel with reset layout buttons
    const settingsPanel = new MockElement('div', 'v13-settings', 'v13-settings');
    const viewSettings = new MockElement('div', 'view-settings', 'panel-view');
    const resetDesktopLayoutBtn = new MockElement('button', 'reset-desktop-layout');
    viewSettings.appendChild(resetDesktopLayoutBtn);
    settingsPanel.appendChild(viewSettings);
    docBody.appendChild(settingsPanel);

    // Help & Appearance views
    const viewHelp = new MockElement('div', 'view-help', 'panel-view');
    docBody.appendChild(viewHelp);
    const viewAppearance = new MockElement('div', 'view-appearance', 'panel-view');
    docBody.appendChild(viewAppearance);
    const orbitReset = new MockElement('div', 'orbit-reset');
    docBody.appendChild(orbitReset);

    const mockDocument = {
        documentElement: docEl,
        body: docBody,
        getElementById: (id) => {
            const find = (node) => {
                if (node.id === id) return node;
                for (const c of node.children) {
                    if (c instanceof MockElement) {
                        const r = find(c);
                        if (r) return r;
                    }
                }
                return null;
            };
            return find(docEl);
        },
        querySelector: (sel) => docEl.querySelector(sel),
        querySelectorAll: (sel) => docEl.querySelectorAll(sel),
        createElement: (tag) => new MockElement(tag),
        createTextNode: (txt) => ({ textContent: txt }),
        addEventListener: (evt, fn, capture) => {
            if (!documentListeners.has(evt)) documentListeners.set(evt, []);
            documentListeners.get(evt).push({ fn, capture });
        }
    };

    const mockWindow = {
        addEventListener: (evt, fn, capture) => {
            if (!windowListeners.has(evt)) windowListeners.set(evt, []);
            windowListeners.get(evt).push({ fn, capture });
        },
        setInterval: () => 1,
        innerWidth: 1920,
        innerHeight: 1080
    };

    const mockLocalStorage = {
        getItem: (k) => storage.get(k) || null,
        setItem: (k, v) => storage.set(k, String(v)),
        removeItem: (k) => storage.delete(k)
    };

    const mockAxx = {
        clamp: (x, lo, hi) => Math.max(lo, Math.min(hi, x)),
        companion: {
            preferredSize: 280,
            data: { prefs: { follow: false } },
            follower: {},
            dock: { selected: 'chat' },
            closeSurface: () => {},
            persistBodySize: () => {},
            enableFollow: () => {}
        },
        home18: { wake: () => {} },
        orbit: {},
        flow: {
            nav: { step: 1 },
            compactTools: () => {},
            fold: () => {},
            tap: () => {}
        },
        actions: { screen: {} },
        app: {
            toast: () => {},
            renderer: {
                setPreview20: () => {},
                resize: () => {},
                draw: () => {},
                hitMask: () => ({ bits: [1] }),
                hitTest: (x, y) => true,
                setPressed: () => {},
                releaseDrag: () => {}
            },
            bridge: {
                status: async () => ({
                    desktop: {
                        workWidth: 1920,
                        workHeight: 1080,
                        spaceLeft: 900,
                        spaceRight: 1020,
                        spaceAbove: 500,
                        spaceBelow: 580,
                        screenX: 900,
                        screenY: 500,
                        scaleFactor: 1.0,
                        ready: true
                    }
                }),
                command: async (cmd, payload) => {
                    ipcLog.push({ cmd, payload });
                    return { ready: true, workWidth: 1920, workHeight: 1080 };
                },
                action: async (act) => {
                    ipcLog.push({ action: act });
                }
            },
            updateHitMap: async () => {}
        },
        organic: { surfaces: new Map() }
    };

    // Construct vm sandbox
    const sandbox = {
        Element: MockElement,
        document: mockDocument,
        window: mockWindow,
        localStorage: mockLocalStorage,
        Axx: mockAxx,
        MutationObserver: class {
            observe() {}
            disconnect() {}
        },
        performance: { now: () => Date.now() },
        screen: { availWidth: 1920, availHeight: 1080 },
        innerWidth: 1920,
        innerHeight: 1080,
        getComputedStyle: () => ({ visibility: 'visible', pointerEvents: 'auto', opacity: '1' }),
        console: { log: () => {}, warn: () => {}, error: console.error },
        queueMicrotask: (fn) => setImmediate(fn),
        setTimeout: (fn, ms) => setTimeout(fn, ms),
        Math: Math,
        Number: Number,
        JSON: JSON
    };

    vm.createContext(sandbox);

    // Execute the exact ResidentDesktop code in this context
    const script = new vm.Script(`
        ${residentDesktopCode}
        this.instance = new ResidentDesktop();
    `);
    script.runInContext(sandbox);

    const resident = sandbox.instance;

    // Helper to fire events
    function dispatchPointerEvent(targetType, eventObj) {
        const listeners = documentListeners.get(eventObj.type) || [];
        let prevented = false;
        let stopped = false;
        const evt = {
            ...eventObj,
            preventDefault: () => { prevented = true; },
            stopImmediatePropagation: () => { stopped = true; },
            defaultPrevented: prevented
        };
        for (const item of listeners) {
            item.fn(evt);
            if (stopped) break;
        }
        return { prevented, stopped };
    }

    return {
        sandbox,
        resident,
        storage,
        ipcLog,
        elements: {
            panel,
            panelHead,
            panelTitle,
            panelCloseBtn,
            panelView,
            chatInput,
            chatTextarea,
            chatSendBtn,
            chatConversation,
            preSnippet,
            codeSnippet,
            resetDesktopLayoutBtn
        },
        dispatchPointerEvent
    };
}

let passed = 0;
let failed = 0;

function test(name, fn) {
    try {
        fn();
        passed++;
        console.log(`  ✅ PASS: ${name}`);
    } catch (err) {
        failed++;
        console.error(`  ❌ FAIL: ${name}\n     ${err.message}`);
    }
}

// =============================================================
// TEST SUITE 1: STRESS TEST PANEL DRAG VS INPUT INTERACTION
// =============================================================
console.log('\n--- 1. STRESS TEST PANEL DRAG VS INPUT INTERACTION ---');

test('Input click isolation: Pointerdown on <input> NEVER initiates drag or resize', () => {
    const h = createHarness();
    const res = h.dispatchPointerEvent('input', {
        type: 'pointerdown',
        button: 0,
        pointerId: 1,
        clientX: 120,
        clientY: 150,
        target: h.elements.chatInput
    });
    assert.strictEqual(h.resident.panelDrag, null, 'panelDrag must be null');
    assert.strictEqual(h.resident.panelResize, null, 'panelResize must be null');
    assert.strictEqual(h.resident.drag, null, 'avatar drag must be null');
    assert.strictEqual(res.prevented, false, 'preventDefault must NOT be called on input');
});

test('Textarea click isolation: Pointerdown on <textarea> NEVER initiates drag or resize', () => {
    const h = createHarness();
    const res = h.dispatchPointerEvent('textarea', {
        type: 'pointerdown',
        button: 0,
        pointerId: 1,
        clientX: 120,
        clientY: 180,
        target: h.elements.chatTextarea
    });
    assert.strictEqual(h.resident.panelDrag, null, 'panelDrag must be null');
    assert.strictEqual(h.resident.panelResize, null, 'panelResize must be null');
    assert.strictEqual(res.prevented, false, 'preventDefault must NOT be called on textarea');
});

test('Button click isolation inside panel-view: Pointerdown on <button> NEVER initiates drag', () => {
    const h = createHarness();
    const res = h.dispatchPointerEvent('button', {
        type: 'pointerdown',
        button: 0,
        pointerId: 1,
        clientX: 200,
        clientY: 200,
        target: h.elements.chatSendBtn
    });
    assert.strictEqual(h.resident.panelDrag, null, 'panelDrag must be null');
    assert.strictEqual(res.prevented, false, 'preventDefault must NOT be called on button');
});

test('Close button inside panel-head: Pointerdown on header button NEVER initiates drag', () => {
    const h = createHarness();
    const res = h.dispatchPointerEvent('button', {
        type: 'pointerdown',
        button: 0,
        pointerId: 1,
        clientX: 380,
        clientY: 25,
        target: h.elements.panelCloseBtn
    });
    assert.strictEqual(h.resident.panelDrag, null, 'panelDrag must be null when clicking header button');
    assert.strictEqual(res.prevented, false, 'preventDefault must NOT be called on header close button');
});

test('Text selection in conversation / code / pre: Pointerdown NEVER initiates drag', () => {
    const h = createHarness();
    // Test code snippet inside pre inside conversation inside panel-view
    const res = h.dispatchPointerEvent('code', {
        type: 'pointerdown',
        button: 0,
        pointerId: 1,
        clientX: 150,
        clientY: 120,
        target: h.elements.codeSnippet
    });
    assert.strictEqual(h.resident.panelDrag, null, 'panelDrag must be null on code block');
    assert.strictEqual(res.prevented, false, 'preventDefault must NOT be called on code block');

    const res2 = h.dispatchPointerEvent('conversation', {
        type: 'pointerdown',
        button: 0,
        pointerId: 1,
        clientX: 160,
        clientY: 130,
        target: h.elements.chatConversation
    });
    assert.strictEqual(h.resident.panelDrag, null, 'panelDrag must be null on conversation container');
    assert.strictEqual(res2.prevented, false, 'preventDefault must NOT be called on conversation');
});

test('Panel header drag initiation: Pointerdown on header initiates panelDrag and notifies backend', () => {
    const h = createHarness();
    h.resident.boxes = [{ id: 'panel', x: 20, y: 30, width: 420, height: 560 }];
    const res = h.dispatchPointerEvent('head', {
        type: 'pointerdown',
        button: 0,
        pointerId: 1,
        clientX: 100,
        clientY: 20,
        target: h.elements.panelHead
    });
    assert(h.resident.panelDrag !== null, 'panelDrag must be active');
    assert.strictEqual(h.resident.panelDrag.initialBoxX, 20);
    assert.strictEqual(h.resident.panelDrag.initialBoxY, 30);
    assert.strictEqual(res.prevented, true, 'preventDefault must be called on drag handle');
    
    // Check IPC call to desktop_activity
    const lastIpc = h.ipcLog.find(c => c.cmd === 'desktop_activity' && c.payload.panelDrag === true);
    assert(lastIpc, 'Backend desktop_activity with panelDrag: true must be dispatched');
});

test('Decoupled drag gesture: 100 pointermove events update CSS transform with ZERO IPC calls', () => {
    const h = createHarness();
    h.resident.boxes = [{ id: 'panel', x: 20, y: 30, width: 420, height: 560 }];
    h.dispatchPointerEvent('head', {
        type: 'pointerdown',
        button: 0,
        pointerId: 1,
        clientX: 100,
        clientY: 20,
        target: h.elements.panelHead
    });

    const initialIpcCount = h.ipcLog.length;

    // Simulate 100 stream updates
    for (let i = 1; i <= 100; i++) {
        h.dispatchPointerEvent('head', {
            type: 'pointermove',
            pointerId: 1,
            clientX: 100 + i,
            clientY: 20 + i * 2,
            target: h.elements.panelHead
        });
    }

    assert.strictEqual(h.ipcLog.length, initialIpcCount, 'ZERO IPC calls during pointermove stream');
    assert.strictEqual(h.elements.panel.style._props.get('transform'), 'translate3d(100px, 200px, 0)');
    assert.strictEqual(h.resident.panelPositions['panel'].relX, 20 + 100);
    assert.strictEqual(h.resident.panelPositions['panel'].relY, 30 + 200);

    // Pointer up
    h.dispatchPointerEvent('head', {
        type: 'pointerup',
        pointerId: 1,
        clientX: 200,
        clientY: 220,
        target: h.elements.panelHead
    });

    assert.strictEqual(h.elements.panel.style._props.get('transform'), 'none', 'Transform must reset to none on pointerup');
    assert.strictEqual(h.resident.panelDrag, null, 'panelDrag must be cleared');
    const exitIpc = h.ipcLog.find(c => c.cmd === 'desktop_activity' && c.payload.panelDrag === false);
    assert(exitIpc, 'Backend desktop_activity with panelDrag: false must be dispatched on pointerup');
});


// =============================================================
// TEST SUITE 2: STRESS TEST PANEL RESIZING & CONSTRAINTS
// =============================================================
console.log('\n--- 2. STRESS TEST PANEL RESIZING & CONSTRAINTS ---');

test('Resize handle installation: ensureResizeHandles appends handle to panel', () => {
    const h = createHarness();
    h.resident.ensureResizeHandles();
    const handle = h.elements.panel.querySelector('.resident-resize-handle');
    assert(handle !== null, 'Resize handle must be created inside panel');
    assert.strictEqual(handle.dataset.resizeHandle, 'se');
});

test('Minimum constraint clamping: Attempt to shrink panel below 320x400 clamps to 320x400', () => {
    const h = createHarness();
    h.resident.ensureResizeHandles();
    const handle = h.elements.panel.querySelector('.resident-resize-handle');
    h.resident.boxes = [{ id: 'panel', x: 20, y: 30, width: 420, height: 560 }];

    // Start resize
    h.dispatchPointerEvent('handle', {
        type: 'pointerdown',
        button: 0,
        pointerId: 2,
        clientX: 440,
        clientY: 590,
        target: handle
    });
    assert(h.resident.panelResize !== null, 'panelResize must be initialized');

    // Attempt to shrink by -300px horizontally and -400px vertically (initial: 420x560 -> target: 120x160)
    h.dispatchPointerEvent('handle', {
        type: 'pointermove',
        pointerId: 2,
        clientX: 440 - 300,
        clientY: 590 - 400,
        target: handle
    });

    assert.strictEqual(h.resident.panelResize.newWidth, 320, 'Width must be clamped to >= 320px');
    assert.strictEqual(h.resident.panelResize.newHeight, 400, 'Height must be clamped to >= 400px');
    assert.strictEqual(h.elements.panel.style._props.get('width'), '320px');
    assert.strictEqual(h.elements.panel.style._props.get('height'), '400px');

    // Pointer up
    h.dispatchPointerEvent('handle', {
        type: 'pointerup',
        pointerId: 2,
        clientX: 140,
        clientY: 190,
        target: handle
    });

    assert.strictEqual(h.resident.panelResize, null, 'panelResize must be cleared on pointerup');
    const saved = JSON.parse(h.storage.get('axx.resident.panel-pos') || '{}');
    assert.strictEqual(saved['panel'].width, 320, 'localStorage must persist clamped width 320');
    assert.strictEqual(saved['panel'].height, 400, 'localStorage must persist clamped height 400');
});

test('Extreme shrinking attempt: -9999px delta clamps strictly to 320x400', () => {
    const h = createHarness();
    h.resident.ensureResizeHandles();
    const handle = h.elements.panel.querySelector('.resident-resize-handle');
    h.resident.boxes = [{ id: 'panel', x: 20, y: 30, width: 420, height: 560 }];

    h.dispatchPointerEvent('handle', {
        type: 'pointerdown',
        button: 0,
        pointerId: 3,
        clientX: 440,
        clientY: 590,
        target: handle
    });

    h.dispatchPointerEvent('handle', {
        type: 'pointermove',
        pointerId: 3,
        clientX: -9999,
        clientY: -9999,
        target: handle
    });

    assert.strictEqual(h.resident.panelResize.newWidth, 320, 'Extreme negative delta clamps width to 320');
    assert.strictEqual(h.resident.panelResize.newHeight, 400, 'Extreme negative delta clamps height to 400');
});

test('Screen boundary constraint: Attempt to resize panel larger than desktop work area', () => {
    const h = createHarness();
    h.resident.ensureResizeHandles();
    const handle = h.elements.panel.querySelector('.resident-resize-handle');
    h.resident.geometry = { workWidth: 1920, workHeight: 1080 };
    h.resident.boxes = [{ id: 'panel', x: 20, y: 30, width: 420, height: 560 }];

    h.dispatchPointerEvent('handle', {
        type: 'pointerdown',
        button: 0,
        pointerId: 4,
        clientX: 440,
        clientY: 590,
        target: handle
    });

    // Expand by 5000px
    h.dispatchPointerEvent('handle', {
        type: 'pointermove',
        pointerId: 4,
        clientX: 440 + 5000,
        clientY: 590 + 5000,
        target: handle
    });

    // workWidth - 40 = 1880, workHeight - 40 = 1040
    assert.strictEqual(h.resident.panelResize.newWidth, 1880, 'Width clamped to desktop workWidth - 40');
    assert.strictEqual(h.resident.panelResize.newHeight, 1040, 'Height clamped to desktop workHeight - 40');
});

test('Resize persistence in localStorage: Smooth expansion updates localStorage on gesture end', () => {
    const h = createHarness();
    h.resident.ensureResizeHandles();
    const handle = h.elements.panel.querySelector('.resident-resize-handle');
    h.resident.boxes = [{ id: 'panel', x: 20, y: 30, width: 420, height: 560 }];

    h.dispatchPointerEvent('handle', {
        type: 'pointerdown',
        button: 0,
        pointerId: 5,
        clientX: 440,
        clientY: 590,
        target: handle
    });

    h.dispatchPointerEvent('handle', {
        type: 'pointermove',
        pointerId: 5,
        clientX: 440 + 80,
        clientY: 590 + 140,
        target: handle
    });

    // Before pointerup, localStorage not yet updated
    assert.strictEqual(h.storage.get('axx.resident.panel-pos'), undefined);

    h.dispatchPointerEvent('handle', {
        type: 'pointerup',
        pointerId: 5,
        clientX: 520,
        clientY: 730,
        target: handle
    });

    const saved = JSON.parse(h.storage.get('axx.resident.panel-pos') || '{}');
    assert.strictEqual(saved['panel'].width, 500); // 420 + 80
    assert.strictEqual(saved['panel'].height, 700); // 560 + 140
});


// =============================================================
// TEST SUITE 3: VERIFY LAYOUT RECOVERY & OFF-SCREEN CLAMPING
// =============================================================
console.log('\n--- 3. VERIFY LAYOUT RECOVERY & BOUNDS CLAMPING ---');

test('Off-screen recovery during layout: Corrupt off-screen coordinates are clamped within workArea', async () => {
    const h = createHarness();
    // Simulate user previously dragged panel way off-screen to negative infinity
    h.resident.panelPositions['panel'] = {
        screenX: -99999,
        screenY: -99999,
        relX: -99999,
        relY: -99999,
        width: 420,
        height: 560
    };

    await h.resident.layout();

    const panelBox = h.resident.boxes.find(b => b.id === 'panel');
    assert(panelBox, 'Panel box must be calculated');

    // Geometry: spaceLeft: 900, spaceRight: 1020, margin: 72
    // minXBound = -900 + 72 = -828
    // maxXBound = 1020 - 420 - 72 = 528
    assert(panelBox.x >= -828, `Panel X (${panelBox.x}) must be clamped >= minXBound (-828)`);
    assert(panelBox.x <= 528, `Panel X (${panelBox.x}) must be clamped <= maxXBound (528)`);

    // Geometry: spaceAbove: 500, spaceBelow: 580, height: 560, margin: 72
    // minYBound = -500 + 72 = -428
    // maxYBound = 580 - 560 - 72 = -52
    assert(panelBox.y >= -428, `Panel Y (${panelBox.y}) must be clamped >= minYBound (-428)`);
    assert(panelBox.y <= -52, `Panel Y (${panelBox.y}) must be clamped <= maxYBound (-52)`);
});

test('Off-screen recovery: Positive overflow (+99999px) is clamped within workArea', async () => {
    const h = createHarness();
    h.resident.panelPositions['panel'] = {
        screenX: 99999,
        screenY: 99999,
        relX: 99999,
        relY: 99999,
        width: 420,
        height: 560
    };

    await h.resident.layout();

    const panelBox = h.resident.boxes.find(b => b.id === 'panel');
    assert(panelBox, 'Panel box must be calculated');
    assert(panelBox.x <= 528, `Panel X (${panelBox.x}) must be clamped <= 528`);
    assert(panelBox.y <= -52, `Panel Y (${panelBox.y}) must be clamped <= -52`);
});

test('resetLayout() execution: Clears localStorage, strips inline styles, restores defaults', async () => {
    const h = createHarness();
    // Setup modified panel
    h.storage.set('axx.resident.panel-pos', JSON.stringify({ panel: { width: 500, height: 700, relX: 200, relY: 100 } }));
    h.resident.panelPositions = { panel: { width: 500, height: 700, relX: 200, relY: 100 } };
    h.elements.panel.style.setProperty('width', '500px');
    h.elements.panel.style.setProperty('height', '700px');
    h.elements.panel.style.setProperty('transform', 'translate3d(50px, 50px, 0)');

    // Execute resetLayout()
    h.resident.resetLayout();

    assert.strictEqual(Object.keys(h.resident.panelPositions).length, 0, 'panelPositions in memory must be empty object');
    assert.strictEqual(h.storage.has('axx.resident.panel-pos'), false, 'localStorage key must be completely removed');
    assert.strictEqual(h.elements.panel.style._props.has('transform'), false, 'transform style must be removed');
    assert.strictEqual(h.elements.panel.style._props.has('width'), false, 'width style must be removed');
    assert.strictEqual(h.elements.panel.style._props.has('height'), false, 'height style must be removed');
});

test('Reset layout button click triggers resetLayout()', () => {
    const h = createHarness();
    let resetCalled = false;
    h.resident.resetLayout = () => { resetCalled = true; };

    // Simulate clicking resetDesktopLayoutBtn
    h.elements.resetDesktopLayoutBtn.dispatchEvent({ type: 'click' });
    assert.strictEqual(resetCalled, true, 'Clicking #reset-desktop-layout must invoke resident.resetLayout()');
});


// =============================================================
// TEST SUITE 4: MULTI-PANEL INDEPENDENCE & ISOLATION
// =============================================================
console.log('\n--- 4. MULTI-PANEL INDEPENDENCE & ISOLATION ---');

test('Multi-panel drag isolation: Dragging panel A does not alter panel B coordinates', () => {
    const h = createHarness();
    // Add second panel: flow-sheet
    const flowSheet = new MockElement('div', 'flow-sheet');
    const flowHead = new MockElement('div', '', 'flow-library-head');
    flowSheet.appendChild(flowHead);
    h.sandbox.document.body.appendChild(flowSheet);

    h.resident.boxes = [
        { id: 'panel', x: 20, y: 30, width: 420, height: 560 },
        { id: 'flow-sheet', x: -300, y: 50, width: 430, height: 460 }
    ];

    // Drag panel
    h.dispatchPointerEvent('head', {
        type: 'pointerdown',
        button: 0,
        pointerId: 10,
        clientX: 100,
        clientY: 20,
        target: h.elements.panelHead
    });

    h.dispatchPointerEvent('head', {
        type: 'pointermove',
        pointerId: 10,
        clientX: 150,
        clientY: 80,
        target: h.elements.panelHead
    });

    h.dispatchPointerEvent('head', {
        type: 'pointerup',
        pointerId: 10,
        clientX: 150,
        clientY: 80,
        target: h.elements.panelHead
    });

    assert.strictEqual(h.resident.panelPositions['panel'].relX, 20 + 50);
    assert.strictEqual(h.resident.panelPositions['panel'].relY, 30 + 60);
    assert.strictEqual(h.resident.panelPositions['flow-sheet'], undefined, 'flow-sheet coordinates must remain untouched');
});

test('Multi-panel resize isolation: Resizing panel A does not alter panel B dimensions', () => {
    const h = createHarness();
    h.resident.ensureResizeHandles();
    const handleA = h.elements.panel.querySelector('.resident-resize-handle');
    h.resident.boxes = [
        { id: 'panel', x: 20, y: 30, width: 420, height: 560 },
        { id: 'flow-sheet', x: -300, y: 50, width: 430, height: 460 }
    ];

    h.dispatchPointerEvent('handle', {
        type: 'pointerdown',
        button: 0,
        pointerId: 11,
        clientX: 440,
        clientY: 590,
        target: handleA
    });

    h.dispatchPointerEvent('handle', {
        type: 'pointermove',
        pointerId: 11,
        clientX: 440 + 60,
        clientY: 590 + 80,
        target: handleA
    });

    h.dispatchPointerEvent('handle', {
        type: 'pointerup',
        pointerId: 11,
        clientX: 500,
        clientY: 670,
        target: handleA
    });

    assert.strictEqual(h.resident.panelPositions['panel'].width, 480);
    assert.strictEqual(h.resident.panelPositions['panel'].height, 640);
    assert.strictEqual(h.resident.panelPositions['flow-sheet'], undefined, 'flow-sheet dimensions must remain untouched');
});


// =============================================================
// TEST SUITE 5: RUST BACKEND INVARIANT VERIFICATION
// =============================================================
console.log('\n--- 5. RUST BACKEND INVARIANT VERIFICATION ---');

const residentRsPath = path.resolve(__dirname, '../src-tauri/src/resident.rs');
const residentRs = fs.readFileSync(residentRsPath, 'utf8');

test('resident.rs implements ACTIVE_PANEL_DRAG and suppresses anchor drift in record_move', () => {
    assert(residentRs.includes('static ACTIVE_PANEL_DRAG: AtomicBool'), 'Must declare ACTIVE_PANEL_DRAG AtomicBool');
    assert(residentRs.includes('pub fn is_panel_drag_active() -> bool'), 'Must declare is_panel_drag_active');
    assert(residentRs.includes('pub fn set_panel_drag(active: bool)'), 'Must declare set_panel_drag');
    
    // In record_move, check condition
    const recordMoveIdx = residentRs.indexOf('pub fn record_move(');
    assert(recordMoveIdx !== -1, 'record_move must exist');
    const recordMoveBody = residentRs.slice(recordMoveIdx, recordMoveIdx + 600);
    assert(recordMoveBody.includes('is_panel_drag_active()'), 'record_move must check is_panel_drag_active()');
    assert(recordMoveBody.includes('LAST_LAYOUT_INSTANT.lock()'), 'record_move must check LAST_LAYOUT_INSTANT');
    assert(recordMoveBody.includes('Duration::from_millis(300)'), 'record_move must enforce 300ms layout stabilization window');
});

test('desktop_layout & desktop_activity accept panel_drag parameter', () => {
    const layoutIdx = residentRs.indexOf('pub fn desktop_layout(');
    const layoutBody = residentRs.slice(layoutIdx, layoutIdx + 500);
    assert(layoutBody.includes('panel_drag: Option<bool>'), 'desktop_layout must accept panel_drag');
    assert(layoutBody.includes('set_panel_drag(dragging)'), 'desktop_layout must update set_panel_drag');

    const activityIdx = residentRs.indexOf('pub fn desktop_activity(');
    const activityBody = residentRs.slice(activityIdx, activityIdx + 600);
    assert(activityBody.includes('panel_drag: Option<bool>'), 'desktop_activity must accept panel_drag');
    assert(activityBody.includes('set_panel_drag(dragging)'), 'desktop_activity must update set_panel_drag');
});

test('Tentacle HWND margin is 72px in ResidentDesktop.layout', () => {
    const marginMatch = residentDesktopCode.match(/margin\s*=\s*(\d+);/);
    assert(marginMatch, 'margin definition must exist in ResidentDesktop');
    assert.strictEqual(parseInt(marginMatch[1], 10), 72, 'margin must be exactly 72px to enclose curved Bezier tubes');
});


// =============================================================
// TEST SUITE 6: ADVERSARIAL STRESS & CORRUPTION HARNESS
// =============================================================
console.log('\n--- 6. ADVERSARIAL STRESS & CORRUPTION HARNESS ---');

test('Non-primary mouse clicks: Right-click (button=2) or middle-click (button=1) NEVER initiate drag or resize', () => {
    const h = createHarness();
    h.resident.ensureResizeHandles();
    const handle = h.elements.panel.querySelector('.resident-resize-handle');

    // Right-click on panel header
    h.dispatchPointerEvent('head', {
        type: 'pointerdown',
        button: 2,
        pointerId: 1,
        clientX: 100,
        clientY: 20,
        target: h.elements.panelHead
    });
    assert.strictEqual(h.resident.panelDrag, null, 'Right click on header must NOT start drag');

    // Middle-click on resize handle
    h.dispatchPointerEvent('handle', {
        type: 'pointerdown',
        button: 1,
        pointerId: 2,
        clientX: 440,
        clientY: 590,
        target: handle
    });
    assert.strictEqual(h.resident.panelResize, null, 'Middle click on handle must NOT start resize');
});

test('Abrupt gesture interruption: window blur / pointercancel resets CSS transform and releases capture', () => {
    const h = createHarness();
    h.resident.boxes = [{ id: 'panel', x: 20, y: 30, width: 420, height: 560 }];

    h.dispatchPointerEvent('head', {
        type: 'pointerdown',
        button: 0,
        pointerId: 1,
        clientX: 100,
        clientY: 20,
        target: h.elements.panelHead
    });
    h.dispatchPointerEvent('head', {
        type: 'pointermove',
        pointerId: 1,
        clientX: 160,
        clientY: 80,
        target: h.elements.panelHead
    });
    assert.strictEqual(h.elements.panel.style._props.get('transform'), 'translate3d(60px, 60px, 0)');

    // Fire pointercancel
    h.dispatchPointerEvent('head', {
        type: 'pointercancel',
        pointerId: 1,
        target: h.elements.panelHead
    });

    assert.strictEqual(h.resident.panelDrag, null, 'panelDrag must be null after pointercancel');
    assert.strictEqual(h.elements.panel.style._props.get('transform'), 'none', 'Transform must be reset to none after cancellation');
});

test('Extraneous pointerId isolation: Events from conflicting pointerIds are rejected', () => {
    const h = createHarness();
    h.resident.boxes = [{ id: 'panel', x: 20, y: 30, width: 420, height: 560 }];

    h.dispatchPointerEvent('head', {
        type: 'pointerdown',
        button: 0,
        pointerId: 1,
        clientX: 100,
        clientY: 20,
        target: h.elements.panelHead
    });

    // Conflicting event from pointerId 99
    h.dispatchPointerEvent('head', {
        type: 'pointermove',
        pointerId: 99,
        clientX: 999,
        clientY: 999,
        target: h.elements.panelHead
    });

    assert.strictEqual(h.resident.panelDrag.currentDx, 0, 'Pointermove with wrong pointerId must be ignored');
    assert.strictEqual(h.elements.panel.style._props.has('transform'), false, 'Transform must not be modified by wrong pointerId');
});

test('Poisoned localStorage recovery: Corrupted dimensions (strings, NaN, negatives) fallback cleanly', async () => {
    const h = createHarness();
    h.storage.set('axx.resident.panel-pos', JSON.stringify({
        panel: {
            width: "MALICIOUS_STRING",
            height: NaN,
            screenX: "OFF_SCREEN",
            screenY: -Infinity,
            relX: null,
            relY: undefined
        }
    }));
    h.resident.panelPositions = h.resident.loadPanelPositions();

    // Must not crash and must clamp properly
    await h.resident.layout();
    const panelBox = h.resident.boxes.find(b => b.id === 'panel');
    assert(panelBox, 'Panel box must be calculated');
    assert.strictEqual(panelBox.width, 420, 'Invalid width falls back to default 420');
    assert.strictEqual(panelBox.height, 450, 'Invalid height falls back to default 450 (for chat dock)');
    assert(Number.isFinite(panelBox.x), 'Panel X must be finite');
    assert(Number.isFinite(panelBox.y), 'Panel Y must be finite');
});

test('Throwing localStorage resilience: QuotaExceededError or SecurityError does not crash layout', () => {
    const h = createHarness();
    h.sandbox.localStorage.setItem = () => { throw new Error('QuotaExceededError'); };
    h.sandbox.localStorage.getItem = () => { throw new Error('SecurityError'); };

    // Should not throw
    assert.doesNotThrow(() => {
        h.resident.savePanelPositions();
        h.resident.loadPanelPositions();
        h.resident.resetLayout();
    }, 'ResidentDesktop operations must be completely resilient to localStorage exceptions');
});


// =============================================================
// SUMMARY
// =============================================================
console.log('\n================================================================');
console.log(`TOTAL TESTS: ${passed + failed} | PASSED: ${passed} | FAILED: ${failed}`);
console.log('================================================================');

if (failed > 0) {
    console.error('EMPIRICAL CHALLENGE DETECTED FAILURES!');
    process.exit(1);
} else {
    console.log('ALL EMPIRICAL CHALLENGE TESTS PASSED CONVINCINGLY!');
}
