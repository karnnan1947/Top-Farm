# -*- coding: utf-8 -*-


def post_init_hook(env):
    """Give every company its consumption locations and an egg store, reusing any that already exist."""
    Location = env['stock.location']
    for company in env['res.company'].search([]):
        vals = {}
        for field, name in (('farm_feed_consumption_location_id', 'Feed Consumption'),
                            ('farm_medication_consumption_location_id', 'Medication Consumption')):
            if not company[field]:
                location = Location.search([
                    ('usage', '=', 'inventory'), ('name', '=', name), ('company_id', 'in', [company.id, False]),
                ], limit=1) or Location.create({'name': name, 'usage': 'inventory', 'company_id': company.id})
                vals[field] = location.id
        warehouse = env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
        if not company.farm_egg_location_id and warehouse:
            # The company must be explicit: a location inherits the *current* company by default, which is
            # refused when the warehouse of another company is the parent (multi-company databases).
            eggs = Location.search([('name', '=', 'Eggs'), ('location_id', '=', warehouse.lot_stock_id.id)], limit=1) \
                or Location.create({'name': 'Eggs', 'usage': 'internal', 'location_id': warehouse.lot_stock_id.id,
                                    'company_id': company.id})
            vals['farm_egg_location_id'] = eggs.id
        if vals:
            company.write(vals)
