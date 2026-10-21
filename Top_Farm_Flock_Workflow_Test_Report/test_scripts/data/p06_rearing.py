# Phase 6: pre-laying rearing in the cages (weeks 5-18): grower feed and vitamins per cage, debeaking labour, cage
# mortality. The cage A-01 log and mortality are confirmed / submitted in the browser (s06_rearing.js).
op = user('operator')
flock = rec('stock.lot', 'flock')
check('TC-06-01', 'flock in Rearing / Pre-Laying after the allocation', 'rearing', flock.flock_stage)
check('TC-06-02', 'birds per cage after the allocation', [978] * 5,
      [rec('stock.location', f'cage_{i}').get_live_bird_count(flock) for i in range(1, 6)])
for i in range(1, 6):
    key = f'fl_rear_{i}'
    if IDS.get(key):
        continue
    log_rec = op['farm.feed.log'].create({
        'location_id': IDS[f'cage_{i}'],
        'line_ids': [Command.create({'product_id': IDS['feed_grower'], 'source_location_id': IDS['silo'], 'quantity': 100}),
                     Command.create({'product_id': IDS['med_vit'], 'source_location_id': IDS['med_store'], 'quantity': 1})],
    })
    if i != 1:
        log_rec.action_confirm()
    save_ids(**{key: log_rec})
check('TC-06-03', 'cage feed log of a rearing flock is pre-laying', 'pre_laying', rec('farm.feed.log', 'fl_rear_2').feeding_phase)
check('TC-06-04', 'cage feed log fills the flock of the cage', flock.name, rec('farm.feed.log', 'fl_rear_2').flock_lot_id.name)

# one analytic line per cost, with the flock AND the cage account
moves = rec('farm.feed.log', 'fl_rear_2').picking_ids.move_ids
lines = moves.analytic_account_line_ids
col_f, col_c = IDS['col_flock'], IDS['col_cage']
check('TC-06-05', 'cage A-02 costs: one analytic line per move with flock + cage accounts',
      [(flock.flock_analytic_account_id.name, 'IHL Cage A-02')] * len(moves),
      [(l[col_f].name, l[col_c].name) for l in lines])

if not IDS.get('bill_labour'):
    bill = env['account.move'].create({
        'move_type': 'in_invoice', 'partner_id': IDS['v_labour'], 'invoice_date': TODAY, 'ref': 'DEBEAK-IHL-01',
        'invoice_line_ids': [Command.create({
            'name': f'Debeaking and bird care labour, {flock.live_bird_count:,} pullets (Laying Shed A)', 'quantity': 1,
            'price_unit': 75000.0, 'account_id': IDS['acc_labour'], 'tax_ids': [Command.clear()],
            'analytic_distribution': {str(flock.flock_analytic_account_id.id): 100.0}})],
    })
    bill.action_post()
    save_ids(bill_labour=bill)

Mort = op['farm.mortality.log']
for key, cage, dead, cause in (('mort_cage_1', 'cage_1', 5, 'cannibalism'), ('mort_cage_3', 'cage_3', 3, 'sudden_death')):
    if not IDS.get(key):
        log_rec = Mort.create({'location_id': IDS[cage], 'bird_product_id': IDS['bird'], 'lot_id': flock.id,
                               'dead_bird_count': dead, 'cause_of_death': cause})
        if cage == 'cage_3':
            log_rec.action_submit()
        save_ids(**{key: log_rec})
check('TC-06-06', 'cage A-03 mortality scrapped (0.31 %)', 'done', rec('farm.mortality.log', 'mort_cage_3').state)
env.cr.commit()
