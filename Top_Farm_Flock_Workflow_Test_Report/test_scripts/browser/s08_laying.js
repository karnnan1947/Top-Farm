// Step 8 evidence: laying feed staged for the day's egg harvest.
module.exports = async (page, ui, { ids }) => {
  await ui.rec(page, 'farm.feed.log', ids.fl_lay_1);
  await ui.shot(page, '0901_laying_feed_log_draft.png',
    'Laying feed log in Cage A-01 (20 October): Layer Mash 110 kg. The flock is Laying, so the Feeding Phase is "Laying Phase (Staged for Egg Harvest)".');
  await ui.click(page, 'Confirm', { wait: 3000 });
  await ui.shot(page, '0902_laying_feed_staged.png',
    'Confirmed (Staged): no stock moves yet. The feed waits for the day\'s egg collection, which consumes it in the egg MOs.');
};
