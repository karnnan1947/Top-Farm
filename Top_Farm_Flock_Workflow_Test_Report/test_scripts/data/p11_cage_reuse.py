# Phase 11: the next flock reuses the permanent cages. After the spent hens of IHL-20-10-2026 left, Cages A-01 to
# A-05 are empty (cleaning and the 2-3 week biosecurity downtime are not simulated). A second chick purchase is
# received and dispatched to Ihalapannawa Brooding-01, where it becomes a new flock with its own analytic account;
# the browser then allocates it into the same 5 cages (s11_cage_reuse.js).
first = rec('stock.lot', 'flock')
cages = [rec('stock.location', f'cage_{i}') for i in range(1, 6)]
check('TC-11-01', 'cages A-01 to A-05 empty after the spent hen sale', [0] * 5, [c.get_live_bird_count() for c in cages])
before = {}
for c in cages:
    lines = analytic_lines(c.farm_analytic_account_id)
    before[c.name] = round(sum(lines.filtered(lambda l: l[IDS['col_flock']] == first.flock_analytic_account_id).mapped('amount')), 2)
save_ids(cage_totals_first_flock=before)

if not IDS.get('po_chicks_2'):
    po = env['purchase.order'].create({
        'partner_id': IDS['v_hatchery'], 'partner_ref': 'HATCH-2026-1102',
        'order_line': [Command.create({'product_id': IDS['bird'], 'product_qty': 4000, 'price_unit': 150.0})],
    })
    po.button_confirm()
    receipt = po.picking_ids
    receipt.move_ids.move_line_ids.unlink()
    env['stock.move.line'].create({
        'move_id': receipt.move_ids.id, 'picking_id': receipt.id, 'product_id': IDS['bird'],
        'lot_name': TODAY.strftime('%d_%m_%Y') + '_B', 'quantity': 4000,
        'location_id': receipt.location_id.id, 'location_dest_id': receipt.location_dest_id.id,
    })
    receipt.move_ids.picked = True
    receipt.button_validate()
    wh = rec('stock.warehouse', 'wh')
    stock = rec('stock.location', 'stock')
    bird = rec('product.product', 'bird')
    dispatch = env['stock.picking'].create({
        'picking_type_id': wh.int_type_id.id, 'location_id': stock.id, 'location_dest_id': IDS['ihl_brood'],
        'origin': 'Chick dispatch to IHL brooding (next flock)',
        'move_ids': [Command.create({'product_id': bird.id, 'uom_id': bird.uom_id.id, 'product_uom_qty': 4000,
                                     'location_id': stock.id, 'location_dest_id': IDS['ihl_brood']})],
    })
    dispatch.action_confirm()
    dispatch.action_assign()
    dispatch.move_line_ids.unlink()
    env['stock.move.line'].create({
        'move_id': dispatch.move_ids.id, 'picking_id': dispatch.id, 'product_id': bird.id,
        'lot_id': lot(TODAY.strftime('%d_%m_%Y') + '_B', bird).id, 'quantity': 4000,
        'location_id': stock.id, 'location_dest_id': IDS['ihl_brood'],
    })
    dispatch.move_ids.picked = True
    dispatch.button_validate()
    save_ids(po_chicks_2=po, dispatch_ihl_2=dispatch, flock_2=dispatch.move_ids.farm_flock_lot_id)
second = rec('stock.lot', 'flock_2')
save_ids(flock_2_account=second.flock_analytic_account_id)
check('TC-11-02', 'the next flock gets a new flock lot (suffix: the first flock already holds this estate-date name)',
      [f'{first.name}-2', True, 'brooding', 4000],
      [second.name, second.is_flock_batch, second.flock_stage, rec('stock.location', 'ihl_brood').get_live_bird_count(second)])
check('TC-11-03', 'the next flock has its own analytic account in the Flock Batches plan', [True, 'Flock Batches'],
      [second.flock_analytic_account_id != first.flock_analytic_account_id, second.flock_analytic_account_id.plan_id.name])
check('TC-11-04', 'the spent first flock is untouched', ['spent', 0], [first.flock_stage, first.live_bird_count])
env.cr.commit()
