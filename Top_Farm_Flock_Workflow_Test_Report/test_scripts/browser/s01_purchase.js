// Step 1 evidence: purchase of the day-old chicks with the hatchery batch number, feed and medicine receipts.
module.exports = async (page, ui, { ids }) => {
  await ui.rec(page, 'purchase.order', ids.po_chicks);
  await ui.shot(page, '0201_po_chicks.png', 'Purchase order P00001 for the day-old chicks: 10,000 pullets at LKR 150 from the hatchery, confirmed.');

  await ui.rec(page, 'stock.picking', ids.receipt_chicks);
  await ui.shot(page, '0202_receipt_chicks_ready.png', 'Chick receipt into the main warehouse (WH/Stock), Ready.');
  await ui.click(page, 'Details');
  await ui.shot(page, '0203_receipt_hatchery_batch_number.png',
    'Receipt line detail: the hatchery batch number 20_10_2026 is entered as the lot of the 10,000 chicks.');
  await ui.closeDialog(page);
  await ui.click(page, 'Validate', { wait: 2500 });
  await ui.shot(page, '0204_receipt_chicks_done.png', 'Chick receipt WH/IN/00001 validated (Done): 10,000 birds received into the main warehouse WH/Stock (their lot 20_10_2026 is shown on the previous and the next figure).');

  const [lot] = await ui.rpc(page, 'stock.lot', 'search', [[['name', '=', ids.hatchery_lot_name]]]);
  await ui.go(page, `/odoo/action-stock.action_production_lot_form/${lot}`);
  await ui.shot(page, '0205_hatchery_lot.png',
    'Hatchery lot 20_10_2026: Chick Arrival Date stamped by the receipt; it is not a flock (Flock Batch unticked).');

  for (const [key, name, caption] of [
    ['po_feed', '0206_po_feed.png', 'Feed purchase: Starter Crumbs 1,000 kg, Grower Mash 1,500 kg, Layer Mash 1,000 kg.'],
    ['po_med', '0208_po_medicine.png', "Medicine purchase: Marek's 10,000 doses, Newcastle ND-IB 10,000 doses, Electrolyte & Vitamin Mix 50 L."],
  ]) {
    await ui.rec(page, 'purchase.order', ids[key]);
    await ui.shot(page, name, caption);
  }
  for (const [key, name, caption] of [
    ['receipt_feed', '0207_receipt_feed_done.png', 'Feed receipt validated into WH/Stock.'],
    ['receipt_med', '0209_receipt_medicine_done.png', 'Medicine receipt validated into WH/Stock.'],
  ]) {
    await ui.rec(page, 'stock.picking', ids[key]);
    await ui.click(page, 'Validate', { wait: 2500 });
    await ui.shot(page, name, caption);
  }

  await ui.doAction(page, {
    type: 'ir.actions.act_window', name: 'Main Warehouse Stock', res_model: 'stock.quant',
    views: [[false, 'list']], domain: [['location_id', '=', ids.stock], ['quantity', '>', 0]],
    context: { create: false },
  });
  await ui.shot(page, '0210_main_warehouse_stock.png',
    'Main warehouse stock after the purchases: 10,000 chicks under hatchery lot 20_10_2026, the feed (kg) and the medicine (doses, litres). The footer total adds different units and has no meaning.');
};
