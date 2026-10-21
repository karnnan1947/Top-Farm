# Phase 3b: checks of the clerk-entered flock lot after the browser validated the Baddegama dispatch (Approach A).
bdg = lot('BDG-20-10-2026')
hatch = lot(IDS['hatchery_lot_name'])
check('TC-03-05', 'dispatch validated with the clerk-entered flock lot', ['done', 'BDG-20-10-2026'],
      [rec('stock.picking', 'dispatch_bdg').state, rec('stock.picking', 'dispatch_bdg').move_ids.farm_flock_lot_id.name])
check('TC-03-06', 'clerk-entered lot completed as a flock at validation',
      [True, 'brooding', 'Baddegama Estate', str(hatch.farm_arrival_date), 'Flock Batches', 5000],
      [bdg.is_flock_batch, bdg.flock_stage, bdg.farm_location_id.name, str(bdg.farm_arrival_date),
       bdg.flock_analytic_account_id.plan_id.name, bdg.initial_bird_count])
conv = env['stock.move'].search([('farm_lot_conversion', '=', True),
                                 '|', ('location_id', '=', IDS['bdg_brood']), ('location_dest_id', '=', IDS['bdg_brood'])])
check('TC-03-07', 'chicks re-labelled in Baddegama Brooding-01 from the hatchery lot to the flock lot',
      [[hatch.name], [bdg.name]], [conv.move_line_ids.filtered(lambda l: l.location_id.id == IDS['bdg_brood']).lot_id.mapped('name'),
                                    conv.move_line_ids.filtered(lambda l: l.location_dest_id.id == IDS['bdg_brood']).lot_id.mapped('name')])
check('TC-03-08', 'Baddegama brooding holds the flock lot only', [5000, 0],
      [rec('stock.location', 'bdg_brood').get_live_bird_count(bdg), rec('stock.location', 'bdg_brood').get_live_bird_count(hatch)])
env.cr.commit()
