/* BeatTracker on synthetic Windows output-meter samples (20 Hz, like system_media_status). */
const assert = require('node:assert/strict');
global.window = {Axx: {}};
require('./rhythm-egg.js');
const {BeatTracker} = window.Axx;

let seed = 7;
const rand = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);

// Kick drum at `bpm` over a music bed; the meter reports the peak of each 50 ms window, starting at an odd offset.
function song(bpm, seconds, {bed = .14, kick = .75, start = 1337, jitter = 12} = {}) {
    const period = 60000 / bpm, out = [], beats = [];
    for (let t = start; t < start + seconds * 1000; t += 50) {
        const since = (t - start) % period;
        out.push([t, Math.min(1, bed + rand() * .05 + (since < 50 ? kick : since < 100 ? kick * .45 : since < 150 ? kick * .2 : 0))]);
    }
    for (let b = start; b < start + seconds * 1000; b += period) beats.push(b + (rand() - .5) * jitter);
    return {samples: out, beats, period, start};
}
function play(tracker, samples, step = 16) {  // samples arrive at 20 Hz; frames are rendered at ~60 Hz in between
    const frames = [];
    let i = 0;
    for (let t = samples[0][0]; t <= samples.at(-1)[0]; t += step) {
        while (i < samples.length && samples[i][0] <= t) { tracker.sample(samples[i][1], samples[i][0]); i++; }
        frames.push([t, tracker.frame(t)]);
    }
    return frames;
}

for (const bpm of [120, 95, 140]) {
    const tracker = new BeatTracker(), {samples, period, start} = song(bpm, 12);
    const frames = play(tracker, samples), last = frames.at(-1)[1];
    assert.ok(last.locked, `${bpm} BPM: locked`);
    assert.ok(Math.abs(last.bpm - bpm) <= 2, `${bpm} BPM: estimated ${last.bpm}`);
    const first = frames.find(([, f]) => f.locked)[1];  // the first tempo shown is already right, not a warm-up guess
    assert.ok(Math.abs(first.bpm - bpm) <= 2, `${bpm} BPM: first shown ${first.bpm}`);
    // Phase: in the last 4 s, every pulse peak lands within 40 ms of a real kick (the meter only samples every 50 ms).
    const peaks = frames.filter(([t, f], k) => t > start + 8000 && f.pulse > .85 && !(frames[k - 1]?.[1].pulse > .85)).map(([t]) => t);
    assert.ok(peaks.length >= Math.floor(4000 / period) - 1, `${bpm} BPM: ${peaks.length} beats in 4 s`);
    for (const t of peaks) {
        const off = ((t - start) % period + period) % period, err = Math.min(off, period - off);
        assert.ok(err <= 40, `${bpm} BPM: beat ${err.toFixed(0)} ms off the kick`);
    }
    console.log(`PASS ${bpm} BPM -> ${last.bpm} BPM, confidence ${last.confidence.toFixed(2)}, ${peaks.length} beats in phase`);
}

{   // kick on the beat plus a softer snare/hat between beats: the beat is still the kick, at 120 BPM
    const tracker = new BeatTracker(), start = 1337, period = 500, samples = [];
    for (let t = start; t < start + 12000; t += 50) {
        const k = (t - start) % period, h = (t - start + period / 2) % period;
        samples.push([t, Math.min(1, .12 + rand() * .04 + (k < 50 ? .75 : k < 100 ? .3 : 0) + (h < 50 ? .38 : 0))]);
    }
    const frames = play(tracker, samples), last = frames.at(-1)[1];
    assert.ok(last.locked && Math.abs(last.bpm - 120) <= 2, `kick + offbeat: ${last.bpm} BPM`);
    const peaks = frames.filter(([t, f], k) => t > start + 8000 && f.pulse > .85 && !(frames[k - 1]?.[1].pulse > .85)).map(([t]) => t);
    for (const t of peaks) { const off = (t - start) % period; assert.ok(Math.min(off, period - off) <= 40, `pulse on the snare (${off} ms)`); }
    console.log(`PASS kick + offbeat -> ${last.bpm} BPM on the kick`);
}
{   // silence: no onsets, no tempo, no pulse
    const tracker = new BeatTracker(), samples = Array.from({length: 200}, (_, i) => [i * 50, 0]);
    const last = play(tracker, samples).at(-1)[1];
    assert.deepEqual([last.locked, last.bpm, last.pulse, tracker.onsets.length], [false, 0, 0, 0]);
    console.log('PASS silence stays still');
}
{   // steady loud sound without a beat (noise, a sustained chord): never confidently locked
    const tracker = new BeatTracker(), samples = Array.from({length: 240}, (_, i) => [i * 50, .45 + rand() * .06]);
    const frames = play(tracker, samples);
    assert.ok(frames.filter(([, f]) => f.locked).length < frames.length * .1, 'noise must not look like a beat');
    console.log('PASS beatless sound is not treated as rhythm');
}
{   // the music stops: the pulse fades out within 3 s
    const tracker = new BeatTracker(), {samples} = song(120, 8);
    const end = samples.at(-1)[0];
    const quiet = Array.from({length: 80}, (_, i) => [end + 50 * (i + 1), 0]);
    const last = play(tracker, [...samples, ...quiet]).at(-1)[1];
    assert.deepEqual([last.locked, last.pulse], [false, 0]);
    console.log('PASS stops when the music stops');
}
{   // pre-lock instant pulse fires on early kicks before 6-onset lock, and low-volume music still locks
    const tracker = new BeatTracker(), {samples} = song(110, 12, {bed: .04, kick: .18});
    const frames = play(tracker, samples);
    const earlyInstant = frames.some(([t, f]) => t < samples[0][0] + 2000 && !f.locked && f.instant > .5);
    const last = frames.at(-1)[1];
    assert.ok(earlyInstant, 'pre-lock instant transient responds immediately');
    assert.ok(last.locked && Math.abs(last.bpm - 110) <= 2, `low-volume 110 BPM -> ${last.bpm}`);
    console.log(`PASS low-volume 110 BPM + early instant pulse -> ${last.bpm} BPM`);
}
