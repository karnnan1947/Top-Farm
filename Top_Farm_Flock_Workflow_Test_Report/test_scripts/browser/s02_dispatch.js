// Step 2 evidence: estate supply, dispatch of the chicks to the brooding nursery and creation of the flock lot.
module.exports = async (page, ui, { ids }) => {
  await ui.rec(page, 'stock.picking', ids.supply_ihl);
  await ui.shot(page, '0301_estate_supply_ready.png',
    "Estate supply transfer WH/INT/00001 (Ready) from WH/Stock to the Ihalapannawa Estate: Starter Crumbs 600 kg, Grower Mash 1,500 kg, Layer Mash 1,000 kg, Marek's 5,000 doses, Newcastle ND-IB 10,000 doses, Electrolyte & Vitamin Mix 50 L.");
  await ui.click(page, 'Validate', { wait: 2500 });
  await ui.click(page, 'Moves', { wait: 2500 });
  await ui.shot(page, '0302_estate_supply_done.png', 'Estate supply validated: its moves show the feed put away in the IHL Feed Silo and the medicine in the IHL Medicine Store.');

  await ui.rec(page, 'stock.picking', ids.dispatch_ihl);
  await ui.shot(page, '0303_dispatch_ready_flock_lot_column.png',
    'Dispatch of 5,000 chicks from WH/Stock to Ihalapannawa Brooding-01. The Flock Lot column appears for a dispatch to brooding; in Approach B it is generated on validation.');
  await ui.click(page, 'Details');
  await ui.shot(page, '0304_dispatch_hatchery_lot_reserved.png',
    'The dispatch takes the chicks out of the main warehouse under their hatchery batch number 20_10_2026.');
  await ui.closeDialog(page);
  await ui.click(page, 'Validate', { wait: 4000 });
  await ui.shot(page, '0305_dispatch_done_flock_lot.png',
    'Dispatch validated: the new flock lot IHL-20-10-2026 ([Estate Code]-[Chick Arrival Date]) is shown on the line.');

  const [flock] = await ui.rpc(page, 'stock.lot', 'search', [[['name', '=', 'IHL-20-10-2026']]]);
  await ui.rec(page, 'stock.lot', flock);
  await ui.shot(page, '0306_flock_lot_brooding.png',
    'Flock lot IHL-20-10-2026: Flock Batch in Brooding stage, Ihalapannawa Estate, chick arrival date, own Flock analytic account, 5,000 birds placed at LKR 750,000.');

  const [bird] = await ui.rpc(page, 'product.product', 'search', [[['is_farm_bird', '=', true]]]);
  await ui.doAction(page, {
    type: 'ir.actions.act_window', name: 'Bird Moves', res_model: 'stock.move.line',
    views: [[false, 'list']], domain: [['product_id', '=', bird], ['state', '=', 'done']],
    context: { create: false },
  });
  await ui.shot(page, '0307_relabelling_moves.png',
    'Moves history of the birds: receipt under 20_10_2026, dispatch to Brooding-01, then re-labelling through Flock Lot Conversion (out under 20_10_2026, back in under IHL-20-10-2026).');

  await ui.rec(page, 'stock.location', ids.ihl_brood);
  await ui.shot(page, '0308_brooding_location.png', 'Brooding-01 now holds the flock IHL-20-10-2026: 5,000 live birds.');

  await ui.doAction(page, {
    type: 'ir.actions.act_window', name: 'Analytic Accounts by Plan', res_model: 'account.analytic.account',
    views: [[false, 'list']], domain: [['plan_id', 'in', [ids.plan_flock, ids.plan_cage]]],
    context: { group_by: ['plan_id'] },
  });
  await ui.expandGroups(page);
  await ui.shot(page, '0309_analytic_flock_account_created.png',
    'The Flock Batches plan now holds the account IHL-20-10-2026, created automatically with the flock lot; cages keep their Farm Cages accounts.');
};
