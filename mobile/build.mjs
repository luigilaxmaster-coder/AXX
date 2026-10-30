import {mkdir, copyFile, cp, readFile, writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
await mkdir(new URL('www', import.meta.url), {recursive:true});
await copyFile(new URL('client.html', import.meta.url), new URL('www/index.html', import.meta.url));
for (const name of ['css', 'icons']) await cp(new URL(name, import.meta.url), new URL('www/'+name, import.meta.url), {recursive:true});
await mkdir(new URL('www/js', import.meta.url), {recursive:true});
await copyFile(new URL('js/live-client.js', import.meta.url), new URL('www/js/live-client.js', import.meta.url));
await copyFile(new URL('js/avatar-renderer.js', import.meta.url), new URL('www/js/avatar-renderer.js', import.meta.url));
await copyFile(new URL('js/display.js', import.meta.url), new URL('www/js/display.js', import.meta.url));
await copyFile(new URL('js/avatar-customization.js', import.meta.url), new URL('www/js/avatar-customization.js', import.meta.url));
await copyFile(new URL('js/remote-voice.js', import.meta.url), new URL('www/js/remote-voice.js', import.meta.url));
await copyFile(new URL('js/remote-control.js', import.meta.url), new URL('www/js/remote-control.js', import.meta.url));
await copyFile(new URL('js/transfer.js', import.meta.url), new URL('www/js/transfer.js', import.meta.url));
await copyFile(new URL('js/file-dictation.js', import.meta.url), new URL('www/js/file-dictation.js', import.meta.url));
await copyFile(new URL('js/mission-continuity.js', import.meta.url), new URL('www/js/mission-continuity.js', import.meta.url));
// Use the exact desktop geometry/material code; no independently maintained mobile avatar.
const desktop = await readFile(new URL('../1.AXX/Axx.html', import.meta.url), 'utf8');
const start = desktop.indexOf('<script>"use strict";');
const marker = '    Axx.SoftwareRenderer = SoftwareRenderer;';
const end = desktop.indexOf('})(Axx || (Axx = {}));', desktop.indexOf(marker));
if (start < 0 || end < start || desktop.indexOf(marker) < start) throw new Error('Desktop renderer boundary changed; update extraction before building');
const renderer = desktop.slice(start + '<script>'.length, end + '})(Axx || (Axx = {}));'.length);
if (renderer.includes('new Axx.App(') || !renderer.includes('class SoftwareRenderer')) throw new Error('Invalid desktop renderer extraction');
await writeFile(new URL('www/js/desktop-avatar.js', import.meta.url), renderer);
await writeFile(new URL('www/renderer-source.json', import.meta.url), JSON.stringify({source:'1.AXX/Axx.html',sha256:createHash('sha256').update(renderer).digest('hex')},null,2));
const contract = await readFile(new URL('companion-contract.json', import.meta.url), 'utf8');
await writeFile(new URL('www/companion-build.json', import.meta.url), JSON.stringify({
  versions: {desktop:JSON.parse(await readFile(new URL('../package.json', import.meta.url),'utf8')).version,android:JSON.parse(await readFile(new URL('package.json', import.meta.url),'utf8')).version,android_code:Number((await readFile(new URL('android/app/build.gradle',import.meta.url),'utf8')).match(/\bversionCode\s+(\d+)\b/)[1])},
  protocol:JSON.parse(contract).id,
  contract_sha256:createHash('sha256').update(contract.replace(/\r\n/g,'\n')).digest('hex'),
  renderer_sha256:createHash('sha256').update(renderer).digest('hex')
},null,2));
