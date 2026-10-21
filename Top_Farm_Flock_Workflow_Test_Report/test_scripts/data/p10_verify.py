# Phase 10: independent verification. Every expected figure is recomputed from the source documents (quantities x
# purchase prices, bird counts x standard cost) and compared with what Odoo booked: analytic items per stage and
# per cage, the Pre-Laying Flock Investment, the flock lifetime P&L, the general ledger and the stock. The tables
# are saved in results/summary.json for the report.
from collections import defaultdict

env.flush_all()
flock = rec('stock.lot', 'flock')
flock_bdg = rec('stock.lot', 'flock_bdg')
acc_flock = flock.flock_analytic_account_id
col_f, col_c = IDS['col_flock'], IDS['col_cage']
price = {k: rec('product.product', k).standard_price for k in
         ('feed_starter', 'feed_grower', 'feed_layer', 'med_marek', 'med_nd', 'med_vit', 'bird')}
names = {k: rec('product.product', k).display_name for k in price}
cages = [rec('stock.location', f'cage_{i}') for i in range(1, 6)]
S = {}

# ---------------------------------------------------------------- purchases
S['purchases'] = [{'po': po.name, 'vendor': po.partner_id.name, 'product': l.product_id.display_name,
                   'qty': l.product_qty, 'uom': l.uom_id.name, 'price': l.price_unit, 'subtotal': l.price_subtotal}
                  for po in (rec('purchase.order', 'po_chicks'), rec('purchase.order', 'po_feed'), rec('purchase.order', 'po_med'))
                  for l in po.order_line]
check('TC-10-01', 'purchase total (chicks + feed + medicine)', 1500000.0 + 455000.0 + 745000.0,
      sum(r['subtotal'] for r in S['purchases']))

# ---------------------------------------------------------------- flock lots
S['flocks'] = [{'flock': f.name, 'estate': f.farm_location_id.name, 'mode': mode, 'source': f.farm_source_lot_id.name,
                'placed': f.initial_bird_count, 'chick_cost': f.chick_cost, 'account': f.flock_analytic_account_id.display_name,
                'plan': f.flock_analytic_account_id.plan_id.name, 'stage': dict(f._fields['flock_stage'].selection)[f.flock_stage]}
               for f, mode in ((flock, 'Approach B - automated (arrival date)'), (flock_bdg, 'Approach A - manual entry'))]
conv = env['stock.move'].search([('farm_lot_conversion', '=', True)])
check('TC-10-02', 'the 4 re-labelling moves post no journal entry', 0, len(conv.account_move_id))
check('TC-10-03', 'the re-labelling leaves the bird stock value unchanged (out = in)', 0.0,
      round(sum(conv.mapped('value')), 2))

# ---------------------------------------------------------------- analytic items by stage
lines = analytic_lines(acc_flock)
move_of = {}
for m in su['stock.move'].search([('analytic_account_line_ids', 'in', lines.ids)]):
    for l in m.analytic_account_line_ids:
        move_of[l.id] = m


def stage_of(line):
    move = move_of.get(line.id)
    if line.move_line_id:      # journal items: the two vendor bills, else the sales invoices
        bill = line.move_line_id.move_id
        if bill == rec('account.move', 'bill_lpg'):
            return 'brooding'
        return 'rearing' if bill == rec('account.move', 'bill_labour') else 'sales'
    if not move:
        return 'other'
    if move.raw_material_production_id:
        return 'laying'
    house = move.farm_location_id or (move.move_line_ids.location_id[:1] if move.product_id.is_farm_bird else move.location_id)
    if move.picking_id.farm_feed_log_id.feeding_phase == 'laying':
        return 'laying'
    if move.product_id.is_farm_bird and not move.is_scrap and not move.farm_mortality_log_id:
        return 'depletion'
    return 'brooding' if house.farm_hierarchy_level == 'brooding' else 'rearing'


actual = defaultdict(float)
for l in lines:
    label = l.product_id.display_name if l.product_id else l.general_account_id.name
    actual[(stage_of(l), label, l[col_c].name or '')] += -l.amount
