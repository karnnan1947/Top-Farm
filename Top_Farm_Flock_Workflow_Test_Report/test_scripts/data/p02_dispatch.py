# Phase 2: supply the estate stores (feed silo, medicine store) and prepare the dispatch of 5,000 chicks from the
# main warehouse to Ihalapannawa Brooding-01 (Approach B: automated flock lot from the chick arrival date).
# Both transfers are left Ready and validated in the browser (s02_dispatch.js).
company.write({'farm_lot_generation_mode': 'auto', 'farm_lot_date_source': 'arrival'})
wh = rec('stock.warehouse', 'wh')
stock = rec('stock.location', 'stock')


def transfer(key, dest_key, lines, origin):
    if IDS.get(key):
        return rec('stock.picking', key)
    picking = env['stock.picking'].create({
        'picking_type_id': wh.int_type_id.id, 'location_id': stock.id, 'location_dest_id': IDS[dest_key],
        'origin': origin,
        'move_ids': [Command.create({
            'product_id': IDS[product_key], 'uom_id': rec('product.product', product_key).uom_id.id,
            'product_uom_qty': qty, 'location_id': stock.id, 'location_dest_id': IDS[move_dest],
        }) for product_key, qty, move_dest in lines],
    })
    picking.action_confirm()
    picking.action_assign()
    for move in picking.move_ids:
        move.quantity = move.product_uom_qty
    picking.move_ids.picked = True
    save_ids(**{key: picking})
    return picking


supply = transfer('supply_ihl', 'ihl', [
    ('feed_starter', 600, 'silo'), ('feed_grower', 1500, 'silo'), ('feed_layer', 1000, 'silo'),
    ('med_marek', 5000, 'med_store'), ('med_nd', 10000, 'med_store'), ('med_vit', 50, 'med_store'),
], 'Estate supply IHL')
dispatch = transfer('dispatch_ihl', 'ihl_brood', [('bird', 5000, 'ihl_brood')], 'Chick dispatch to IHL brooding')
hatch = lot(IDS['hatchery_lot_name'], rec('product.product', 'bird'))
save_ids(hatchery_lot=hatch, col_flock=plan_col(rec('account.analytic.plan', 'plan_flock')),
         col_cage=plan_col(rec('account.analytic.plan', 'plan_cage')))
check('TC-02-01', 'dispatch reserves the hatchery lot', IDS['hatchery_lot_name'], dispatch.move_line_ids.lot_id.name)
check('TC-02-02', 'dispatch destination is a brooding nursery', 'brooding',
      dispatch.location_dest_id.farm_hierarchy_level)
check('TC-02-03', 'transfer flagged as a dispatch to brooding (Flock Lot column shown)', True, dispatch.farm_to_brooding)
env.cr.commit()
