# Phase 8: commercial laying (20 October). The day's Layer Mash is staged per cage; the egg collections consume it
# through the graded MOs. Cage A-01's feed log is confirmed in the browser (s08_laying.js), its collection is
# created in p08b and produced in the browser (s08b_eggs.js).
op = user('operator')
flock = rec('stock.lot', 'flock')
check('TC-08-01', 'flock in Laying', 'laying', flock.flock_stage)
for i in range(1, 6):
    key = f'fl_lay_{i}'
    if IDS.get(key):
        continue
    log_rec = op['farm.feed.log'].create({
        'location_id': IDS[f'cage_{i}'],
        'line_ids': [Command.create({'product_id': IDS['feed_layer'], 'source_location_id': IDS['silo'], 'quantity': 110})],
    })
    if i != 1:
        log_rec.action_confirm()
    save_ids(**{key: log_rec})
check('TC-08-02', 'cage feed of a laying flock is staged, not expensed', ['laying', 'confirmed', 0],
      [rec('farm.feed.log', 'fl_lay_2').feeding_phase, rec('farm.feed.log', 'fl_lay_2').state,
       len(rec('farm.feed.log', 'fl_lay_2').picking_ids)])
for i in range(2, 6):
    if not env['farm.egg.collection'].search([('cage_location_id', '=', IDS[f'cage_{i}']), ('date', '=', TODAY)]):
        op['farm.egg.collection'].create({'cage_location_id': IDS[f'cage_{i}'], 'date': TODAY, 'qty_large': 450,
                                          'qty_medium': 300, 'qty_jumbo': 100, 'qty_damage': 30,
                                          }).action_generate_split_manufacturing_orders()
col2 = env['farm.egg.collection'].search([('cage_location_id', '=', IDS['cage_2']), ('date', '=', TODAY)])
raw = col2.production_ids.move_raw_ids
check('TC-08-03', 'cage A-02 MOs consume exactly the staged 110 kg of Layer Mash', 110.0, round(sum(raw.mapped('quantity')), 3))
check('TC-08-04', 'laying feed of the MOs tagged to flock + cage on one analytic line',
      [(flock.flock_analytic_account_id.name, 'IHL Cage A-02')] * len(raw),
      [(l[IDS['col_flock']].name, l[IDS['col_cage']].name) for l in raw.analytic_account_line_ids])
env.cr.commit()
