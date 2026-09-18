const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
const {_electron: electron} = require(require.resolve('playwright', {
  paths: [path.resolve(__dirname, '../electron'), path.resolve(__dirname, '../.verify')],
}));
const {expect} = require(require.resolve('playwright/test', {
  paths: [path.resolve(__dirname, '../electron'), path.resolve(__dirname, '../.verify')],
}));
(async () => {
  if (!process.argv[2]) throw new Error('Pass the built application executable.');
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'jarviss installed ü-'));
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
    await page.locator('.setup-storage summary').click();
    await expect(page.locator('#hardware-summary')).toContainText('GB memory');
    await expect(page.locator('#hardware-summary')).toContainText('free storage');
    await page.locator('.setup-storage summary').click();
    assert.ok(plan.download_bytes > 0, 'Fresh setup must require downloads');
    assert.equal(state.ready, false, 'No model should already be running');
    assert.equal(state.voiceReady, false, 'Voice must not come from host downloads');
    assert.equal(fs.existsSync(path.join(root, '.venv')), false);
    assert.equal(fs.existsSync(path.join(root, 'runtime')), false);
    await page.waitForFunction(count => document.querySelectorAll('#setup-models input').length === count, plan.models.length, {timeout: 60000});
    assert.equal(await page.locator('#setup-models input').count(), plan.models.length);
    await page.screenshot({path: screenshot});
    console.log('PASS packaged app opens fresh setup, recommends a model and communicates with its bundled backend without Python or Node on PATH');
    // Exercise the packaged reader assets and PDF support, not source-tree files.
    await page.locator('#setup-later').click();
    await page.locator('#assistant.visible').waitFor();
    await page.locator('#navigation-toggle').click();
    await page.locator('#panel-toggle').click();
    assert.equal(await page.locator('#navigation-panel').isVisible(),false);
    assert.equal(await page.locator('#voice-panel').isVisible(),false);
    await page.locator('#navigation-toggle').click();
    await page.locator('#panel-toggle').click();
    assert.equal(await page.locator('#navigation-panel').isVisible(),true);
    assert.equal(await page.locator('#voice-panel').isVisible(),true);
    assert.equal(await page.locator('.sidebar-resize').count(),2);
    console.log('PASS packaged sidebar controls collapse and restore both panels');
    await page.locator('[data-page="docs"]').click();
    assert.ok(await page.locator('#references .doc-row').count() >= 38);
    await page.locator('[data-reference="fda-food-flood"] .doc-row-main').click();
    await page.locator('#reference-reader.visible').waitFor();
    assert.equal(await page.locator('#reference-title').innerText(),'Food and water after storms');
    assert.equal(await page.locator('#reference-text > section').count(),3);
    assert.doesNotMatch(await page.locator('#reference-text').innerText(),/WATCH|Get Assistance|1-888-SAFE/);
    await page.locator('#reference-back').click();
    await page.locator('[data-reference="army-rope"] .doc-row-main').click();
    await page.locator('#reference-reader.visible').waitFor();
    await page.locator('#reference-contents').click();
    await page.locator('#reference-section-list button').last().click();
    await page.locator('.reference-selected').waitFor();
    const opened=app.waitForEvent('window');
    await page.locator('#reference-page-pdf').click();
    const viewer=await opened;
    await viewer.waitForURL(/army-rope\.pdf\?view=\d+#page=26&view=FitH/,{timeout:60000});
    const frame=viewer.frames().find(f=>f.url().startsWith('chrome-extension:'))||await viewer.waitForEvent('framenavigated',{predicate:f=>f.url().startsWith('chrome-extension:')});
    await expect(frame.getByRole('textbox',{name:'Page number',exact:true})).toHaveValue('26',{timeout:60000});
    await viewer.close();
    assert.equal(await page.evaluate(()=>typeof window.require),'undefined');
    console.log('PASS packaged offline text, reader scripts/styles, section navigation and illustrated PDF at the cited page');
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
