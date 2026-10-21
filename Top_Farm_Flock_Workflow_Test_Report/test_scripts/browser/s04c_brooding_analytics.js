// Step 4c evidence (Farm Manager session): approval of the mortality, and the brooding-stage analytic costs.
module.exports = async (page, ui, { ids }) => {
  await ui.rec(page, 'farm.mortality.log', ids.mort_brood_2);
  await ui.click(page, 'Approve Scrap', { wait: 3000 });
  await ui.shot(page, '0510_brooding_mortality_approved.png',
    'The Farm Manager approves: the 60 chicks are scrapped; Approved By and Approved Date are recorded, the To-Do is closed.');
  await ui.go(page, '/odoo/action-top_farm_mortality.action_farm_mortality_log');
  await ui.shot(page, '0511_mortality_records.png',
    'Mortality records of Brooding-01 for flock IHL-20-10-2026: MORT/2026/00001 (50 chicks, 1.00 %) and MORT/2026/00002 (60 chicks, 2.20 % cumulative), both Scrapped: 110 dead.');

  await ui.go(page, '/odoo/action-analytic.account_analytic_line_action_entries');
  const lineAction = (name, domain, views, context = {}) => ui.doAction(page, {
    type: 'ir.actions.act_window', name, res_model: 'account.analytic.line', views, domain, context,
  });
  await lineAction('Brooding Costs of Flock IHL-20-10-2026', [[ids.col_flock, '=', ids.flock_account]], [[false, 'list']]);
  await ui.shot(page, '0512_brooding_analytic_items.png',
    "Analytic items of flock IHL-20-10-2026 in the brooding stage (LKR -601,500): the transfers of FEED/2026/00001 and FEED/2026/00002 (starter feed, Marek's and Newcastle vaccines, electrolytes), the two mortality scraps (50 + 60 chicks, shown with the bird product name) and the LPG bill. Every line carries the Flock account only; the Farm Cages column is empty.");
  await lineAction('Brooding Costs by Product', [[ids.col_flock, '=', ids.flock_account]], [[false, 'pivot']],
    { pivot_row_groupby: ['product_id'], pivot_measures: ['amount', 'unit_amount'] });
  await ui.shot(page, '0513_brooding_analytic_pivot.png',
    'Brooding-stage expenses of the batch by product (negative = cost): starter feed 400 kg, vaccines, electrolytes 10 L, mortality 110 birds; the line without product is the LPG heating bill. Total LKR 601,500.');

  await ui.rec(page, 'stock.lot', ids.flock);
  await page.locator('.o_farm_investment').scrollIntoViewIfNeeded();
  await ui.shot(page, '0514_brooding_investment_summary.png',
    'Pre-Laying Flock Investment after the brooding records (still dated on the test day, age 0.0 weeks, before the arrival date is moved back): chicks LKR 750,000, starter feed LKR 56,000, vaccines and electrolytes LKR 359,000 (the quantity mixes doses and litres), LPG heating LKR 170,000 = LKR 273.01 per live bird. Brooding mortality is not added: the dead chicks are already in the chick cost.',
    { keepScroll: true });
};
