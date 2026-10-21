// Step 6 evidence: pre-laying rearing in the cages and its analytic tagging (flock + cage on one line).
module.exports = async (page, ui, { ids }) => {
  await ui.rec(page, 'farm.feed.log', ids.fl_rear_1);
  await ui.shot(page, '0701_cage_feed_log_draft.png',
    'Rearing feed log FEED/2026/00004 in Cage A-01 of Laying Shed A: the flock IHL-20-10-2026 is filled in from the cage. Grower Mash 100 kg and Electrolyte & Vitamin Mix 1 L.');
  await ui.click(page, 'Confirm', { wait: 3000 });
  await ui.shot(page, '0702_cage_feed_log_confirmed.png',
    'Confirmed: pre-laying feed is still a direct expense of the flock (Pre-Laying, Reconciled), now also charged to the cage.');
  await ui.go(page, '/odoo/action-top_farm_operations.action_farm_feed_log');
  await ui.shot(page, '0703_feed_logs_list.png',
    'Daily feed & medication logs, newest first: one rearing log per cage of Laying Shed A (100 kg Grower Mash + 1 L vitamins each, flock IHL-20-10-2026), then the brooding logs of BDG-20-10-2026 (Baddegama) and IHL-20-10-2026 (Ihalapannawa); all Pre-Laying, Reconciled. The Total Medication footer adds doses and litres.');

  await ui.rec(page, 'farm.mortality.log', ids.mort_cage_1);
  await ui.click(page, 'Submit', { wait: 3000 });
  await ui.shot(page, '0704_cage_mortality_scrapped.png',
    'Cage mortality MORT/2026/00003: 5 birds of the flock in Cage A-01 (0.51 % of its 978 birds), scrapped at once.');
  await ui.openForm(page, '/odoo/action-analytic.account_analytic_line_action_entries', 'account.move', ids.bill_labour);
  await ui.shot(page, '0705_debeaking_labour_bill.png',
    'Debeaking & bird care labour bill (LKR 75,000 on 510500 Bird Care Labour), charged to the flock analytic account IHL-20-10-2026.');

  await ui.go(page, '/odoo/action-analytic.account_analytic_line_action_entries');
  await ui.doAction(page, {
    type: 'ir.actions.act_window', name: 'Cage Costs of Flock IHL-20-10-2026', res_model: 'account.analytic.line',
    views: [[false, 'list']], domain: [[ids.col_flock, '=', ids.flock_account], [ids.col_cage, '!=', false]],
  });
  await ui.shot(page, '0706_cage_analytic_items.png',
    'Analytic items of the rearing costs in the cages (12 lines): each line carries BOTH the flock account (Flock Batches) and the cage account (Farm Cages), so the cost is counted once and reported per flock and per cage.',
    { height: 1150 });
  await ui.doAction(page, {
    type: 'ir.actions.act_window', name: 'Flock IHL-20-10-2026 Costs by Cage', res_model: 'account.analytic.line',
    views: [[false, 'pivot']], domain: [[ids.col_flock, '=', ids.flock_account]],
    context: { pivot_row_groupby: [ids.col_cage, 'product_id'], pivot_column_groupby: [], pivot_measures: ['amount'] },
  });
  await ui.shot(page, '0707_flock_costs_by_cage_pivot.png',
    'Analytic costs of the flock so far by cage (LKR 747,200; the LKR 750,000 chick purchase is in the bird stock value, not in analytic items). "None" = brooding and flock-level costs (LKR 676,500: vaccines, electrolytes, brooding mortality, starter feed, LPG heating, debeaking labour); one row per cage for the rearing grower feed, vitamins and cage mortality (LKR 70,700).',
    { height: 1500 });

  await ui.rec(page, 'stock.lot', ids.flock);
  await page.locator('.o_farm_investment').scrollIntoViewIfNeeded();
  await ui.shot(page, '0708_rearing_investment_summary.png',
    'Pre-Laying Flock Investment during rearing: chicks, starter and grower feed, vaccines and vitamins, LPG heating and debeaking labour = LKR 1,479,500, i.e. LKR 303.05 per live bird (4,882), against the LKR 1,200-1,300 per bird benchmark. (Still dated on the test day, before the flock age is simulated.)',
    { keepScroll: true });
  await ui.go(page, '/odoo/action-top_farm_dashboard.action_farm_flock_investment_report');
  await ui.shot(page, '0709_investment_report_pivot.png',
    'Pre-Laying Flock Investment report: expenditure and cost per bird by flock and cost component. Cost / Bird is meaningful on the flock rows; in the Total row it is only shown where a single flock has that cost.');
};
