// Step 10 evidence: flock-first reports, the full analytic picture, the ledger and the dashboard.
module.exports = async (page, ui, { ids }) => {
  const act = (name, model, views, domain = [], context = {}) => ui.doAction(page, {
    type: 'ir.actions.act_window', name, res_model: model, views, domain, context,
  });

  await ui.go(page, '/odoo/action-top_farm_dashboard.action_farm_profitability_report');
  await act('Flock Lifetime Profitability', 'farm.profitability.report', [[false, 'pivot']], [], {
    pivot_row_groupby: ['flock_lot_id'], pivot_column_groupby: [],
    pivot_measures: ['egg_revenue', 'bird_revenue', 'feed_cost', 'medication_cost', 'mortality_cost', 'bird_cost',
                     'other_cost', 'gross_profit', 'operating_margin_pct'],
  });
  await ui.shot(page, '1101_flock_lifetime_pnl.png',
    'Flock Lifetime Profitability: egg and spent hen revenue less feed, medication, mortality loss, bird cost of sales and other direct costs, per flock.',
    { width: 1800 });
  await act('Flock Profitability by Cage', 'farm.profitability.report', [[false, 'pivot']],
    [['flock_lot_id', '=', ids.flock]], {
      pivot_row_groupby: ['cage_location_id'], pivot_column_groupby: [],
      pivot_measures: ['revenue', 'feed_cost', 'medication_cost', 'mortality_cost', 'bird_cost', 'other_cost', 'gross_profit'],
    });
  await ui.shot(page, '1102_flock_pnl_by_cage.png',
    'The same P&L of flock IHL-20-10-2026 split by cage: egg revenue by the eggs each cage laid, spent hen revenue and cost by the cage the hens left from, feed, medication and mortality of the cage. "None" = flock-level items: the brooding costs and the LPG and labour bills.',
    { width: 1800 });
  await ui.go(page, '/odoo/action-top_farm_dashboard.action_farm_revenue_allocation');
  await ui.shot(page, '1103_flock_revenue_allocation.png',
    'Flock Revenue Allocation: egg revenue of each delivered egg lot shared between the cages by their eggs of that grade and day; spent hen revenue on the cage the hens were delivered from.');
  await ui.go(page, '/odoo/action-top_farm_dashboard.action_farm_flock_investment_report');
  await ui.shot(page, '1104_investment_final.png',
    'Pre-Laying Flock Investment (final): IHL-20-10-2026 locked at point of lay; BDG-20-10-2026 still accumulating in brooding.');
  await ui.go(page, '/odoo/action-top_farm_dashboard.action_farm_feed_report');
  await act('Feed & Medication Consumption', 'farm.feed.report', [[false, 'pivot']], [], {
    pivot_row_groupby: ['flock_lot_id', 'house_type'], pivot_column_groupby: ['input_type'], pivot_measures: ['quantity', 'cost'],
  });
  await ui.shot(page, '1105_feed_consumption_analysis.png',
    'Feed Consumption Analysis by flock and house type (brooding nursery / cage), feed vs medication.');
  await ui.go(page, '/odoo/action-top_farm_dashboard.action_farm_mortality_bi');
  await act('Mortality by Flock', 'farm.mortality.bi', [[false, 'pivot']], [], {
    pivot_row_groupby: ['flock_lot_id', 'location_id'], pivot_column_groupby: ['cause_of_death'],
    pivot_measures: ['dead_bird_count', 'mortality_pct'],
  });
  await ui.shot(page, '1106_mortality_bi.png', 'Mortality BI by flock and brooding nursery / cage, per cause of death.', { width: 1800 });

  await ui.go(page, '/odoo/action-analytic.account_analytic_line_action_entries');
  await act('Flock IHL-20-10-2026: all analytic items', 'account.analytic.line', [[false, 'pivot']],
    [[ids.col_flock, '=', ids.flock_account]], {
      pivot_row_groupby: [ids.col_cage], pivot_column_groupby: ['general_account_id'], pivot_measures: ['amount'],
    });
  await ui.shot(page, '1107_flock_analytic_lifecycle.png',
    'All analytic items of flock IHL-20-10-2026 over its lifecycle, by cage (rows; "None" = flock level) and general account (columns): sales income, the cost-of-goods-sold pairs of the invoices (Livestock / Egg Stock against 600000 Expenses, netting to zero), the bills, and the stock moves (no general account). The grand total, LKR 1,876,800, equals the gross operating profit of the flock P&L.',
    { width: 1800 });
  await act('Farm Ledger Accounts', 'account.move.line', [[false, 'list']],
    [['account_id', 'in', [ids.acc_feed_exp, ids.acc_med_exp, ids.acc_mort, ids.acc_heat, ids.acc_labour, ids.acc_egg_rev, ids.acc_bird_rev]],
     ['parent_state', '=', 'posted']], { group_by: ['account_id'] });
  await ui.shot(page, '1108_general_ledger_farm_accounts.png',
    'General ledger of the farm accounts: feed, medication, mortality, heating and labour expenses; egg and spent hen sales.');

  await ui.go(page, '/odoo/action-top_farm_dashboard.action_farm_dashboard_kpis');
  const dates = page.locator('.o_farm_dashboard input[type="date"]');
  await dates.nth(0).fill('2026-10-13');
  await dates.nth(0).dispatchEvent('change');
  await ui.settle(page, 1200);
  await dates.nth(1).fill('2026-10-20');
  await dates.nth(1).dispatchEvent('change');
  await ui.settle(page, 1200);
  await page.locator('.o_farm_dashboard h3').first().click();
  await ui.settle(page, 600);
  await ui.shot(page, '1109_dashboard_all_flocks.png',
    'Flock Performance Dashboard, 13-20 October, all active flocks: live population by stage (the spent flock is no longer counted), hen-day rate, FCR, mortality, harvest by grade. The FCR is low because the period mixes pre-laying eggs, which carry no feed, with one laying day.');
  await ui.go(page, '/odoo/action-top_farm_core.action_farm_flock_lots');
  await page.locator('.o_searchview .o_facet_remove').first().click().catch(() => {});
  await ui.settle(page, 1200);
  await ui.shot(page, '1110_flock_batches_final.png',
    'Flock Batches at the end of the test: IHL-20-10-2026 Spent / Depleted, BDG-20-10-2026 in Brooding.');
};
