# Phase 7b: the other cages' harvests of 19 October, after the browser produced cage A-01 and the alert was raised.
op = user('operator')
flock = rec('stock.lot', 'flock')
day = TODAY - timedelta(days=1)
check('TC-07-06', 'laying alert raised by the 19 October harvest', True, flock.laying_notification_sent)
for i in range(2, 6):
    if not env['farm.egg.collection'].search([('cage_location_id', '=', IDS[f'cage_{i}']), ('date', '=', day)]):
        op['farm.egg.collection'].create({'cage_location_id': IDS[f'cage_{i}'], 'date': day, 'qty_large': 400,
                                          'qty_medium': 240, 'qty_jumbo': 80, 'qty_damage': 80,
                                          }).action_generate_split_manufacturing_orders()
rate, eggs, bird_days = flock._get_rolling_hen_day(day)
save_ids(rate_19oct=rate, eggs_19oct_window=eggs, bird_days_19oct_window=bird_days)
check('TC-07-07', '7-day rolling hen-day on 19 October at or above 50 %', True, rate >= 50, ok=rate >= 50)
check('TC-07-08', 'manual mode: the flock waits for the manager in Rearing', 'rearing', flock.flock_stage)
acts = flock.activity_ids.filtered(lambda a: a.activity_type_id == env.ref('top_farm_core.mail_activity_type_point_of_lay'))
check('TC-07-09', 'point-of-lay To-Do scheduled for the Farm Manager', True, bool(acts))
env.cr.commit()
