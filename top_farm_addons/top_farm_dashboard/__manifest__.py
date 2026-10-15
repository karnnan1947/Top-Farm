{
    'name': 'Top Farm Dashboard - Biological KPIs & Cage P&L Analytics',
    'version': '20.0.1.1.0',
    'category': 'Inventory/Poultry',
    'summary': 'Executive poultry KPIs, delivery-lot invoice tagging, size-weighted egg revenue and cage P&L',
    'description': """
Top Farm Business Intelligence
==============================
- Executive dashboard: live population, hen-day %, FCR (kg/dozen), mortality %, egg grade mix and trend.
- Delivery-lot invoice tagging: the batch analytic account of the delivered egg lot lands on the customer invoice line.
- Size-weighted allocation of batch egg revenue to cages, lot by lot.
- Cage & Batch P&L: revenue less feed, medication and mortality loss, with operating margin per group.
- Ratio-correct mortality analysis by batch, cage, month and cause.
    """,
    'author': 'Top Farm ERP Team',
    'depends': ['top_farm_core', 'top_farm_operations', 'top_farm_mortality', 'sale_stock', 'account'],
    'data': [
        'security/ir.access.csv',
        'views/stock_lot_views.xml',
        'views/farm_dashboard_config_views.xml',
        'views/farm_profitability_views.xml',
        'views/farm_mortality_bi_views.xml',
        'views/farm_egg_report_views.xml',
        'views/farm_feed_report_views.xml',
        'views/farm_dashboard_views.xml',
        'views/farm_dashboard_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'top_farm_dashboard/static/src/dashboard/*.js',
            'top_farm_dashboard/static/src/dashboard/*.xml',
            'top_farm_dashboard/static/src/dashboard/*.scss',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
