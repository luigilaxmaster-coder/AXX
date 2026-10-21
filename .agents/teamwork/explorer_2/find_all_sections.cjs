const fs = require('fs');
const path = require('path');

const axxPath = path.resolve(process.cwd(), '1.AXX/Axx.html');
const content = fs.readFileSync(axxPath, 'utf8');
const lines = content.split('\n');

function findOccurrences(regex, max = 5) {
    const res = [];
    lines.forEach((l, idx) => {
        if (regex.test(l)) {
            res.push({ line: idx + 1, text: l.trim().slice(0, 140) });
        }
    });
    return res.slice(0, max);
}

console.log('=== SECTION 1: CONVERSACIÓN ===');
console.log(findOccurrences(/view-chat|chat-composer|chat-input|openFeature\('chat'\)/));

console.log('=== SECTION 2: HERRAMIENTAS ===');
console.log(findOccurrences(/flow-fan|flow-quick|flow-library|renderQuick/));

console.log('=== SECTION 3: DICTADO (UI) ===');
console.log(findOccurrences(/ink-review|dictation|DictationBuffer|VoiceInk/));

console.log('=== SECTION 4: TRADUCCIÓN (UI) ===');
console.log(findOccurrences(/view-translation|VoiceTranslation|v18-translation/));

console.log('=== SECTION 5: MÚSICA (UI) ===');
console.log(findOccurrences(/view-audio|view-music|MusicStudio|openMusicSources/));

console.log('=== SECTION 6: GRABACIÓN (UI) ===');
console.log(findOccurrences(/ScreenSession|CaptureStudio|a11-screen/));

console.log('=== SECTION 7: TEMPORIZADOR (UI) ===');
console.log(findOccurrences(/view-timer|start-timer|orbit-timer-presets/));

console.log('=== SECTION 8: ARCHIVOS (UI) ===');
console.log(findOccurrences(/view-files|reach-tray|reach-preview/));

console.log('=== SECTION 9: COMANDOS (UI) ===');
console.log(findOccurrences(/view-actions|command-library|command-form/));

console.log('=== SECTION 10: CONFIGURACIÓN (UI) ===');
console.log(findOccurrences(/view-settings|desktop-runtime|always-top/));

console.log('=== SECTION 11: MENÚS ===');
console.log(findOccurrences(/context-menu|chat20-menu|dock-bar/));

console.log('=== SECTION 12: AYUDAS ===');
console.log(findOccurrences(/view-help|panel-info-fold|flow-help/));

console.log('=== SECTION 13: ESTADOS DE ERROR ===');
console.log(findOccurrences(/fatal|toast|render-notice|connection-message\.error/));
