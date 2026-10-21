// Step 8b evidence: graded egg collection consuming the staged feed, MOs, egg lots and the laying analytics.
module.exports = async (page, ui, { ids }) => {
  await ui.rec(page, 'farm.egg.collection', ids.col_laying);
  await ui.shot(page, '0903_laying_collection_draft.png',
    'Egg collection of Cage A-01 on 20 October: 870 graded eggs (Large 440, Medium 300, Jumbo 100, Damaged 30); the Staged Feed tab holds the 110 kg Layer Mash log.');
  await ui.click(page, 'Produce Eggs', { wait: 1500 });
  await ui.confirmDialog(page, 'Ok');
  await ui.shot(page, '0904_laying_collection_produced.png',
    'Produced: live birds snapshot, hen-day rate and FCR (kg feed per dozen eggs) recorded; 4 graded MOs consumed the 110 kg in proportion to the eggs.');
  await ui.click(page, 'Manufacturing', { wait: 2500 });
  await ui.shot(page, '0905_laying_mos.png', 'The 4 graded MOs of the collection.');
  await page.locator('.o_data_row').first().click();
  await ui.settle(page, 1500);
  await ui.shot(page, '0906_laying_mo_feed_component.png',
    'Large-egg MO: 55.64 kg of Layer Mash consumed as a component, in proportion to the large eggs (440 / 870 x 110 kg = 55.63 kg; the 0.01 kg rounding remainder goes to the largest grade so that the 4 MOs consume exactly 110 kg); finished eggs under lot LOT-EGG-IHL-20-10-2026-20261020.');

  const [eggLot] = await ui.rpc(page, 'stock.lot', 'search', [[['name', '=', 'LOT-EGG-IHL-20-10-2026-20261020'], ['product_id', '=', ids.egg_large]]]);
  await ui.go(page, `/odoo/action-stock.action_production_lot_form/${eggLot}`);
  await ui.shot(page, '0907_egg_lot_parent_flock.png',
    'Egg lot LOT-EGG-IHL-20-10-2026-20261020 (Large): Parent Flock IHL-20-10-2026 and Egg Production Date, used to trace sales back to the flock.');
  await ui.doAction(page, {
    type: 'ir.actions.act_window', name: 'Graded Eggs in the Egg Cold Store', res_model: 'stock.quant',
    views: [[false, 'list']], domain: [['location_id', '=', ids.egg_store], ['quantity', '>', 0]],
    context: { create: false, group_by: ['product_id'] },
  });
  await ui.expandGroups(page);
  await ui.shot(page, '0908_egg_cold_store_by_lot.png',
    'Graded eggs in the Egg Cold Store by product and daily flock egg lot (13-20 October): Damaged 2,200, Jumbo 2,550, Large 12,490, Medium 7,650 = 24,890 eggs.', { height: 1900 });

  await ui.go(page, '/odoo/action-analytic.account_analytic_line_action_entries');
  await ui.doAction(page, {
    type: 'ir.actions.act_window', name: 'Laying Feed of Flock IHL-20-10-2026', res_model: 'account.analytic.line',
    views: [[false, 'list']],
    domain: [[ids.col_flock, '=', ids.flock_account], ['product_id', '=', ids.feed_layer]],
  });
  await ui.shot(page, '0909_laying_feed_analytic.png',
    'Analytic items of the laying feed (Layer Mash, LKR 120 / kg) consumed by the 20 egg MOs of 20 October: each line carries the flock account IHL-20-10-2026 and the cage account of the producing cage; LKR 13,200 (110 kg) per cage.', { height: 1250 });
  await ui.go(page, '/odoo/action-top_farm_dashboard.action_farm_egg_report');
  await ui.shot(page, '0910_egg_production_analysis.png',
    'Egg Production Analysis by flock and cage, per grade: 24,890 eggs on 13-20 October. The Hen-Day (%) under a grade is the flock rate weighted by the share of the eggs of that grade, not a per-grade laying rate; the overall rate is 63.73 %.');
};
