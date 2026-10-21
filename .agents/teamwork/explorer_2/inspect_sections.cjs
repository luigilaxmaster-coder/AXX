const fs = require('fs');
const path = require('path');

const axxPath = path.resolve(process.cwd(), '1.AXX/Axx.html');
const content = fs.readFileSync(axxPath, 'utf8');

const sections = [
    'chat', 'tools', 'dictation', 'translation', 'music', 
    'recording', 'timer', 'files', 'commands', 'settings', 
    'menu', 'help', 'error'
];

console.log('--- Inspecting UI Sections in Axx.html ---');

// Search for FEATURES definition
const featuresMatch = content.match(/FEATURES\s*=\s*(\[[\s\S]*?\]);/);
if (featuresMatch) {
    console.log('\nAxx.FEATURES definition found:');
    try {
        // extract feature objects roughly
        const feats = featuresMatch[1].match(/\{[^{}]+\}/g);
        console.log(`Total features in catalog: ${feats ? feats.length : 0}`);
        if (feats) {
            feats.forEach(f => {
                const idMatch = f.match(/id:\s*['"]([^'"]+)['"]/);
                const titleMatch = f.match(/title:\s*['"]([^'"]+)['"]/);
                if (idMatch) console.log(`  - Feature: ${idMatch[1]} (${titleMatch ? titleMatch[1] : ''})`);
            });
        }
    } catch (e) {
        console.error(e);
    }
}

// Search for tool IDs, views, and handlers for each required section
function searchKey(key, regex) {
    const lines = content.split('\n');
    const matches = [];
    lines.forEach((l, idx) => {
        if (regex.test(l)) {
            matches.push({ line: idx + 1, text: l.trim() });
        }
    });
    return matches;
}

console.log('\n--- Dictation UI & Handlers ---');
searchKey('dictation', /dictat|dictationLauncher|openReview|ink-review/).slice(0, 10).forEach(m => console.log(`  Line ${m.line}: ${m.text.slice(0, 120)}`));

console.log('\n--- Translation UI & Handlers ---');
searchKey('translation', /translation|symbiosis.*translat|VoiceTranslation/).slice(0, 10).forEach(m => console.log(`  Line ${m.line}: ${m.text.slice(0, 120)}`));

console.log('\n--- Music UI & Handlers ---');
searchKey('music', /MusicStudio|LocalMusic|view-audio|openMusic|source-local|source-youtube/).slice(0, 10).forEach(m => console.log(`  Line ${m.line}: ${m.text.slice(0, 120)}`));

console.log('\n--- Recording UI & Handlers ---');
searchKey('recording', /CaptureStudio|ScreenSession|view-capture|startRecording|stopRecording/).slice(0, 10).forEach(m => console.log(`  Line ${m.line}: ${m.text.slice(0, 120)}`));

console.log('\n--- Commands UI & Handlers ---');
searchKey('commands', /command-library|view-actions|resolveCommand/).slice(0, 10).forEach(m => console.log(`  Line ${m.line}: ${m.text.slice(0, 120)}`));