brood_expected = [
    (names['feed_starter'], 400, price['feed_starter']), (names['med_marek'], 5000, price['med_marek']),
    (names['med_nd'], 5000, price['med_nd']), (names['med_vit'], 10, price['med_vit']),
    (names['bird'] + ' (mortality)', 110, price['bird']),
]
S['brooding'] = []
for label, qty, unit in brood_expected:
    product = label.replace(' (mortality)', '')
    S['brooding'].append({'item': label, 'qty': qty, 'unit_cost': unit, 'expected': qty * unit,
                          'actual': actual[('brooding', product, '')], 'accounts': 'Flock only'})
S['brooding'].append({'item': 'LPG & electricity bill (brooding heat)', 'qty': 1, 'unit_cost': 170000.0,
                      'expected': 170000.0, 'actual': actual[('brooding', 'Brooding Heating (LPG / Electricity)', '')],
                      'accounts': 'Flock only'})
for row in S['brooding']:
    check('TC-10-04', f"brooding analytic cost: {row['item']}", row['expected'], round(row['actual'], 2),
          ok=close(row['expected'], row['actual']))
brood_cage_lines = [l for l in lines if stage_of(l) == 'brooding' and l[col_c]]
check('TC-10-05', 'no brooding analytic item carries a cage account', 0, len(brood_cage_lines))

S['rearing'] = []
for i, cage in enumerate(cages, start=1):
    dead = {1: 5, 3: 3}.get(i, 0)
    exp = 100 * price['feed_grower'] + 1 * price['med_vit'] + dead * price['bird']
    act = sum(v for (stage, label, cg), v in actual.items() if stage == 'rearing' and cg == f'IHL Cage A-0{i}')
    S['rearing'].append({'cage': cage.name, 'grower': 100 * price['feed_grower'], 'vitamins': price['med_vit'],
                         'mortality': dead * price['bird'], 'expected': exp, 'actual': act})
    check('TC-10-06', f'rearing analytic cost of {cage.name} (flock + cage)', exp, round(act, 2), ok=close(exp, act))
labour = actual[('rearing', 'Bird Care Labour (Debeaking)', '')]
check('TC-10-07', 'debeaking labour on the flock account (no cage)', 75000.0, labour)

S['laying'] = []
for i, cage in enumerate(cages, start=1):
    exp = 110 * price['feed_layer']
    act = actual[('laying', names['feed_layer'], f'IHL Cage A-0{i}')]
    S['laying'].append({'cage': cage.name, 'kg': 110, 'expected': exp, 'actual': act})
    check('TC-10-08', f'laying feed of the egg MOs on {cage.name} (flock + cage)', exp, round(act, 2), ok=close(exp, act))

hens = IDS['hens_sold']
dep = [(cg, v) for (stage, label, cg), v in actual.items() if stage == 'depletion']
S['depletion'] = [{'cage': cg, 'actual': v} for cg, v in sorted(dep)]
check('TC-10-09', 'spent hen cost of sales on the flock, split over the 5 cages', [5, hens * price['bird']],
      [len(dep), round(sum(v for __, v in dep), 2)], ok=len(dep) == 5 and close(sum(v for __, v in dep), hens * price['bird']))

# ---------------------------------------------------------------- pre-laying investment
inv_rows = {c: (cost, qty) for c, cost, qty in env['farm.flock.investment.report']._read_group(
    [('flock_lot_id', '=', flock.id)], ['component'], ['cost:sum', 'quantity:sum'])}
birds_pol = flock.laying_start_bird_count
inv_expected = {
    'chick': 5000 * price['bird'],
    'feed': 400 * price['feed_starter'] + 500 * price['feed_grower'],
    'medication': 5000 * price['med_marek'] + 5000 * price['med_nd'] + 15 * price['med_vit'],
    'other': 170000.0 + 75000.0,
}
labels = dict(env['farm.flock.investment.report']._fields['component'].selection)
S['investment'] = [{'component': labels[c], 'expected': e, 'actual': inv_rows.get(c, (0, 0))[0],
                    'per_bird': inv_rows.get(c, (0, 0))[0] / birds_pol if birds_pol else 0} for c, e in inv_expected.items()]
