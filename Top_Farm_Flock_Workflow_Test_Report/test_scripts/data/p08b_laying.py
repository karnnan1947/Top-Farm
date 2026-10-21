# Phase 8b: cage A-01's egg collection of 20 October, created after its feed was staged in the browser.
op = user('operator')
check('TC-08-05', 'cage A-01 laying feed staged in the browser', 'confirmed', rec('farm.feed.log', 'fl_lay_1').state)
if not IDS.get('col_laying'):
    col = op['farm.egg.collection'].create({'cage_location_id': IDS['cage_1'], 'date': TODAY, 'qty_large': 440,
                                            'qty_medium': 300, 'qty_jumbo': 100, 'qty_damage': 30})
    save_ids(col_laying=col)
check('TC-08-06', 'collection finds the staged feed of the cage and day', [IDS['fl_lay_1']],
      rec('farm.egg.collection', 'col_laying').feed_log_ids.ids)
env.cr.commit()
