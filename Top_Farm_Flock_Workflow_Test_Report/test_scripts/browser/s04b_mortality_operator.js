// Step 4b evidence (Farm Operator session): the operator submits the brooding mortality logs.
module.exports = async (page, ui, { ids }) => {
  await ui.rec(page, 'farm.mortality.log', ids.mort_brood_1);
  await ui.shot(page, '0507_brooding_mortality_draft.png',
    'The Farm Operator records 50 dead chicks of flock IHL-20-10-2026 in Brooding-01 (cause Disease / Infection), in Draft.');
  await ui.click(page, 'Submit', { wait: 3000 });
  await ui.shot(page, '0508_brooding_mortality_scrapped.png',
    'Submitted by the Farm Operator: 50 of the 5,000 opening birds (1.00 %, not above the 2 % threshold) are scrapped at once.');
  await ui.rec(page, 'farm.mortality.log', ids.mort_brood_2);
  await ui.click(page, 'Submit', { wait: 3000 });
  await ui.shot(page, '0509_brooding_mortality_waiting_approval.png',
    'Another 60 chicks the same day: 110 cumulative = 2.20 % > 2 %. The operator cannot scrap them: the log waits for the Farm Manager, who gets a chatter alert and a To-Do.');
};
