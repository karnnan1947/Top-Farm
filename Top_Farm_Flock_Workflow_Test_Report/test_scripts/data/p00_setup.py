# Phase 0: master data and configuration for the flock workflow test.

# --- company ---------------------------------------------------------------------------------------------
lkr = su.ref('base.LKR')
lkr.active = True
company.sudo().write({'name': 'Top Farm', 'currency_id': lkr.id})
su['product.pricelist'].search([]).write({'currency_id': lkr.id})    # created in USD at install
admin.sudo().write({'tz': 'Asia/Colombo', 'name': 'Farm Manager (Admin)'})
env['res.config.settings'].create({
    'group_stock_multi_locations': True, 'group_stock_production_lot': True,
    'group_analytic_accounting': True, 'group_uom': True,
}).execute()
check('TC-00-01', 'company currency', 'LKR', company.currency_id.name)

# --- users: the operator records the daily logs, the admin acts as Farm Manager -----------------------
operator = su['res.users'].search([('login', '=', 'operator')]) or su['res.users'].create({
    'login': 'operator', 'name': 'Farm Operator', 'password': 'operator123', 'tz': 'Asia/Colombo',
    'group_ids': [Command.set([env.ref('base.group_user').id, env.ref('top_farm_core.group_farm_user').id,
                               env.ref('top_farm_mortality.group_mortality_user').id])]})
save_ids(operator=operator)

# --- general ledger accounts -------------------------------------------------------------------------------
def account(code, name, atype):
    acc = env['account.account'].search([('code', '=', code)], limit=1)
    if acc:
        acc.write({'name': name})
        return acc
    return env['account.account'].create({'code': code, 'name': name, 'account_type': atype})

acc = {
    'feed_exp': account('510100', 'Feed Expense', 'expense'),
    'med_exp': account('510200', 'Vet & Medication Expense', 'expense'),
    'mort': account('510300', 'Mortality Loss', 'expense'),
    'heat': account('510400', 'Brooding Heating (LPG / Electricity)', 'expense'),
    'labour': account('510500', 'Bird Care Labour (Debeaking)', 'expense'),
    'bird_stock': account('140100', 'Livestock (Birds)', 'asset_current'),
    'feed_stock': account('140200', 'Feed Stock', 'asset_current'),
    'med_stock': account('140300', 'Vaccine & Medicine Stock', 'asset_current'),
    'egg_stock': account('140400', 'Egg Stock', 'asset_current'),
    'wip': account('140500', 'Egg Production WIP', 'asset_current'),
    'egg_rev': account('410100', 'Egg Sales', 'income'),
    'bird_rev': account('410200', 'Spent Hen Sales', 'income'),
}
save_ids(**{f'acc_{k}': v for k, v in acc.items()})

# --- product categories: automated (perpetual) valuation -----------------------------------------------
def categ(name, stock_acc, method, income=None):
    c = env['product.category'].search([('name', '=', name)], limit=1) or env['product.category'].create({'name': name})
    vals = {'property_valuation': 'real_time', 'property_cost_method': method,
            'property_stock_valuation_account_id': stock_acc.id}
    if income:
        vals['property_account_income_categ_id'] = income.id
    c.write(vals)
    return c

cat_bird = categ('Live Birds', acc['bird_stock'], 'standard', acc['bird_rev'])
cat_feed = categ('Feed', acc['feed_stock'], 'average')
cat_med = categ('Vaccines & Medicine', acc['med_stock'], 'average')
cat_egg = categ('Graded Eggs', acc['egg_stock'], 'average', acc['egg_rev'])

UNIT, KG, LITRE = env.ref('uom.product_uom_unit'), env.ref('uom.product_uom_kgm'), env.ref('uom.product_uom_litre')

def product(name, cat, uom, cost, price=0.0, **extra):
    t = env['product.template'].search([('name', '=', name)], limit=1)
    vals = {'name': name, 'type': 'consu', 'is_storable': True, 'categ_id': cat.id, 'uom_id': uom.id,
            'standard_price': cost, 'list_price': price, 'taxes_id': [Command.clear()],
            'supplier_taxes_id': [Command.clear()], **extra}
    if not t:
        t = env['product.template'].create(vals)
    return t.product_variant_id

bird = product('Layer Bird - Brown (Hy-Line)', cat_bird, UNIT, 150.0, 650.0, tracking='lot', is_farm_bird=True,
               description_purchase='Day-old pullet chicks')
feeds = {
    'starter': product('Starter Crumbs (Weeks 0-4)', cat_feed, KG, 140.0, farm_input_type='feed', sale_ok=False),
    'grower': product('Grower Mash (Weeks 5-18)', cat_feed, KG, 130.0, farm_input_type='feed', sale_ok=False),
    'layer': product('Layer Mash (Week 19+)', cat_feed, KG, 120.0, farm_input_type='feed', sale_ok=False),
}
meds = {
    'marek': product("Marek's Vaccine (dose)", cat_med, UNIT, 58.0, farm_input_type='medication', sale_ok=False),
    'nd': product('Newcastle ND-IB Vaccine (dose)', cat_med, UNIT, 12.0, farm_input_type='medication', sale_ok=False),
    'vit': product('Electrolyte & Vitamin Mix (L)', cat_med, LITRE, 900.0, farm_input_type='medication', sale_ok=False),
}
eggs = {g: product(f'Egg - {g.title()}', cat_egg, UNIT, 0.0, p, tracking='lot', invoice_policy='delivery',
                   purchase_ok=False)
        for g, p in (('large', 45.0), ('medium', 40.0), ('jumbo', 50.0), ('damaged', 20.0))}
