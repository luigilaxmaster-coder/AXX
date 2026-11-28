'use strict';
const assert = require('node:assert/strict');
const stateMod = require('./notch-state.js');
const motionMod = require('./notch-motion.js');
const snapMod = require('./notch-snapshot.js');
const projMod = require('./notch-projections.js');

const {
  createInitialState,
  reduce,
  resolveLayout,
  isDockedPresentation,
  tendrilsAllowed,
  isNotchVisible,
  isInDockApproachBand
} = stateMod;

// 1. Complete Golden Path + Zero Tentacle Gate (INV-02)
{
  let s = createInitialState({ enabled: true, displayId: 'DISPLAY1' });
  const snap = snapMod.captureSnapshot({
    identityRevision: 3,
    settings: { form: 17, palette: 4, scale: 1.15, keepForm: true, actionMorph: true, motionStyle: 'tide' },
    studio: { exposure: 1.1, roughness: 0.04, living: true, intensity: 1.2 },
    camera: [-0.25, 0.14],
    finish: 'opticalglass',
    freePosition: { displayId: 'DISPLAY1', screenX: 900, screenY: 400, anchorX: 152, anchorY: 152, size: 280 }
  });

  let res = reduce(s, { type: 'DRAG_APPROACH_ENTER', displayId: 'DISPLAY1' });
  s = res.next;
  assert.equal(s.physical, 'approach');
  assert.equal(isNotchVisible(s), false);

  res = reduce(s, { type: 'DOCK_COMMIT', snapshot: snap, token: 'dock-1' });
  s = res.next;
  assert.equal(s.physical, 'retracting');
  assert.equal(tendrilsAllowed(s), false);
  assert.ok(res.effects.some(e => e.type === 'RETRACT_TENDRILS' && e.epoch === s.dockEpoch));

  // Attempting RETRACT_COMPLETE with tentacleLinks > 0 MUST roll back to free!
  const badRetract = reduce(s, { type: 'RETRACT_COMPLETE', epoch: s.dockEpoch, tentacleLinks: 2 });
  assert.equal(badRetract.next.physical, 'free');
  assert.equal(badRetract.next.lastError, 'TENTACLE_RETRACT_FAILED');

  // Valid RETRACT_COMPLETE with 0 links -> docking
  res = reduce(s, { type: 'RETRACT_COMPLETE', epoch: s.dockEpoch, tentacleLinks: 0 });
  s = res.next;
  assert.equal(s.physical, 'docking');
  assert.equal(isDockedPresentation(s), true);
  assert.equal(tendrilsAllowed(s), false);

  // Stale ACK from previous epoch or older revision is ignored
  const staleAck = reduce(s, { type: 'NATIVE_GEOMETRY_ACK', epoch: s.dockEpoch - 1, revision: s.geometryRevision, tentacleLinks: 0 });
  assert.equal(staleAck.next.physical, 'docking');

  // Valid ACK -> docked/compact
  res = reduce(s, { type: 'NATIVE_GEOMETRY_ACK', epoch: s.dockEpoch, revision: s.geometryRevision, tentacleLinks: 0 });
  s = res.next;
  assert.equal(s.physical, 'docked');
  assert.equal(s.size, 'compact');
  assert.equal(isNotchVisible(s), true);
  assert.equal(tendrilsAllowed(s), false);
  assert.ok(res.effects.some(e => e.type === 'SUSPEND_3D_RENDERER'));

  // Undocking -> free restores exact snapshot
  res = reduce(s, { type: 'UNDOCK_REQUEST', token: 'undock-1' });
  s = res.next;
  assert.equal(s.physical, 'undocking');
  assert.equal(tendrilsAllowed(s), false);
  const restoreEffect = res.effects.find(e => e.type === 'RESTORE_SNAPSHOT');
  assert.ok(restoreEffect);
  assert.equal(restoreEffect.snapshot.identity.settings.form, 17);
  assert.equal(restoreEffect.snapshot.identity.settings.palette, 4);
  assert.equal(restoreEffect.snapshot.identity.finish, 'opticalglass');

  res = reduce(s, { type: 'UNDOCK_COMPLETE', epoch: s.dockEpoch, avatarValid: true });
  s = res.next;
  assert.equal(s.physical, 'free');
  assert.equal(tendrilsAllowed(s), true);
  assert.ok(res.effects.some(e => e.type === 'ENABLE_FREE_TENDRILS'));
}

