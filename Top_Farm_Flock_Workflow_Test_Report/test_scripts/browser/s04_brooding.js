// Step 4 evidence (Farm Manager session): brooding feed, vaccines and heating.
module.exports = async (page, ui, { ids }) => {
  await ui.rec(page, 'farm.feed.log', ids.fl_brood_1);
  await ui.shot(page, '0501_brooding_feed_log_draft.png',
    "Daily feed & medication log FEED/2026/00001 in Brooding-01, recorded by the Farm Operator: the flock IHL-20-10-2026 is filled in from the nursery, no cage is needed. Starter Crumbs 150 kg, Marek's vaccine 5,000 doses, Electrolyte & Vitamin Mix 5 L (the Total Medication field adds doses and litres).");
  await ui.click(page, 'Confirm', { wait: 3000 });
  await ui.shot(page, '0502_brooding_feed_log_confirmed.png',
    'Confirmed: brooding feed and medication are expensed at once (Pre-Laying, Reconciled), through two consumption transfers.');
  const [log] = await ui.rpc(page, 'farm.feed.log', 'read', [[ids.fl_brood_1], ['picking_ids']]);
  const moves = await ui.rpc(page, 'stock.move', 'search_read',
    [[['picking_id', 'in', log.picking_ids], ['product_id', '=', ids.feed_starter]]], { fields: ['picking_id', 'account_move_id'] });
  await ui.rec(page, 'stock.picking', moves[0].picking_id[0]);
  await ui.shot(page, '0503_brooding_feed_consumption_transfer.png',
    'Consumption transfer: Starter Crumbs from the IHL Feed Silo to the Feed Consumption virtual location.');
  await ui.openForm(page, '/odoo/action-analytic.account_analytic_line_action_entries', 'account.move', moves[0].account_move_id[0]);
  await ui.shot(page, '0504_brooding_feed_journal_entry.png',
    'Journal entry of the brooding feed: 510100 Feed Expense debited, 140200 Feed Stock credited, LKR 21,000 = 150 kg x 140.');
  await ui.rec(page, 'farm.feed.log', ids.fl_brood_2);
  await ui.shot(page, '0505_second_brooding_feed_log.png',
    'Second brooding log FEED/2026/00002 (confirmed by the Farm Operator): Starter Crumbs 250 kg, Newcastle ND-IB vaccine 5,000 doses, Electrolyte & Vitamin Mix 5 L.');
  await ui.openForm(page, '/odoo/action-analytic.account_analytic_line_action_entries', 'account.move', ids.bill_lpg);
  await ui.shot(page, '0506_lpg_heating_bill_analytic.png',
    'Vendor bill for LPG & electricity, 4 brooding weeks (LKR 170,000 on 510400 Brooding Heating), charged 100 % to the flock analytic account IHL-20-10-2026 (see the analytic items further on).');
};
