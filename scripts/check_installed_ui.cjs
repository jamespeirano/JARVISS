const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
const {_electron: electron} = require(require.resolve('playwright', {
  paths: [path.resolve(__dirname, '../electron'), path.resolve(__dirname, '../.verify')],
}));
(async () => {
  if (!process.argv[2]) throw new Error('Pass the built application executable.');
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'jarvis-installed-ui-'));
  const screenshot = path.join(process.env.RUNNER_TEMP || os.tmpdir(), 'jarvis-signed-startup.png');
  let app;
  try {
    const env = {...process.env, JARVISS_ROOT: root, JARVISS_DATA: path.join(root, 'local-data'),
      JARVISS_APP_DATA: path.join(root, 'app'), PATH: process.platform === 'win32'
        ? [path.join(process.env.SystemRoot, 'System32'), process.env.SystemRoot].join(path.delimiter)
        : '/usr/bin:/bin'};
    for (const name of ['ELECTRON_RUN_AS_NODE', 'JARVISS_BUNDLED_RUNTIME', 'JARVISS_RESOURCES', 'PYTHONHOME', 'PYTHONPATH']) delete env[name];
    app = await electron.launch({executablePath: path.resolve(process.argv[2]), env, timeout: 120000});
    const page = await app.firstWindow({timeout: 120000});
    // Check the actual screen before calling the bridge: an empty renderer is a failed build.
    await page.locator('#setup.visible').waitFor({state: 'visible', timeout: 120000});
    await page.waitForFunction(() => document.querySelector('#setup-models input'), {}, {timeout: 120000});
    assert.equal(await page.locator('#assistant').isVisible(), false);
    assert.equal(await page.evaluate(() => typeof window.require), 'undefined');
    const plan = await page.evaluate(() => window.jarviss.command('setup_plan'));
    const state = await page.evaluate(() => window.jarviss.command('state'));
    assert.equal(plan.hardware.system, process.platform === 'win32' ? 'Windows' : os.type());
    assert.ok(plan.models.length >= 2);
    assert.equal(plan.components.guides, true);
    assert.equal(plan.selected, plan.recommended || plan.models[0].id);
    assert.ok(await page.locator('#hardware-summary').innerText());
    assert.ok(plan.download_bytes > 0, 'Fresh setup must require downloads');
    assert.equal(state.ready, false, 'No model should already be running');
    assert.equal(state.voiceReady, false, 'Voice must not come from host downloads');
    assert.equal(fs.existsSync(path.join(root, '.venv')), false);
    assert.equal(fs.existsSync(path.join(root, 'runtime')), false);
    await page.waitForFunction(count => document.querySelectorAll('#setup-models input').length === count, plan.models.length, {timeout: 60000});
    assert.equal(await page.locator('#setup-models input').count(), plan.models.length);
    await page.screenshot({path: screenshot});
    console.log('PASS packaged app opens fresh setup, recommends a model and communicates with its bundled backend without Python or Node on PATH');
  } catch (error) {
    if (app) {
      for (const page of app.windows()) {
        console.error('Startup page:', page.url());
        console.error('Visible text:', await page.locator('body').innerText({timeout: 5000}).catch(() => '(unavailable)'));
        await page.screenshot({path: screenshot, timeout: 5000}).catch(() => {});
      }
    }
    throw error;
  } finally {
    if (app) await app.close();
    fs.rmSync(root, {recursive: true, force: true});
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