// 2. 500 repeated dock/undock stress cycles + interruption at approach/retracting/docking/undocking
{
  let s = createInitialState({ enabled: true });
  const snap = snapMod.captureSnapshot({ settings: { form: 0, palette: 0, scale: 1 }, finish: 'obsidian' });
  for (let i = 0; i < 500; i++) {
    s = reduce(s, { type: 'DOCK_COMMAND', snapshot: snap }).next;
    assert.equal(s.physical, 'retracting');
    s = reduce(s, { type: 'RETRACT_COMPLETE', epoch: s.dockEpoch, tentacleLinks: 0 }).next;
    assert.equal(s.physical, 'docking');
    s = reduce(s, { type: 'NATIVE_GEOMETRY_ACK', epoch: s.dockEpoch, revision: s.geometryRevision, tentacleLinks: 0 }).next;
    assert.equal(s.physical, 'docked');
    s = reduce(s, { type: 'UNDOCK_REQUEST' }).next;
    assert.equal(s.physical, 'undocking');
    s = reduce(s, { type: 'UNDOCK_COMPLETE', epoch: s.dockEpoch, avatarValid: true }).next;
    assert.equal(s.physical, 'free');
  }
  assert.equal(s.handledTokens.length, 0);

  // Interrupt each phase
  let r1 = reduce(createInitialState({ enabled: true }), { type: 'DRAG_APPROACH_ENTER' }).next;
  r1 = reduce(r1, { type: 'TRANSITION_CANCEL' }).next;
  assert.equal(r1.physical, 'free');

  let r2 = reduce(createInitialState({ enabled: true }), { type: 'DOCK_COMMAND', snapshot: snap }).next;
  r2 = reduce(r2, { type: 'TRANSITION_CANCEL' }).next;
  assert.equal(r2.physical, 'free');

  let r3 = reduce(createInitialState({ enabled: true }), { type: 'DOCK_COMMAND', snapshot: snap }).next;
  r3 = reduce(r3, { type: 'RETRACT_COMPLETE', epoch: r3.dockEpoch, tentacleLinks: 0 }).next;
  r3 = reduce(r3, { type: 'TRANSITION_CANCEL' }).next;
  assert.equal(r3.physical, 'free');

  let r4 = reduce(createInitialState({ enabled: true }), { type: 'DOCK_COMMAND', snapshot: snap }).next;
  r4 = reduce(r4, { type: 'RETRACT_COMPLETE', epoch: r4.dockEpoch, tentacleLinks: 0 }).next;
  r4 = reduce(r4, { type: 'NATIVE_GEOMETRY_ACK', epoch: r4.dockEpoch, revision: r4.geometryRevision, tentacleLinks: 0 }).next;
  r4 = reduce(r4, { type: 'UNDOCK_REQUEST' }).next;
  r4 = reduce(r4, { type: 'TRANSITION_CANCEL' }).next;
  assert.equal(r4.physical, 'docked');
}

// 3. Portal drag enter/leave restores exact previous surface, Drop token deduplicates
{
  const snap = snapMod.captureSnapshot({ settings: { form: 1, palette: 1, scale: 1 }, finish: 'prism' });
  let s = createInitialState({ enabled: true });
  s = reduce(s, { type: 'DOCK_COMMAND', snapshot: snap }).next;
  s = reduce(s, { type: 'RETRACT_COMPLETE', epoch: s.dockEpoch, tentacleLinks: 0 }).next;
  s = reduce(s, { type: 'NATIVE_GEOMETRY_ACK', epoch: s.dockEpoch, revision: s.geometryRevision, tentacleLinks: 0 }).next;
  s = reduce(s, { type: 'SET_SURFACE_SIZE', size: 'expanded', content: 'media', activate: true }).next;
  assert.equal(s.size, 'expanded');
  assert.equal(s.content, 'media');

  s = reduce(s, { type: 'PORTAL_DRAG_ENTER' }).next;
  assert.equal(s.content, 'portal');
  assert.equal(s.size, 'peek');

  s = reduce(s, { type: 'PORTAL_DRAG_LEAVE' }).next;
  assert.equal(s.size, 'expanded');
  assert.equal(s.content, 'media');

  const d1 = reduce(s, { type: 'PORTAL_DROP', targetId: 'chat-attach', token: 'drop-abc', files: [{ name: 'a.txt' }] });
  assert.equal(d1.effects.filter(e => e.type === 'DISPATCH_PORTAL_DROP').length, 1);
  const d2 = reduce(d1.next, { type: 'PORTAL_DROP', targetId: 'chat-attach', token: 'drop-abc', files: [{ name: 'a.txt' }] });
  assert.equal(d2.effects.length, 0);
}