save_ids(bird=bird, **{f'feed_{k}': v for k, v in feeds.items()}, **{f'med_{k}': v for k, v in meds.items()},
         **{f'egg_{k}': v for k, v in eggs.items()})
check('TC-00-02', 'bird product tracked by lots', 'lot', bird.tracking)

# --- partners ---------------------------------------------------------------------------------------------
def partner(name, **vals):
    return env['res.partner'].search([('name', '=', name)], limit=1) or env['res.partner'].create({'name': name, **vals})

save_ids(
    v_hatchery=partner('Hatchery Supplier (Test)', supplier_rank=1),
    v_feed=partner('Feed Mill Supplier (Test)', supplier_rank=1),
    v_vet=partner('Vet Pharma Supplier (Test)', supplier_rank=1),
    v_lpg=partner('LPG & Utilities Supplier (Test)', supplier_rank=1),
    v_labour=partner('Bird Care Labour Contractor (Test)', supplier_rank=1),
    c_eggs=partner('Egg Wholesale Customer (Test)', customer_rank=1),
    c_hens=partner('Spent Hen Buyer (Test)', customer_rank=1),
)

# --- farm infrastructure ----------------------------------------------------------------------------------
wh = env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
wh.name = 'Top Farm Main Warehouse'
stock = wh.lot_stock_id
plan_flock = env.ref('top_farm_core.analytic_plan_flock_batches')
plan_cage = env.ref('top_farm_core.analytic_plan_farm_cages')

def location(name, parent, **vals):
    return loc(name, parent) or env['stock.location'].create(
        {'name': name, 'location_id': parent.id, 'usage': 'internal', **vals})

def cage_account(name):
    return env['account.analytic.account'].search([('name', '=', name)], limit=1) or \
        env['account.analytic.account'].create({'name': name, 'code': name.split()[-1], 'plan_id': plan_cage.id})

egg_store = location('Egg Cold Store', stock)
ihl = location('Ihalapannawa Estate', stock, farm_hierarchy_level='farm', farm_code='IHL',
               farm_egg_location_id=egg_store.id)
bdg = location('Baddegama Estate', stock, farm_hierarchy_level='farm', farm_code='BDG',
               farm_egg_location_id=egg_store.id)
ihl_brood = location('Brooding-01', ihl, farm_hierarchy_level='brooding')
bdg_brood = location('Brooding-01', bdg, farm_hierarchy_level='brooding')
shed = location('Laying Shed A', ihl, farm_hierarchy_level='shed')
cages = [location(f'Cage A-0{i}', shed, farm_hierarchy_level='cage',
                  farm_analytic_account_id=cage_account(f'IHL Cage A-0{i}').id) for i in range(1, 6)]
bdg_shed = location('Laying Shed B', bdg, farm_hierarchy_level='shed')
bdg_cage = location('Battery Row B-01', bdg_shed, farm_hierarchy_level='cage',
                    farm_analytic_account_id=cage_account('BDG Battery B-01').id)
silo = location('Feed Silo', ihl)
med_store = location('Medicine Store', ihl)
save_ids(wh=wh, stock=stock, egg_store=egg_store, ihl=ihl, bdg=bdg, ihl_brood=ihl_brood, bdg_brood=bdg_brood,
         shed=shed, bdg_shed=bdg_shed, bdg_cage=bdg_cage, silo=silo, med_store=med_store,
         **{f'cage_{i + 1}': c for i, c in enumerate(cages)}, plan_flock=plan_flock, plan_cage=plan_cage)
check('TC-00-03', 'cages resolve their estate through the shed', 'Ihalapannawa Estate',
      cages[0].parent_farm_location_id.name)

# --- accounting of the farm virtual locations --------------------------------------------------------------
company.farm_feed_consumption_location_id.valuation_account_id = acc['feed_exp']
company.farm_medication_consumption_location_id.valuation_account_id = acc['med_exp']
su.ref('top_farm_mortality.location_bird_mortality').write(
    {'valuation_account_id': acc['mort'].id, 'company_id': company.id})
env['stock.location'].search([('usage', '=', 'production'), ('company_id', 'in', [company.id, False])],
                             limit=1).valuation_account_id = acc['wip']

# --- Top Farm settings --------------------------------------------------------------------------------
company.write({
    'farm_lot_generation_mode': 'auto', 'farm_lot_date_source': 'arrival',
    'farm_flock_auto_analytic': True, 'farm_flock_analytic_plan_id': plan_flock.id,
    'laying_transition_mode': 'manual', 'laying_min_age_weeks': 17.0,
    'laying_hen_day_threshold_pct': 50.0, 'laying_rolling_days': 7,
    'farm_egg_location_id': egg_store.id,
    'farm_egg_large_product_id': eggs['large'].id, 'farm_egg_medium_product_id': eggs['medium'].id,
    'farm_egg_jumbo_product_id': eggs['jumbo'].id, 'farm_egg_damage_product_id': eggs['damaged'].id,
})
cfg = env['farm.dashboard.config']._get_config()
cfg.write({'pre_laying_target_cost': 1200.0, 'pre_laying_target_cost_max': 1300.0,
           'target_hen_day_pct': 85.0, 'target_fcr': 1.6})
mort_cfg = env['farm.mortality.config']._get_config()
mort_cfg.write({'daily_mortality_threshold_pct': 2.0, 'threshold_rule': 'above'})
check('TC-00-04', 'flock lot generation mode', 'auto', company.farm_lot_generation_mode)
check('TC-00-05', 'laying benchmark (min age / hen-day / window)', [17.0, 50.0, 7],
      [company.laying_min_age_weeks, company.laying_hen_day_threshold_pct, company.laying_rolling_days])
env.cr.commit()
log('setup done')
