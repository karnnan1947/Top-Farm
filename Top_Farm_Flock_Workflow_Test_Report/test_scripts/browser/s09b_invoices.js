// Step 9b evidence: invoices with the flock analytic account, depletion of the flock, empty cages.
module.exports = async (page, ui, { ids }) => {
  await ui.go(page, `/odoo/action-account.action_move_out_invoice_type/${ids.inv_eggs}`);
  await ui.shot(page, '1008_egg_invoice_analytic.png',
    'Posted egg invoice (LKR 249,000): every line carries the flock analytic account IHL-20-10-2026.');
  await ui.go(page, `/odoo/action-account.action_move_out_invoice_type/${ids.inv_hens}`);
  await ui.shot(page, '1009_spent_hen_invoice.png', 'Posted spent hen invoice, tagged to the flock account.');

  await ui.rec(page, 'stock.lot', ids.flock);
  await ui.click(page, 'Mark as Spent', { wait: 1500 });
  await ui.confirmDialog(page, 'Ok');
  await ui.shot(page, '1010_flock_spent.png',
    'The Farm Manager marks the flock Spent / Depleted: depletion date recorded, no live birds left.');
  await ui.go(page, '/odoo/action-top_farm_core.action_top_farm_locations');
  await ui.expandGroups(page);
  await ui.shot(page, '1011_cages_empty_for_next_flock.png',
    'The permanent cages of Laying Shed A are empty, ready for cleaning and the next flock; BDG-20-10-2026 is still brooding in Baddegama.');
};
