const fs = require('node:fs');
const path = require('node:path');

function requirePlaywright() {
  let resolved;
  try { resolved = require.resolve('playwright'); }
  catch (error) {
    if (error.code !== 'MODULE_NOT_FOUND') throw error;
    const bundled = process.env.USERPROFILE && path.join(process.env.USERPROFILE,
      '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
    if (!bundled || !fs.existsSync(path.join(bundled, 'package.json'))) throw error;
    return require(bundled);
  }
  return require(resolved);
}

async function launchChromium(chromium) {
  const explicit = process.env.AXX_TEST_CHROMIUM;
  if (explicit) return chromium.launch({ headless: true, executablePath: explicit });
  try { return await chromium.launch({ headless: true }); }
  catch (error) {
    // shortcut: legacy Codex browser 1248 only; remove after its bundled default is installed.
    const fallback = process.platform === 'win32' && process.env.LOCALAPPDATA &&
      path.join(process.env.LOCALAPPDATA,
        'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe');
    if (!/Executable doesn't exist at /.test(error.message) || !fallback || !fs.existsSync(fallback)) throw error;
    return chromium.launch({ headless: true, executablePath: fallback });
  }
}

module.exports = { requirePlaywright, launchChromium };
