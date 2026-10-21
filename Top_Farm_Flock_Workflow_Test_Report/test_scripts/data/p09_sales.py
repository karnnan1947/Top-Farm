# Phase 9: sales. An egg sale order is prepared for the browser (s09_sales.js confirms it and validates the
# delivery). END-OF-CYCLE SIMULATION: the spent hens of flock IHL-20-10-2026 (normally sold after 70-75 weeks) are
# sold right after the egg sale, so the flock's lifetime P&L can be closed in this test.
flock = rec('stock.lot', 'flock')
if not IDS.get('so_eggs'):
    so = env['sale.order'].create({
        'partner_id': IDS['c_eggs'], 'client_order_ref': 'EGG-PO-7781',
        'order_line': [Command.create({'product_id': IDS[f'egg_{g}'], 'product_uom_qty': q, 'price_unit': p,
                                       'tax_ids': [Command.clear()]})
                       for g, q, p in (('large', 3000, 45.0), ('medium', 2000, 40.0), ('jumbo', 600, 50.0),
                                       ('damaged', 200, 20.0))],
    })
    save_ids(so_eggs=so)

# spent hens: every live bird of the flock, delivered from its cages under the flock lot
if not IDS.get('so_hens'):
    birds = flock.live_bird_count
    so = env['sale.order'].create({
        'partner_id': IDS['c_hens'], 'client_order_ref': 'SPENT-HEN-0021',
        'order_line': [Command.create({'product_id': IDS['bird'], 'product_uom_qty': birds, 'price_unit': 650.0,
                                       'name': f'Spent hens, flock {flock.name}', 'tax_ids': [Command.clear()]})],
    })
    so.action_confirm()
    picking = so.picking_ids
    move = picking.move_ids
    move.move_line_ids.unlink()        # deliver this flock only, cage by cage
    for i in range(1, 6):
        cage = rec('stock.location', f'cage_{i}')
        qty = cage.get_live_bird_count(flock)
        env['stock.move.line'].create({'move_id': move.id, 'picking_id': picking.id, 'product_id': IDS['bird'],
                                       'lot_id': flock.id, 'quantity': qty, 'location_id': cage.id,
                                       'location_dest_id': picking.location_dest_id.id})
    move.picked = True
    save_ids(so_hens=so, delivery_hens=picking, hens_sold=birds)
check('TC-09-01', 'spent hen delivery prepared from the 5 cages under the flock lot',
      [flock.name, flock.live_bird_count], [rec('stock.picking', 'delivery_hens').move_line_ids.lot_id.name,
                                            int(sum(rec('stock.picking', 'delivery_hens').move_line_ids.mapped('quantity')))])
env.cr.commit()