for row in S['investment']:
    check('TC-10-10', f"investment component: {row['component']}", row['expected'], round(row['actual'], 2),
          ok=close(row['expected'], row['actual']))
total_inv = sum(inv_expected.values())
cfg = env['farm.dashboard.config']._get_config()
S['investment_total'] = {'total': total_inv, 'birds': birds_pol, 'per_bird': total_inv / birds_pol,
                         'target': cfg.pre_laying_target_cost, 'target_max': cfg.pre_laying_target_cost_max,
                         'remaining': cfg.pre_laying_target_cost - total_inv / birds_pol,
                         'locked_on': str(flock.laying_start_date)}
check('TC-10-11', 'investment per bird at point of lay', round(total_inv / birds_pol, 2),
      round(flock.investment_cost_per_bird, 2), ok=close(total_inv / birds_pol, flock.investment_cost_per_bird))
check('TC-10-12', 'laying feed stays out of the locked investment', True,
      'laying' not in [r['component'] for r in S['investment']] and close(inv_rows['feed'][0], inv_expected['feed']))

# ---------------------------------------------------------------- hen-day and eggs
cols = env['farm.egg.collection'].search([('flock_lot_id', '=', flock.id), ('state', '=', 'done')], order='date')
by_day = defaultdict(lambda: [0, 0, 0.0])
for c in cols:
    by_day[c.date][0] += c.total_egg_qty
    by_day[c.date][1] += c.confirmed_live_bird_count
    by_day[c.date][2] += c.feed_consumed_qty
# The flock is depleted now, so the engine's own rolling rate (which fills a cage-day without harvest with the cage's
# current birds) cannot be replayed. Rebuild the end-of-day rate the same way from the collection snapshots: a cage-day
# without harvest counts the cage's birds of that period with no eggs.
snap = {(c.cage_location_id.id, c.date): c for c in cols}
cage_birds = {}
for c in cols:
    cage_birds.setdefault(c.cage_location_id.id, c.confirmed_live_bird_count)


def rolling_end_of_day(day):
    eggs = bird_days = 0
    for offset in range(7):
        d = day - timedelta(days=6 - offset)
        for cage_id, birds in cage_birds.items():
            c = snap.get((cage_id, d))
            eggs += c.total_egg_qty if c else 0
            bird_days += c.confirmed_live_bird_count if c else birds
    return round(eggs / bird_days * 100, 2) if bird_days else 0.0


S['hen_day'] = [{'date': str(d), 'eggs': e, 'birds': b, 'hen_day': round(e / b * 100, 2) if b else 0,
                 'feed_kg': f, 'rolling': rolling_end_of_day(d)} for d, (e, b, f) in sorted(by_day.items())]
S['rolling_at_alert'] = {'18oct_engine': IDS['rate_18oct'], '19oct_end_of_day_engine': IDS['rate_19oct']}
crossed = S['hen_day'][-3]['rolling'] < 50 <= S['hen_day'][-2]['rolling'] and IDS['rate_18oct'] < 50
check('TC-10-13', 'rolling hen-day below 50 % on 18 October, at or above 50 % on 19 October', True, crossed, ok=crossed)
grades = {'large': 'qty_large', 'medium': 'qty_medium', 'jumbo': 'qty_jumbo', 'damaged': 'qty_damage'}
S['eggs'] = []
for g, fname in grades.items():
    produced = sum(cols.mapped(fname))
    product = rec('product.product', f'egg_{g}')
    mo_qty = sum(cols.production_ids.filtered(lambda p: p.product_id == product).mapped('qty_produced'))
    sold = {'large': 3000, 'medium': 2000, 'jumbo': 600, 'damaged': 200}[g]
    on_hand = product.with_context(location=IDS['egg_store']).qty_available
    S['eggs'].append({'grade': g.title(), 'collected': produced, 'mo_produced': mo_qty, 'sold': sold, 'on_hand': on_hand})
    check('TC-10-14', f'{g} eggs: collected = produced by MOs = sold + on hand', [produced, produced],
          [mo_qty, sold + on_hand])

