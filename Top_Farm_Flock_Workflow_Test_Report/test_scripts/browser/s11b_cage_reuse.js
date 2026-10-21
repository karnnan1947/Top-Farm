// Step 11b evidence: one cage account, two flocks, kept apart by the flock account of every analytic line.
module.exports = async (page, ui, { ids }) => {
  await ui.rec(page, 'stock.location', ids.cage_1);
  await ui.shot(page, '1205_cage_a01_next_flock.png',
    'Cage A-01 with the next flock: Flocks Present IHL-20-10-2026-2, same cage analytic account [A-01] IHL Cage A-01 as for the first flock.');
  await ui.go(page, '/odoo/action-analytic.account_analytic_line_action_entries');
  await ui.doAction(page, {
    type: 'ir.actions.act_window', name: 'Cage Costs by Flock', res_model: 'account.analytic.line',
    views: [[false, 'pivot']], domain: [[ids.col_cage, '!=', false]],
    context: { pivot_row_groupby: [ids.col_cage], pivot_column_groupby: [ids.col_flock], pivot_measures: ['amount'] },
  });
  await ui.shot(page, '1206_cage_by_flock_pivot.png',
    'Analytic items of the cages by flock: each cage account (rows) holds the costs and revenue of the first flock IHL-20-10-2026 and the costs of the next flock IHL-20-10-2026-2 in separate columns. One cage, two flocks, nothing mixed.',
    { width: 1800 });
  await ui.doAction(page, {
    type: 'ir.actions.act_window', name: 'Cage A-01: analytic items by flock', res_model: 'account.analytic.line',
    views: [[false, 'list']], domain: [[ids.col_cage, '=', ids.cage_1_account || false]],
    context: { group_by: [ids.col_flock] },
  });
  await ui.expandGroups(page);
  await ui.shot(page, '1207_cage_a01_items_by_flock.png',
    'Cage A-01 analytic items grouped by flock: the first flock lines (rearing, laying feed, mortality, spent hens) and the next flock lines (grower feed, vitamins, 2 dead birds), all on the cage account [A-01].',
    { height: 1500 });
  await ui.go(page, '/odoo/action-top_farm_core.action_farm_flock_lots');
  await page.locator('.o_searchview .o_facet_remove').first().click().catch(() => {});
  await ui.settle(page, 1200);
  await ui.shot(page, '1208_flock_batches_with_next_flock.png',
    'Flock Batches: IHL-20-10-2026 Spent, its successor IHL-20-10-2026-2 in Rearing in the same cages, BDG-20-10-2026 in Brooding at Baddegama.');
};
