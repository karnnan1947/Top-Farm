# Phase 7: towards point of lay. TIME SIMULATION: the test cannot wait 18 weeks, so the flock's chick arrival date is
# moved back 18 weeks (16-06-2026) and its cage allocation 14 weeks; every transaction is still posted on the test
# day. The first eggs of the pre-laying flock are harvested on 13-18 October (no staged feed: rearing feed is a
# direct expense). The 19 October collection of cage A-01 is produced in the browser (s07_point_of_lay.js).
op = user('operator')
flock = rec('stock.lot', 'flock')
if flock.farm_arrival_date == TODAY:
    flock.write({'farm_arrival_date': TODAY - timedelta(weeks=18), 'cage_allocation_date': TODAY - timedelta(weeks=14)})
check('TC-07-01', 'simulated flock age (weeks)', 18.0, flock.flock_age_weeks)
Col = op['farm.egg.collection']


def collect(cage_key, day, total, produce=True):
    existing = env['farm.egg.collection'].search([('cage_location_id', '=', IDS[cage_key]), ('date', '=', day)])
    if existing:
        return existing
    large, medium, jumbo = int(total * 0.5), int(total * 0.3), int(total * 0.1)
    col = Col.create({'cage_location_id': IDS[cage_key], 'date': day, 'qty_large': large, 'qty_medium': medium,
                      'qty_jumbo': jumbo, 'qty_damage': total - large - medium - jumbo})
    if produce:
        col.action_generate_split_manufacturing_orders()
    return col


for offset, per_cage in ((7, 300), (6, 300), (5, 300), (4, 800), (3, 800), (2, 800)):
    for i in range(1, 6):
        collect(f'cage_{i}', TODAY - timedelta(days=offset), per_cage)
rate, eggs, bird_days = flock._get_rolling_hen_day(TODAY - timedelta(days=2))
check('TC-07-02', '7-day rolling hen-day on 18 October below the 50 % benchmark', True, rate < 50, ok=rate < 50)
check('TC-07-03', 'no laying alert yet', False, flock.laying_notification_sent)
first = env['farm.egg.collection'].search([('flock_lot_id', '=', flock.id)], order='date, id', limit=1)
check('TC-07-04', 'pre-laying harvest: 4 graded MOs without feed components', [4, 0],
      [len(first.production_ids), len(first.production_ids.move_raw_ids)])
egg_lot = first.production_ids.lot_producing_ids[:1]
check('TC-07-05', 'egg lot linked to its parent flock', [flock.name, True],
      [egg_lot.farm_flock_lot_id.name, egg_lot.name.startswith(f'LOT-EGG-{flock.name}-')])
col_ui = collect('cage_1', TODAY - timedelta(days=1), 800, produce=False)
save_ids(col_point_of_lay=col_ui, rate_18oct=rate)
env.cr.commit()
