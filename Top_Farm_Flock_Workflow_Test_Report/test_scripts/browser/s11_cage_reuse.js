// Step 11 evidence: the next flock is placed in the same, now empty, cages.
module.exports = async (page, ui, { ids }) => {
  await ui.rec(page, 'stock.lot', ids.flock_2);
  await ui.shot(page, '1201_next_flock_lot.png',
    'The next chick purchase (4,000 birds, hatchery lot 20_10_2026_B) dispatched to Ihalapannawa Brooding-01 becomes a new flock with its own analytic account. It is named IHL-20-10-2026-2 because the first flock already holds IHL-20-10-2026 (same estate, same date in this test); in production the next flock arrives weeks later and carries its own date.');
  await ui.rec(page, 'stock.location', ids.ihl_brood);
  await ui.click(page, 'Allocate Flock to Cages', { wait: 2500 });
  await ui.shot(page, '1202_reuse_wizard_cages_free.png',
    'Allocation wizard for the next flock: the same 5 cages of Laying Shed A are listed; Birds Now 0 and no other flock in them, so they can receive the new flock. (A cage still holding another flock would be refused.)');
  await ui.click(page, 'Split Equally', { wait: 2500 });
  await ui.shot(page, '1203_reuse_split_equally.png', 'Split Equally: 800 birds of IHL-20-10-2026-2 per cage.');
  await ui.click(page, 'Allocate', { wait: 5000 });
  await ui.go(page, '/odoo/action-top_farm_core.action_top_farm_locations');
  await ui.expandGroups(page);
  await ui.shot(page, '1204_reused_cages.png',
    'The permanent cages now hold the next flock IHL-20-10-2026-2; each cage keeps its own cage analytic account ([A-01] to [A-05]).');
};
