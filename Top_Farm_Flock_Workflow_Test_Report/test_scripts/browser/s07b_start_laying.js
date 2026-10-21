// Step 7b evidence: the Farm Manager confirms the Laying Phase; the pre-laying investment is locked.
module.exports = async (page, ui, { ids }) => {
  await ui.rec(page, 'stock.lot', ids.flock);
  await ui.click(page, 'Start Laying Phase', { wait: 1500 });
  await ui.shot(page, '0808_start_laying_confirm.png',
    'The Farm Manager clicks Start Laying Phase and confirms that the pre-laying investment will be locked. The 19 October collections of Cages A-02 to A-05 have been entered meanwhile (13-19 October: 59.99 % at the end of the day).');
  await ui.confirmDialog(page, 'Ok');
  await ui.shot(page, '0809_flock_laying.png',
    'Flock IHL-20-10-2026 in Laying: Laying Phase start date and birds at point of lay recorded, the To-Do closed, the chatter logs the transition.');
  await page.locator('.o_farm_investment').scrollIntoViewIfNeeded();
  await ui.shot(page, '0810_investment_locked.png',
    'Pre-Laying Flock Investment locked at the start of the Laying Phase: LKR 1,479,500 over the 4,882 birds at point of lay = LKR 303.05 per bird.', { keepScroll: true });
};
