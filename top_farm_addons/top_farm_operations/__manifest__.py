# -*- coding: utf-8 -*-
{
    'name': 'Top Farm Operations - Feed, Eggs & Proportional MO Engine',
    'version': '19.0.1.0.0',
    'category': 'Poultry Farm Operations',
    'summary': 'Daily feed and medication logging, graded egg collections, and proportional MO splitting',
    'description': """
Top Farm Daily Operations
=========================
- Daily Feed & Medication entry with automated Pre-Laying consumption.
- Daily Graded Egg Collection (Medium, Large, Jumbo, Damage).
- Proportional MO Auto-Split Engine converting feed into graded table eggs.
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
        'security/ir.model.access.csv',
        'security/farm_operations_security.xml',
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        'views/farm_feed_log_views.xml',
        'views/farm_egg_collection_views.xml',
        'views/res_config_settings_views.xml',
        'views/product_template_views.xml',
        'views/stock_location_views.xml',
        'views/farm_operations_menus.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
