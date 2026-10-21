// Step 7 evidence: first eggs of the pre-laying flock and the 50 % hen-day alert.
module.exports = async (page, ui, { ids }) => {
  await ui.rec(page, 'stock.lot', ids.flock);
  await ui.shot(page, '0801_flock_18_weeks_rearing.png',
    "Flock IHL-20-10-2026 at 18 weeks (simulated arrival 16 June), still in Rearing / Pre-Laying. Its Rolling Hen-Day field counts the 7 days up to today, 20 October, with no harvest yet on 19-20 October; the 12-18 October rate is 48.28 %, below the 50 % benchmark. (The chatter's 'moved to Rearing / Pre-Laying at 0.0 weeks' was logged before the arrival date was moved back.)");
  await ui.go(page, '/odoo/action-top_farm_operations.action_farm_egg_collection');
  await ui.shot(page, '0802_pre_laying_egg_collections.png',
    'First egg collections of the pre-laying flock, 13-18 October (5 cages a day): about 31 % per cage on 13-15 October, then about 82 % on 16-18 October. The 19 October collection of Cage A-01 (top row) is still a draft.',
    { height: 1600 });

  await ui.rec(page, 'farm.egg.collection', ids.col_point_of_lay);
  await ui.shot(page, '0803_egg_collection_draft.png',
    'Egg collection of Cage A-01 on 19 October: 800 graded eggs (Large 400, Medium 240, Jumbo 80, Damaged 80). No staged feed: the flock is not laying yet, its feed is a direct expense.');
  await ui.click(page, 'Produce Eggs', { wait: 1500 });
  await ui.confirmDialog(page, 'Ok');
  await ui.shot(page, '0804_egg_collection_produced.png',
    'Produced: live birds snapshot 973 (Cage A-01), hen-day 82.22 %, one manufacturing order per egg grade lotted under the flock. The chatter notes that pre-laying eggs carry no feed cost.');
  await ui.click(page, 'Manufacturing', { wait: 2500 });
  await ui.shot(page, '0805_pre_laying_mos.png', 'The 4 graded manufacturing orders of the collection (Large 400, Medium 240, Jumbo 80, Damaged 80).');
  await page.locator('.o_data_row').first().click();
  await ui.settle(page, 1500);
  await ui.shot(page, '0806_pre_laying_mo_detail.png',
    'Graded egg MO of a pre-laying flock: no feed component; the eggs are produced under the egg lot LOT-EGG-IHL-20-10-2026-20261019. The MO dates show 20 October, the day the simulated collection was processed; the egg lot carries the collection date.');

  await ui.rec(page, 'stock.lot', ids.flock);
  await ui.shot(page, '0807_laying_alert.png',
    'The Cage A-01 harvest of 19 October pushed the 7-day rolling hen-day rate of 13-19 October to 50.6 % (17,300 eggs / 34,174 live bird days, the other cages counted with no eggs yet): the Farm Manager gets the alert "Ready to transition to Laying Phase" and a To-Do. (The Rolling Hen-Day field counts up to today, 20 October.)');
};
