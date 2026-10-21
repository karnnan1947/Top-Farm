// Step 3 evidence: Approach A, the clerk enters the flock lot on the dispatch line.
module.exports = async (page, ui, { ids }) => {
  await ui.rec(page, 'stock.picking', ids.dispatch_bdg);
  await ui.click(page, 'Validate', { wait: 2500 });
  await ui.shot(page, '0401_manual_mode_refused.png',
    'Approach A (manual entry): validating the dispatch to Baddegama Brooding-01 without a flock lot is refused; the message suggests the name built from the estate code and the arrival date.');
  await ui.closeDialog(page);

  const cell = page.locator('.o_field_x2many_list td[name="farm_flock_lot_id"]').first();
  await cell.click();
  const input = page.locator('.o_field_x2many_list div[name="farm_flock_lot_id"] input').first();
  await input.fill('BDG-20-10-2026');
  await page.locator('.o-autocomplete--dropdown-item', { hasText: 'Create' }).first().click();
  await ui.settle(page, 1200);
  await page.locator('.o_form_sheet .o_form_label, .o_form_sheet h1').first().click().catch(() => {});
  await ui.shot(page, '0402_manual_flock_lot_entered.png',
    'The clerk types the flock lot BDG-20-10-2026 in the Flock Lot column of the dispatch line.');
  await ui.save(page);
  await ui.click(page, 'Validate', { wait: 4000 });
  await ui.shot(page, '0403_manual_dispatch_done.png',
    "Dispatch WH/INT/00003 validated (Done): the line carries the clerk-entered flock lot BDG-20-10-2026. The 5,000 chicks were re-labelled from hatchery lot 20_10_2026 on validation, as the flock lot's chatter shows on the next figure.");

  const [flock] = await ui.rpc(page, 'stock.lot', 'search', [[['name', '=', 'BDG-20-10-2026']]]);
  await ui.rec(page, 'stock.lot', flock);
  await ui.shot(page, '0404_manual_flock_lot.png',
    'Flock lot BDG-20-10-2026 completed at validation: Brooding stage, Baddegama Estate, arrival date from the hatchery lot, own Flock analytic account.');
};