// 4. Fullscreen suppression hides notch without ending activities; feature flag off recovers to free
{
  const snap = snapMod.captureSnapshot({ settings: { form: 3, palette: 2, scale: 1 }, finish: 'smoke' });
  let s = createInitialState({ enabled: true });
  s = reduce(s, { type: 'DOCK_COMMAND', snapshot: snap }).next;
  s = reduce(s, { type: 'RETRACT_COMPLETE', epoch: s.dockEpoch, tentacleLinks: 0 }).next;
  s = reduce(s, { type: 'NATIVE_GEOMETRY_ACK', epoch: s.dockEpoch, revision: s.geometryRevision, tentacleLinks: 0 }).next;
  s = reduce(s, { type: 'SYNC_PROJECTIONS', source: 'timer', sourceEpoch: 'local', projections: [{ id: 'timer:1', source: 'timer', revision: 1, status: 'running', progress: { kind: 'determinate', value: 0.4 } }] }).next;
  assert.deepEqual(s.activityIds, ['timer:1']);

  s = reduce(s, { type: 'SET_VISIBILITY', visibility: 'fullscreenSuppressed' }).next;
  assert.equal(isNotchVisible(s), false);
  assert.deepEqual(s.activityIds, ['timer:1']);

  const disabled = reduce(s, { type: 'SET_ENABLED', enabled: false });
  assert.equal(disabled.next.physical, 'free');
  assert.ok(disabled.effects.some(e => e.type === 'RESTORE_SNAPSHOT'));
}

// 5. Stale projection revision rejection & epoch reset
{
  let s = createInitialState({ enabled: true });
  s = reduce(s, {
    type: 'SYNC_PROJECTIONS',
    source: 'commands',
    sourceEpoch: 'ep1',
    projections: [{ id: 'cmd:1', source: 'commands', sourceEpoch: 'ep1', revision: 5, status: 'awaiting_user' }]
  }).next;
  assert.equal(s.attention, 'approval');

  // Stale revision 3 in same epoch must not overwrite revision 5
  s = reduce(s, {
    type: 'SYNC_PROJECTIONS',
    source: 'commands',
    sourceEpoch: 'ep1',
    projections: [{ id: 'cmd:1', source: 'commands', sourceEpoch: 'ep1', revision: 3, status: 'completed' }]
  }).next;
  assert.deepEqual(s.activityIds, []);

  // New epoch ep2 allows revision 1
  s = reduce(s, {
    type: 'SYNC_PROJECTIONS',
    source: 'commands',
    sourceEpoch: 'ep2',
    projections: [{ id: 'cmd:1', source: 'commands', sourceEpoch: 'ep2', revision: 1, status: 'completed' }]
  }).next;
  assert.deepEqual(s.activityIds, ['cmd:1']);
  assert.equal(s.attention, 'completed');
}

