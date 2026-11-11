# -*- coding: utf-8 -*-
{
    'name': 'Top Farm Operations - Feed, Eggs & Proportional MO Engine',
    'version': '20.0.2.3.0',
    'category': 'Poultry Farm Operations',
    'summary': 'Brooding and cage feeding, graded egg collections, laying transition and proportional MO splitting',
    'description': """
Top Farm Daily Operations
=========================
- Daily Feed & Medication entry per flock, in a brooding nursery or a cage, expensed to the flock
  during brooding and rearing.
- Daily Graded Egg Collection (Medium, Large, Jumbo, Damage) per cage, lotted under the parent flock and
  produced straight into the Egg Collection Location mapped on that cage (no company-wide egg store).
- Laying transition on the 50 % benchmark: rolling hen-day rate over a configurable window, from a
  minimum flock age; alert to the Farm Managers or automatic start of the Laying Phase.
- Proportional MO Auto-Split Engine converting staged laying feed into graded table eggs.
- Zero-loss mathematical rounding reconciliation.
- Nightly cron fallback for unharvested laying feed.
- Broiler batches: feed and medication of a broiler shed are capitalized into the batch (Broiler Cost Pool).
  The harvest wizard records a pickup (birds, average or weighbridge weight): a single-component MO converts
  the birds (units) into meat (kg) valued at the batch cost of the birds taken, updating stock quantity and
  inventory valuation. Sales orders are created separately from the Sales module. Batch FCR, harvested
  weight, meat sales and gross margin on the batch. A batch is harvested in Growing or Harvesting; the first
  partial harvest moves it to Harvesting, the last one closes it.
- Layer culling: the same wizard, from a layer flock or one of its cages, converts all or part of the hens
  (units) into a separate Layer Live Weight product (kg) under a CULL-[flock]-[date] lot, at the hens' stock
  value. The hens left keep laying; the flock is Spent once no hen remains.
    """,
    'author': 'Top Farm ERP Team',
    'depends': [
        'top_farm_core',
        'mrp',
        'mrp_account',
        'sale_stock',
        'mail',
    ],
    'data': [
        'security/ir.access.csv',
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        'views/farm_feed_log_views.xml',
        'views/farm_egg_collection_views.xml',
        'views/res_config_settings_views.xml',
        'views/product_template_views.xml',
        'views/stock_location_views.xml',
        'views/stock_lot_views.xml',
        'views/mrp_production_views.xml',
        'views/sale_order_views.xml',
        'wizard/farm_broiler_harvest_wizard_views.xml',
        'views/farm_operations_menus.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
