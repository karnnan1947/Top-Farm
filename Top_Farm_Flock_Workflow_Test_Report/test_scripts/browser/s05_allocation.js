// Step 5 evidence: end of brooding, the flock is split into the cages of the farm with the Brooding-to-Cage wizard.
module.exports = async (page, ui, { ids }) => {
  await ui.rec(page, 'stock.location', ids.ihl_brood);
  await ui.shot(page, '0601_brooding_ready_for_allocation.png',
    'Brooding-01 holds 4,890 surviving birds of flock IHL-20-10-2026 (5,000 placed - 110 dead); the Farm Manager clicks Allocate Flock to Cages. In production this happens at about week 4; in the test it is done on the test day, before the flock age is simulated.');
  await ui.click(page, 'Allocate Flock to Cages', { wait: 2500 });
  await ui.shot(page, '0602_allocation_wizard.png',
    'Brooding-to-Cage Allocation wizard: source nursery and flock lot detected, 4,890 live birds, the 5 cages of the estate listed with their current occupancy (all empty).');
  await ui.click(page, 'Split Equally', { wait: 2500 });
  await ui.shot(page, '0603_allocation_split_equally.png', 'Split Equally: 978 birds per cage (5 x 978 = 4,890), nothing left in brooding.');
  await ui.click(page, 'Allocate', { wait: 5000 });

  await ui.rec(page, 'stock.lot', ids.flock);
  await ui.shot(page, '0604_flock_rearing_stage.png',
    'The flock keeps its lot number IHL-20-10-2026 in the cages and moves to Rearing / Pre-Laying; the chatter records the allocation. (Age 0.0 weeks and allocation on 20 October: the flock age is simulated later, before the point of lay.)');
  const [picking] = await ui.rpc(page, 'stock.picking', 'search', [[['origin', '=', 'Cage allocation of IHL-20-10-2026']]]);
  await ui.rec(page, 'stock.picking', picking);
  await ui.click(page, 'Moves', { wait: 2500 });
  await ui.shot(page, '0605_allocation_transfer.png',
    'Moves of the allocation transfer: 978 birds from Brooding-01 to each of Cage A-01 to A-05, all under flock lot IHL-20-10-2026.');
  await ui.go(page, '/odoo/action-top_farm_core.action_top_farm_locations');
  await ui.expandGroups(page);
  await ui.shot(page, '0606_infrastructure_after_allocation.png',
    'Farm infrastructure after the allocation: Brooding-01 is empty and each cage of Laying Shed A holds 978 birds of IHL-20-10-2026.');
};
