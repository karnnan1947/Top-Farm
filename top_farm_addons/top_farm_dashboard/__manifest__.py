{
    'name': 'Top Farm Dashboard - Flock KPIs, Investment & Lifetime P&L',
    'version': '20.0.2.1.0',
    'category': 'Inventory/Poultry',
    'summary': 'Executive flock KPIs, pre-laying flock investment, delivery-lot invoice tagging and flock lifetime P&L',
    'description': """
Top Farm Business Intelligence
==============================
- Executive dashboard: live population by flock stage, hen-day %, FCR (kg/dozen), mortality %, egg grade mix
  and trend, filtered by flock.
- Pre-Laying Flock Investment Report: chick purchase, feed, vaccines and direct costs accumulated per bird
  from day 0 until the Laying Phase locks it, against the target cost per bird.
- Delivery-lot invoice tagging: the flock analytic account of the delivered egg lot lands on the customer
  invoice line.
- Size-weighted allocation of flock egg revenue to its cages, lot by lot.
- Flock Lifetime P&L: revenue less feed, medication, mortality loss and other direct costs, per flock, farm and cage.
- Ratio-correct mortality analysis by flock, brooding nursery / cage, month and cause.
    """,
    'author': 'Top Farm ERP Team',
    'depends': ['top_farm_core', 'top_farm_operations', 'top_farm_mortality', 'sale_stock', 'account'],
    'data': [
        'security/ir.access.csv',
        'views/stock_lot_views.xml',
        'views/farm_dashboard_config_views.xml',
        'views/farm_profitability_views.xml',
        'views/farm_flock_investment_views.xml',
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
