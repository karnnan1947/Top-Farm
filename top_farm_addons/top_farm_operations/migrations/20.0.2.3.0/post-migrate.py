# -*- coding: utf-8 -*-
from odoo.tools.sql import column_exists


def migrate(cr, version):
    # A broiler batch that was already partly harvested is in its sales window: Harvesting, not Growing.
    cr.execute("""
        UPDATE stock_lot lot
           SET flock_stage = 'harvesting'
         WHERE lot.is_flock_batch AND lot.flock_type = 'broiler' AND lot.flock_stage = 'growing'
           AND EXISTS (SELECT 1 FROM mrp_production mo
                        WHERE mo.farm_broiler_lot_id = lot.id AND mo.state = 'done')
    """)

    # Eggs are now produced into the Egg Collection Location of each cage. So that egg collections keep working
    # right after the upgrade, a cage with no location yet gets the store its eggs went to before: the Egg Store
    # Location of its farm, else the company-wide Egg Store of the settings (both removed from the UI). Managers
    # then give each cage its own location in Farm Infrastructure.
    company_store = "NULL::integer"
    if column_exists(cr, 'res_company', 'farm_egg_location_id'):
        company_store = "company.farm_egg_location_id"
    cr.execute(f"""
        UPDATE stock_location cage
           SET farm_egg_location_id = COALESCE(farm.farm_egg_location_id, {company_store})
          FROM stock_location farm, res_company company
         WHERE cage.farm_hierarchy_level = 'cage'
           AND cage.farm_egg_location_id IS NULL
           AND farm.id = cage.parent_farm_location_id
           AND company.id = COALESCE(cage.company_id, farm.company_id)
    """)
    # the farm-level mapping is not used any more (the field is only shown on cages)
    cr.execute("""
        UPDATE stock_location SET farm_egg_location_id = NULL
         WHERE farm_egg_location_id IS NOT NULL AND COALESCE(farm_hierarchy_level, '') != 'cage'
    """)
