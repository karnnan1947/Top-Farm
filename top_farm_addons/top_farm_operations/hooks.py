# -*- coding: utf-8 -*-


def post_init_hook(env):
    """Give every company its consumption locations, reusing any that already exist. Eggs have no company-wide
    store: each cage maps its own Egg Collection Location (Farm Infrastructure)."""
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
        if vals:
            company.write(vals)
