// Step 9 evidence: egg sale (confirmed and delivered in the browser) and spent hen delivery.
module.exports = async (page, ui, { ids }) => {
  await ui.rec(page, 'sale.order', ids.so_eggs);
  await ui.click(page, 'Confirm', { wait: 3000 });
  await ui.shot(page, '1001_egg_sale_order.png',
    'Egg sale order confirmed: Large 3,000 @ 45, Medium 2,000 @ 40, Jumbo 600 @ 50, Damaged 200 @ 20 (LKR 249,000).');
  await ui.click(page, 'Delivery', { wait: 2500 });
  await ui.click(page, 'Validate', { wait: 4000 });
  await ui.shot(page, '1002_egg_delivery_done.png', 'Egg delivery validated from the Egg Cold Store.');
  const [so] = await ui.rpc(page, 'sale.order', 'read', [[ids.so_eggs], ['picking_ids']]);
  const lines = await ui.rpc(page, 'stock.move.line', 'search', [[['picking_id', 'in', so.picking_ids]]]);
  await ui.doAction(page, {
    type: 'ir.actions.act_window', name: 'Delivered Egg Lots', res_model: 'stock.move.line',
    views: [[false, 'list']], domain: [['id', 'in', lines]], context: { create: false },
  });
  await ui.shot(page, '1003_egg_delivery_lots.png',
    'Delivered egg lots: the oldest flock egg lots (LOT-EGG-IHL-20-10-2026-<date>) are taken first; each lot links back to flock IHL-20-10-2026.');
  await ui.rec(page, 'sale.order', ids.so_eggs);
  await page.locator('.o_notebook .nav-link', { hasText: 'Order Lines' }).first().click().catch(() => {});
  await ui.shot(page, '1004_egg_sale_lines_analytic.png',
    'After the delivery the sale lines carry the analytic distribution of the delivered lots: 100 % flock IHL-20-10-2026.',
    { width: 1800 });

  await ui.rec(page, 'sale.order', ids.so_hens);
  await ui.shot(page, '1005_spent_hen_sale_order.png',
    'End of cycle (simulated): the spent hens of the flock are sold, all its live birds at LKR 650.');
  await ui.rec(page, 'stock.picking', ids.delivery_hens);
  await ui.click(page, 'Details');
  await ui.shot(page, '1006_spent_hen_delivery_from_cages.png',
    'Spent hen delivery: the birds leave the 5 cages of Laying Shed A under flock lot IHL-20-10-2026.');
  await ui.closeDialog(page);
  await ui.click(page, 'Validate', { wait: 4000 });
  await ui.shot(page, '1007_spent_hen_delivery_done.png', 'Spent hen delivery validated: the cages are empty.');
};