// 6. Identity Snapshot Matrix across 24 forms x 9 palettes x 4 finishes = 864 combinations (INV-03)
{
  const finishes = ['obsidian', 'prism', 'smoke', 'opticalglass'];
  let count = 0;
  for (let form = 0; form < 24; form++) {
    for (let palette = 0; palette < 9; palette++) {
      for (const finish of finishes) {
        const fakeStore = { data: { settings: { form, palette, scale: 1.0, keepForm: true } }, save() {} };
        let applied = null;
        const fakeRenderer = {
          configure(s) { applied = { ...s }; },
          setStudio(st) { applied.studio = st; },
          setCamera20(cam) { applied.camera = cam; },
          setFinish(f) { applied.finish = f; },
          setForm(f) { applied.activeForm = f; }
        };
        const snap = snapMod.captureSnapshot({
          identityRevision: count + 1,
          settings: fakeStore.data.settings,
          studio: { exposure: 1, roughness: 0.05 },
          camera: [-0.18, 0.08],
          finish
        });
        // Mutate store while docked, then restore
        fakeStore.data.settings = { form: 0, palette: 0, scale: 0.7 };
        const res = snapMod.restoreSnapshot(snap, { store: fakeStore, renderer: fakeRenderer });
        assert.equal(res.restored, true);
        assert.equal(fakeStore.data.settings.form, form);
        assert.equal(fakeStore.data.settings.palette, palette);
        assert.equal(applied.finish, finish);
        assert.equal(applied.activeForm, form);
        count++;
      }
    }
  }
  assert.equal(count, 864);
}

// 7. Continuous retargeting motion test (C0/C1 continuity + Reduce Motion)
{
  const ch = new motionMod.MotionChannel(0, 300, 32, 0);
  ch.setTarget(200, false);
  for (let i = 0; i < 6; i++) ch.step(1 / 60, false);
  const posAtInterrupt = ch.value;
  const velAtInterrupt = ch.velocity;
  assert.ok(posAtInterrupt > 0 && posAtInterrupt < 200);
  assert.ok(velAtInterrupt > 0);
  // Retarget to 40: velocity and value must be preserved continuously!
  ch.setTarget(40, false);
  assert.equal(ch.value, posAtInterrupt);
  assert.equal(ch.velocity, velAtInterrupt);

  // Reduce motion snaps immediately
  ch.setTarget(300, true);
  assert.equal(ch.value, 300);
  assert.equal(ch.velocity, 0);
}

// 8. Layout resolver bounds across DPI scales & narrow screens
{
  let s = createInitialState({ enabled: true });
  s = { ...s, physical: 'docked', size: 'expanded', content: 'intent' };
  for (const work of [
    { x: 0, y: 0, width: 1536, height: 816 },
    { x: -1920, y: 0, width: 1280, height: 720 },
    { x: 0, y: 0, width: 768, height: 540 },
    { x: 0, y: 0, width: 320, height: 480 }
  ]) {
    for (const uiScale of [0.9, 1.0, 1.15, 1.25]) {
      const box = resolveLayout(s, work, uiScale, { activityCount: 4 });
      assert.ok(box.width > 0 && box.width <= work.width);
      assert.ok(box.height > 0 && box.height <= work.height);
      assert.ok(box.x >= 0 && box.x + box.width <= work.width);
      assert.equal(box.y, 0);
    }
  }
  assert.equal(isInDockApproachBand(30, 48, 24, false), true);
  assert.equal(isInDockApproachBand(60, 48, 24, false), false);
  assert.equal(isInDockApproachBand(60, 48, 24, true), true); // hysteresis holds inside 48+24=72
  assert.equal(isInDockApproachBand(80, 48, 24, true), false);
}

// 9. Honest progress in projections (never fakes determinate %)
{
  const fakeAxx = {
    app: { store: { data: { timer: { id: 't1', kind: 'focus', status: 'running', durationMs: 60000, deadline: 1030000, updatedAt: 1000000, revision: 1 } } } },
    remaining: (t, now) => Math.max(0, t.deadline - now),
    companion: { pending: {}, data: { draft: '' }, brain: { connected: false } },
    desktop: { ready: true }
  };
  const proj = projMod.collectAllProjections(fakeAxx, 1000000);
  const timer = proj.projections.find(p => p.kind === 'timer');
  const chat = proj.projections.find(p => p.kind === 'chat');
  assert.equal(timer.progress.kind, 'determinate');
  assert.ok(Math.abs(timer.progress.fraction - 0.5) < 1e-6);
  assert.equal(chat.progress.kind, 'indeterminate');
}

console.log('PASS: notch-state (500 cycles + interruptions + epochs), zero-tendril guard, 864x identity matrix, C0/C1 motion retargeting, layout bounds, and honest projections');
