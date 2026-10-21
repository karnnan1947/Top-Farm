# Phase 11b: the next flock is fed in the reused cages; the analytic items of each cage now hold two flocks, kept apart
# by the flock account on every line. Saves results/reuse.json for the report.
op = user('operator')
first, second = rec('stock.lot', 'flock'), rec('stock.lot', 'flock_2')
cages = [rec('stock.location', f'cage_{i}') for i in range(1, 6)]
save_ids(cage_1_account=cages[0].farm_analytic_account_id)
check('TC-11-05', 'the next flock was allocated into the same 5 cages', [800] * 5,
      [c.get_live_bird_count(second) for c in cages])
for i, cage in enumerate(cages, start=1):
    key = f'fl_reuse_{i}'
    if IDS.get(key):
        continue
    log_rec = op['farm.feed.log'].create({
        'location_id': cage.id,
        'line_ids': [Command.create({'product_id': IDS['feed_grower'], 'source_location_id': IDS['silo'], 'quantity': 80}),
                     Command.create({'product_id': IDS['med_vit'], 'source_location_id': IDS['med_store'], 'quantity': 1})],
    })
    log_rec.action_confirm()
    save_ids(**{key: log_rec})
check('TC-11-06', 'the feed log of a reused cage picks the new flock', second.name, rec('farm.feed.log', 'fl_reuse_1').flock_lot_id.name)
if not IDS.get('mort_reuse_1'):
    m = op['farm.mortality.log'].create({'location_id': cages[0].id, 'bird_product_id': IDS['bird'], 'lot_id': second.id,
                                         'dead_bird_count': 2, 'cause_of_death': 'other'})
    m.action_submit()
    save_ids(mort_reuse_1=m)
check('TC-11-07', 'mortality of a reused cage is charged to the new flock', ['done', second.name],
      [rec('farm.mortality.log', 'mort_reuse_1').state, rec('farm.mortality.log', 'mort_reuse_1').lot_id.name])

col_f = IDS['col_flock']
price = {k: rec('product.product', k).standard_price for k in ('feed_grower', 'med_vit', 'bird')}
rows = []
for i, cage in enumerate(cages, start=1):
    lines = analytic_lines(cage.farm_analytic_account_id)
    old = round(sum(lines.filtered(lambda l: l[col_f] == first.flock_analytic_account_id).mapped('amount')), 2)
    new = round(sum(lines.filtered(lambda l: l[col_f] == second.flock_analytic_account_id).mapped('amount')), 2)
    other = lines.filtered(lambda l: l[col_f] not in (first.flock_analytic_account_id | second.flock_analytic_account_id))
    expected_new = -(80 * price['feed_grower'] + price['med_vit'] + (2 * price['bird'] if i == 1 else 0))
    rows.append({'cage': cage.name, 'cage_account': cage.farm_analytic_account_id.display_name,
                 'first_flock': old, 'first_flock_before': IDS['cage_totals_first_flock'][cage.name],
                 'second_flock': new, 'second_expected': expected_new, 'lines_without_flock': len(other)})
    check('TC-11-08', f'{cage.name}: first flock totals unchanged by the next flock', IDS['cage_totals_first_flock'][cage.name], old)
    check('TC-11-09', f'{cage.name}: next flock costs on the same cage account, under the new flock account',
          expected_new, new, ok=close(expected_new, new))
    check('TC-11-10', f'{cage.name}: every cost line names its flock', 0, len(other))
dump('reuse.json', {'first': first.name, 'second': second.name,
                    'first_account': first.flock_analytic_account_id.display_name,
                    'second_account': second.flock_analytic_account_id.display_name, 'rows': rows})
env.cr.commit()
