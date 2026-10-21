# Phase 4: brooding (weeks 0-4) of flock IHL-20-10-2026 in Brooding-01: starter feed, vaccines and electrolytes,
# LPG heating bill, and brooding mortality. The Farm Operator records the logs; the browser confirms / submits
# the ones shown in the report (s04_brooding.js).
company.farm_lot_generation_mode = 'auto'
op = user('operator')
flock = lot('IHL-20-10-2026')
flock_bdg = lot('BDG-20-10-2026')
save_ids(flock=flock, flock_bdg=flock_bdg, flock_account=flock.flock_analytic_account_id,
         flock_bdg_account=flock_bdg.flock_analytic_account_id)
Feed = op['farm.feed.log']


def feed_log(key, location_key, lines, confirm):
    if IDS.get(key):
        return rec('farm.feed.log', key)
    log_rec = Feed.create({
        'location_id': IDS[location_key],
        'line_ids': [Command.create({'product_id': IDS[p], 'source_location_id': IDS[src], 'quantity': q})
                     for p, src, q in lines],
    })
    if confirm:
        log_rec.action_confirm()
    save_ids(**{key: log_rec})
    return log_rec


fl1 = feed_log('fl_brood_1', 'ihl_brood', [('feed_starter', 'silo', 150), ('med_marek', 'med_store', 5000),
                                           ('med_vit', 'med_store', 5)], confirm=False)
fl2 = feed_log('fl_brood_2', 'ihl_brood', [('feed_starter', 'silo', 250), ('med_nd', 'med_store', 5000),
                                           ('med_vit', 'med_store', 5)], confirm=True)
fl3 = feed_log('fl_brood_bdg', 'bdg_brood', [('feed_starter', 'stock', 150), ('med_marek', 'stock', 5000)],
               confirm=True)
check('TC-04-01', 'feed log picks the flock living in the brooding nursery', flock.name, fl1.flock_lot_id.name)
check('TC-04-02', 'brooding feed phase is pre-laying (direct expense)', 'pre_laying', fl1.feeding_phase)
check('TC-04-03', 'second brooding feed log expensed at once', 'reconciled', fl2.state)

# brooding heating: LPG bill for the 4 brooding weeks, charged 100 % to the flock account
if not IDS.get('bill_lpg'):
    bill = env['account.move'].create({
        'move_type': 'in_invoice', 'partner_id': IDS['v_lpg'], 'invoice_date': TODAY, 'ref': 'LPG-BROOD-IHL-01',
        'invoice_line_ids': [Command.create({
            'name': 'LPG gas and electricity, brooding heat 4 weeks (Brooding-01)', 'quantity': 1,
            'price_unit': 170000.0, 'account_id': IDS['acc_heat'], 'tax_ids': [Command.clear()],
            'analytic_distribution': {str(flock.flock_analytic_account_id.id): 100.0}})],
    })
    bill.action_post()
    save_ids(bill_lpg=bill)

# brooding mortality: 50 chicks (1 %) then 60 more the same day (2.2 % cumulative, above the 2 % threshold)
Mort = op['farm.mortality.log']
for key, dead, cause in (('mort_brood_1', 50, 'disease'), ('mort_brood_2', 60, 'heat_stress')):
    if not IDS.get(key):
        log_rec = Mort.create({'location_id': IDS['ihl_brood'], 'bird_product_id': IDS['bird'], 'lot_id': flock.id,
                               'dead_bird_count': dead, 'cause_of_death': cause,
                               'notes': 'Brooding week 1 losses' if dead == 50 else 'Heat spike in the brooder'})
        save_ids(**{key: log_rec})
env.cr.commit()
