const fs = require('fs');
const path = require('path');

const axxPath = path.resolve(process.cwd(), '1.AXX/Axx.html');
const refPath = path.resolve(process.cwd(), 'reference/Axx_reference_v20.html');

const axxHtml = fs.readFileSync(axxPath, 'utf8');
const refHtml = fs.readFileSync(refPath, 'utf8');

console.log('--- Comparison: Axx.html vs Axx_reference_v20.html ---');
console.log('Axx.html size:', axxHtml.length, 'lines:', axxHtml.split('\n').length);
console.log('Reference v20 size:', refHtml.length, 'lines:', refHtml.split('\n').length);

// Compare CSS variables in :root
const getRootVars = (content) => {
    const rootMatches = [...content.matchAll(/--([a-z0-9_-]+)\s*:\s*([^;]+);/gi)];
    const vars = {};
    rootMatches.forEach(m => vars[m[1]] = m[2].trim());
    return vars;
};

const axxVars = getRootVars(axxHtml.substring(0, 50000));
const refVars = getRootVars(refHtml.substring(0, 50000));
console.log('\nRoot CSS Variables in Axx.html:', axxVars);
console.log('\nRoot CSS Variables in Reference v20:', refVars);

// Compare major CSS rules
const checkRule = (selector, name) => {
    const inAxx = axxHtml.includes(selector);
    const inRef = refHtml.includes(selector);
    console.log(`Selector ${name} (${selector}): in Axx.html = ${inAxx}, in Ref = ${inRef}`);
};

checkRule('.axx-resident', 'Axx resident class');
checkRule('.dock-shell', 'Dock shell');
checkRule('#flow-fan', 'Flow fan (radial menu)');
checkRule('.reach-tray', 'Reach tray');
checkRule('#panel', 'Panel');
checkRule('.stage', 'Stage (3D canvas container)');
checkRule('.companion-intro', 'Companion intro text');
checkRule('.home-tools-grid', 'Home tools grid');
checkRule('.presence-controls', 'Presence controls');

// Check Palettes
const getPalettes = (content) => {
    const m = content.match(/PALETTES\s*=\s*(\[[\s\S]*?\]);/);
    if (!m) return [];
    try {
        const matches = [...m[1].matchAll(/name:\s*['"]([^'"]+)['"]/g)];
        return matches.map(x => x[1]);
    } catch { return []; }
};
console.log('\nPalettes in Axx.html:', getPalettes(axxHtml));
console.log('Palettes in Ref v20:', getPalettes(refHtml));

// Check Forms
const getForms = (content) => {
    const m = content.match(/FORMS\s*=\s*(\[[\s\S]*?\]);/);
    if (!m) return [];
    try {
        const matches = [...m[1].matchAll(/name:\s*['"]([^'"]+)['"]/g)];
        return matches.map(x => x[1]);
    } catch { return []; }
};
console.log('\nForms in Axx.html (' + getForms(axxHtml).length + '):', getForms(axxHtml).slice(0, 10));
console.log('Forms in Ref v20 (' + getForms(refHtml).length + '):', getForms(refHtml).slice(0, 10));
