const assert = require('node:assert/strict');

// Check rendered pixels in both the source app and the installed release.
module.exports = async function checkOrbAnimation(page) {
  const pixels = () => page.locator('#orb canvas').evaluate(canvas => canvas.toDataURL());
  const settles = () => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  async function moves() {
    const before = await pixels();
    await page.waitForFunction(before => document.querySelector('#orb canvas').toDataURL() !== before, before, {timeout: 5000});
  }
  async function staysStill() {
    await settles();
    const before = await pixels();
    await page.waitForTimeout(250);
    assert.equal(await pixels(), before, 'Hidden or reduced-motion orb must stay still');
  }
  await page.emulateMedia({reducedMotion: 'no-preference'});
  for (const state of ['idle', 'listening', 'thinking', 'speaking']) {
    await page.evaluate(state => {
      window.jarvisState('status', state === 'thinking' ? 'Thinking' : 'Ready');
      window.jarvisState('voice', state === 'listening' ? 'Listening' : state === 'speaking' ? 'Speaking' : 'Voice off');
    }, state);
    assert.equal(await page.locator('#orb').getAttribute('data-state'), state);
    await moves();
  }
  await page.evaluate(() => window.jarvisState('voice', 'Voice off'));
  await moves(); // Returning from an active state must keep the gentle idle motion.
  await page.locator('#panel-toggle').click();
  assert.equal(await page.locator('#voice-panel').isVisible(), false);
  await staysStill();
  await page.locator('#panel-toggle').click();
  await moves();
  await page.emulateMedia({reducedMotion: 'reduce'});
  await staysStill();
  await page.evaluate(() => window.jarvisState('voice', 'Listening'));
  await staysStill();
  await page.evaluate(() => window.jarvisState('voice', 'Voice off'));
  await page.emulateMedia({reducedMotion: 'no-preference'});
  await moves();
};
