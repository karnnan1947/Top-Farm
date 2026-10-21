// usage: node run_steps.js <steps.js> [user] [password]
// A steps file exports: async (page, ui, ctx) => {...}
const ui = require('./ui');
const path = require('path');

(async () => {
  const file = path.resolve(process.argv[2]);
  const user = process.argv[3] || 'admin';
  const pwd = process.argv[4] || 'admin';
  const { browser, context, page } = await ui.start(user, pwd);
  try {
    await require(file)(page, ui, { browser, context, user, ids: ui.IDS() });
  } catch (e) {
    console.log('STEP FAILED:', e.message.split('\n')[0]);
    await page.screenshot({ path: path.join(ui.RESULTS, 'failure.png') });
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
