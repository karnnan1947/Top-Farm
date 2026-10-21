// Step 0 evidence: Top Farm configuration, analytic plans, farm infrastructure and products.
module.exports = async (page, ui, { ids }) => {
  await ui.go(page, '/odoo/action-top_farm_core.action_top_farm_config_settings');
  await ui.shot(page, '0101_settings_lot_generation.png',
    'Top Farm settings: Approach B (automated estate flock lot allocation) dated by the Chick Arrival Date, with an automatically created Flock analytic account in the Flock Batches plan.');
  await page.getByText('Laying Phase Transition', { exact: true }).first().evaluate((e) => e.scrollIntoView({ block: 'start' }));
  await ui.settle(page, 500);
  await ui.shot(page, '0102_settings_laying_transition.png',
    'Laying Phase transition: the Farm Managers are alerted at a 50 % rolling 7-day hen-day rate from 17 weeks; daily operations: feed and medication consumption locations, egg store and graded egg products.',
    { keepScroll: true });

  await ui.doAction(page, {
    type: 'ir.actions.act_window', name: 'Analytic Accounts by Plan', res_model: 'account.analytic.account',
    views: [[false, 'list']], domain: [['plan_id', 'in', [ids.plan_flock, ids.plan_cage]]],
    context: { group_by: ['plan_id'] },
  });
  await ui.expandGroups(page);
  await ui.shot(page, '0103_analytic_plans_cages.png',
    'Analytic accounts of the Flock Batches and Farm Cages plans, grouped by plan: only Farm Cages has accounts yet, one per cage (IHL Cage A-01 to A-05, BDG Battery B-01). Flock accounts are created automatically when a flock is dispatched.');

  await ui.go(page, '/odoo/action-top_farm_core.action_top_farm_locations');
  await ui.expandGroups(page);
  await ui.shot(page, '0104_farm_infrastructure.png',
    'Permanent farm infrastructure: two estates with their estate codes, a brooding nursery each, laying sheds grouping the cages, and the cages with their cage analytic accounts. No batch locations.');
  await ui.rec(page, 'stock.location', ids.ihl);
  await ui.shot(page, '0105_farm_ihl_estate_code.png', 'Farm Facility Ihalapannawa Estate with estate code IHL (used to name its flock lots) and its egg store.');
  await ui.rec(page, 'stock.location', ids.cage_1);
  await ui.shot(page, '0106_cage_analytic_account.png', 'Cage A-01 in Laying Shed A, mapped to its permanent cage analytic account [A-01] in the Farm Cages plan.');

  const [bird] = await ui.rpc(page, 'product.product', 'read', [[ids.bird], ['product_tmpl_id']]);
  await ui.rec(page, 'product.template', bird.product_tmpl_id[0]);
  await ui.shot(page, '0107_product_layer_bird.png', 'Bird product: Is Live Farm Bird, tracked By Lots (hatchery lot, then flock lot), category Live Birds, cost LKR 150.');
  const [feed] = await ui.rpc(page, 'product.product', 'read', [[ids.feed_starter], ['product_tmpl_id']]);
  await ui.rec(page, 'product.template', feed.product_tmpl_id[0]);
  await ui.shot(page, '0108_product_starter_feed.png', 'Feed product Starter Crumbs (Weeks 0-4): Farm Input Type = Feed, category Feed, cost LKR 140 per kg.');
  const [med] = await ui.rpc(page, 'product.product', 'read', [[ids.med_marek], ['product_tmpl_id']]);
  await ui.rec(page, 'product.template', med.product_tmpl_id[0]);
  await ui.shot(page, '0109_product_vaccine.png', "Medicine product Marek's Vaccine (dose): Farm Input Type = Medication / Vaccine, cost LKR 58.");
  const [cat] = await ui.rpc(page, 'product.category', 'search', [[['name', '=', 'Live Birds']]]);
  await ui.rec(page, 'product.category', cat);
  await ui.shot(page, '0110_category_live_birds.png', 'Product category Live Birds: automated (perpetual) inventory valuation at standard price, stock account 140100 Livestock (Birds).');
};
