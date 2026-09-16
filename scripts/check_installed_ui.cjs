const {_electron: electron} = require('../.verify/node_modules/playwright');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
(async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'jarvis-installed-ui-'));
  let app;
  try {
    const env = {...process.env, JARVISS_ROOT: root, JARVISS_APP_DATA: path.join(root, 'app'),
      PATH: process.env.SystemRoot + '\\System32;' + process.env.SystemRoot};
    delete env.ELECTRON_RUN_AS_NODE;
    delete env.JARVISS_BUNDLED_RUNTIME;
    delete env.JARVISS_RESOURCES;
    app = await electron.launch({executablePath: process.argv[2], env, timeout: 90000});
    const page = await app.firstWindow();
    const plan = await page.evaluate(() => window.jarviss.command('setup_plan'));
    assert.equal(plan.hardware.system, 'Windows');
    assert.ok(plan.models.length >= 2);
    assert.equal(plan.components.guides, true);
    assert.equal(await page.locator('#setup').isVisible(), true);
    await page.waitForFunction(count => document.querySelectorAll('#setup-models input').length === count, plan.models.length, {timeout: 60000});
    assert.equal(await page.locator('#setup-models input').count(), plan.models.length);
    await page.screenshot({path: path.join(process.env.RUNNER_TEMP, 'jarvis-signed-startup.png')});
    console.log('PASS installed Electron app opens setup and communicates with its bundled backend without Python or Node on PATH');
  } finally {
    if (app) await app.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
