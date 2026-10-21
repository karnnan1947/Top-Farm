# Phase 1: purchase the day-old chicks, the feed and the medicine. The receipts are prepared (quantities and the
# hatchery batch number) and left Ready: they are validated in the browser (s01_purchase.js).
HATCHERY_LOT = TODAY.strftime('%d_%m_%Y')      # batch number given by the hatchery, e.g. 20_10_2026

def purchase(vendor_key, lines, ref):
    po = env['purchase.order'].search([('partner_ref', '=', ref)], limit=1)
    if not po:
        po = env['purchase.order'].create({
            'partner_id': IDS[vendor_key], 'partner_ref': ref,
            'order_line': [Command.create({'product_id': IDS[key], 'product_qty': qty, 'price_unit': price})
                           for key, qty, price in lines],
        })
        po.button_confirm()
    return po

po_chicks = purchase('v_hatchery', [('bird', 10000, 150.0)], 'HATCH-2026-1019')
po_feed = purchase('v_feed', [('feed_starter', 1000, 140.0), ('feed_grower', 1500, 130.0),
                              ('feed_layer', 1000, 120.0)], 'FEED-2026-0412')
po_med = purchase('v_vet', [('med_marek', 10000, 58.0), ('med_nd', 10000, 12.0), ('med_vit', 50, 900.0)],
                  'VET-2026-0388')

# chick receipt: the hatchery batch number is entered on the receipt line
receipt = po_chicks.picking_ids
move = receipt.move_ids
if receipt.state != 'done':
    move.move_line_ids.unlink()
    env['stock.move.line'].create({
        'move_id': move.id, 'picking_id': receipt.id, 'product_id': move.product_id.id,
        'lot_name': HATCHERY_LOT, 'quantity': 10000,
        'location_id': receipt.location_id.id, 'location_dest_id': receipt.location_dest_id.id,
    })
    move.picked = True
for picking in (po_feed.picking_ids | po_med.picking_ids).filtered(lambda p: p.state != 'done'):
    for m in picking.move_ids:
        m.quantity = m.product_uom_qty
    picking.move_ids.picked = True

save_ids(po_chicks=po_chicks, po_feed=po_feed, po_med=po_med, receipt_chicks=receipt,
         receipt_feed=po_feed.picking_ids, receipt_med=po_med.picking_ids, hatchery_lot_name=HATCHERY_LOT)
check('TC-01-01', 'chick purchase order confirmed', 'purchase', po_chicks.state)
check('TC-01-02', 'chick PO amount (10,000 x 150)', 1500000.0, po_chicks.amount_untaxed)
check('TC-01-03', 'feed PO amount', 1000 * 140 + 1500 * 130 + 1000 * 120.0, po_feed.amount_untaxed)
check('TC-01-04', 'medicine PO amount', 10000 * 58 + 10000 * 12 + 50 * 900.0, po_med.amount_untaxed)
check('TC-01-05', 'chick receipt carries the hatchery batch number', HATCHERY_LOT,
      receipt.move_line_ids.lot_name)
env.cr.commit()