# ---------------------------------------------------------------- lifetime P&L
pnl = env['farm.profitability.report']._read_group([('flock_lot_id', '=', flock.id)], [], [
    'egg_revenue:sum', 'bird_revenue:sum', 'feed_cost:sum', 'medication_cost:sum', 'mortality_cost:sum',
    'bird_cost:sum', 'other_cost:sum', 'total_cost:sum', 'gross_profit:sum'])[0]
pnl_expected = {
    'Egg revenue': 3000 * 45 + 2000 * 40 + 600 * 50 + 200 * 20.0,
    'Spent hen revenue': hens * 650.0,
    'Feed cost': 400 * price['feed_starter'] + 500 * price['feed_grower'] + 550 * price['feed_layer'],
    'Medication cost': inv_expected['medication'],
    'Mortality loss': 118 * price['bird'],
    'Bird cost of sales': hens * price['bird'],
    'Other direct cost': 245000.0,
}
pnl_expected['Total direct cost'] = sum(v for k, v in pnl_expected.items() if 'revenue' not in k)
pnl_expected['Gross operating profit'] = (pnl_expected['Egg revenue'] + pnl_expected['Spent hen revenue']
                                          - pnl_expected['Total direct cost'])
S['pnl'] = [{'line': k, 'expected': v, 'actual': a} for (k, v), a in zip(pnl_expected.items(), pnl)]
for row in S['pnl']:
    check('TC-10-15', f"flock lifetime P&L: {row['line']}", row['expected'], round(row['actual'], 2),
          ok=close(row['expected'], row['actual']))

# ---------------------------------------------------------------- general ledger
def balance(key):
    lines = su['account.move.line'].search([('account_id', '=', IDS[key]), ('parent_state', '=', 'posted')])
    return round(sum(lines.mapped('balance')), 2)

gl_expected = [
    ('acc_feed_exp', 'Feed Expense (brooding + rearing, both estates)', (400 + 150) * price['feed_starter'] + 500 * price['feed_grower']),
    ('acc_med_exp', 'Vet & Medication Expense', inv_expected['medication'] + 5000 * price['med_marek']),
    ('acc_mort', 'Mortality Loss', 118 * price['bird']),
    ('acc_heat', 'Brooding Heating (LPG / Electricity)', 170000.0),
    ('acc_labour', 'Bird Care Labour (Debeaking)', 75000.0),
    ('acc_egg_rev', 'Egg Sales (credit)', -pnl_expected['Egg revenue']),
    ('acc_bird_rev', 'Spent Hen Sales (credit)', -pnl_expected['Spent hen revenue']),
]
S['gl'] = [{'account': rec('account.account', k).display_name, 'what': w, 'expected': e, 'actual': balance(k)}
           for k, w, e in gl_expected]
for row in S['gl']:
    check('TC-10-16', f"general ledger: {row['what']}", row['expected'], row['actual'], ok=close(row['expected'], row['actual']))

# ---------------------------------------------------------------- dashboard
kpi = env['farm.dashboard'].get_kpis(date_from=str(TODAY - timedelta(days=7)), date_to=str(TODAY), flock_id=flock.id)
S['dashboard'] = {k: kpi[k] for k in ('eggs', 'hen_day', 'fcr', 'feed_kg', 'dead', 'mortality', 'live_population')}
S['mortality'] = [{'log': m.name, 'location': m.location_id.name, 'dead': m.dead_bird_count,
                   'opening': m.opening_population, 'pct': m.mortality_pct,
                   'approval': 'Manager approval' if m.approved_by_id else 'Automatic', 'state': m.state}
                  for m in env['farm.mortality.log'].search([('lot_id', '=', flock.id)], order='id')]
check('TC-10-17', 'mortality logs of the flock (birds)', 118, sum(r['dead'] for r in S['mortality']))
S['shots'] = load('shots.json')
dump('summary.json', S)
failed = [c for c in CHECKS if c['status'] != 'PASS']
log(f'verification: {len([c for c in CHECKS if c["status"] == "PASS"])} PASS, {len(failed)} FAIL')
env.cr.commit()
