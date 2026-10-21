# Phase 3: Approach A (manual flock lot entry). The other 5,000 chicks go to Baddegama Brooding-01; the clerk must
# type the flock lot on the transfer line (s03_manual_dispatch.js). Approach B is restored in phase 4.
company.farm_lot_generation_mode = 'manual'
wh = rec('stock.warehouse', 'wh')
stock = rec('stock.location', 'stock')
bird = rec('product.product', 'bird')
if not IDS.get('dispatch_bdg'):
    picking = env['stock.picking'].create({
        'picking_type_id': wh.int_type_id.id, 'location_id': stock.id, 'location_dest_id': IDS['bdg_brood'],
        'origin': 'Chick dispatch to BDG brooding',
        'move_ids': [Command.create({'product_id': bird.id, 'uom_id': bird.uom_id.id, 'product_uom_qty': 5000,
                                     'location_id': stock.id, 'location_dest_id': IDS['bdg_brood']})],
    })
    picking.action_confirm()
    picking.action_assign()
    picking.move_ids.quantity = 5000
    picking.move_ids.picked = True
    save_ids(dispatch_bdg=picking)
check('TC-03-01', 'flock lot generation switched to manual entry', 'manual', company.farm_lot_generation_mode)
# the refusal is tested here in a rolled-back savepoint; the browser then shows it to the clerk
refused = ''
try:
    with env.cr.savepoint():
        rec('stock.picking', 'dispatch_bdg').button_validate()
except UserError as e:
    refused = str(e)
check('TC-03-02', 'dispatch to brooding without a flock lot is refused in manual mode', True,
      'Enter the Flock Lot' in refused, ok='Enter the Flock Lot' in refused)
check('TC-03-03', 'the refusal suggests the estate lot name', True, 'BDG-' in refused, ok='BDG-' in refused)
check('TC-03-04', 'the refused dispatch is still Ready (nothing moved)', 'assigned', rec('stock.picking', 'dispatch_bdg').state)
env.cr.commit()
