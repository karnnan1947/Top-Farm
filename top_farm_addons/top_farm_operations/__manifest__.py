# -*- coding: utf-8 -*-
{
    'name': 'Top Farm Operations - Feed, Eggs & Proportional MO Engine',
    'version': '20.0.2.0.0',
    'category': 'Poultry Farm Operations',
    'summary': 'Brooding and cage feeding, graded egg collections, laying transition and proportional MO splitting',
    'description': """
Top Farm Daily Operations
=========================
- Daily Feed & Medication entry per flock, in a brooding nursery or a cage, expensed to the flock
  during brooding and rearing.
- Daily Graded Egg Collection (Medium, Large, Jumbo, Damage) per cage, lotted under the parent flock.
- Laying transition on the 50 % benchmark: rolling hen-day rate over a configurable window, from a
  minimum flock age; alert to the Farm Managers or automatic start of the Laying Phase.
- Proportional MO Auto-Split Engine converting staged laying feed into graded table eggs.
- Zero-loss mathematical rounding reconciliation.
- Nightly cron fallback for unharvested laying feed.
    """,
    'author': 'Top Farm ERP Team',
    'depends': [
        'top_farm_core',
        'mrp',
        'mrp_account',
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
        'views/farm_operations_menus.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
