{
    'name': 'Top Farm Dashboard - Flock KPIs, Investment & Lifetime P&L',
    'version': '20.0.2.8.0',
    'category': 'Inventory/Poultry',
    'summary': 'Layer and broiler KPI dashboards, daily hen-day report, flock investment, lifetime P&L',
    'description': """
Top Farm Business Intelligence
==============================
- Layer Performance Dashboard (layer flocks only): live hens by stage, hen-day %, hen-housed %, laying feed per
  hen per day, feed per dozen eggs, mortality %, egg grading mix and daily harvest trend with the hen-day %.
- Broiler Performance Dashboard (broiler batches only): live broilers, live biomass (live birds x the batch's
  estimated average weight), batch FCR (feed kg / live weight kg), cumulative mortality over the batch, daily feed
  intake by feed product (booster, starter, finisher) in kg and g/bird/day, and a batch summary table.
- Dashboard access per user: Flock / Layer Dashboard and Broiler Dashboard checkboxes on the user (Farm Dashboards
  tab). The layer dashboard and the layer reports (egg production, pre-laying investment) need the first, the
  broiler dashboard and the Broiler Lifecycle Investment the second.
- Daily Egg Production & Hen-Day %: one row per cage and day (live birds, total eggs, hen-day %, eggs per grade,
  feed, FCR), grouped by day and flock with exact subtotals (ratio of sums); Excel through the pivot's
  standard Download xlsx.
- Pre-Laying Flock Investment Report (layer flocks): chick purchase, then one line per feed and per vaccine / medication
  product consumed (quantity, expenditure, cost per placed and per live bird) and the direct costs, accumulated
  from day 0 until the Laying Phase locks it, against the target cost per bird. Feed and medication are read from
  the consumption moves: stock received at zero cost still shows its quantity, costed at the product's current
  Cost until "Revalue Zero-Cost Consumption" (Dashboard Settings) values it and posts the missing flock expense.
- Broiler Lifecycle Investment Report (broiler batches): the same product-wise rearing cost from placement until
  the harvest (work in progress in the Broiler Cost Pool), per placed chick and per kg of live weight produced.
- Delivery-lot invoice tagging: the flock analytic account of the delivered egg lot lands on the customer
  invoice line.
- Size-weighted allocation of flock egg revenue to its cages, lot by lot.
- Flock Lifetime P&L: revenue less feed, medication, mortality loss and other direct costs, per flock, farm and cage.
- Ratio-correct mortality analysis by flock, brooding nursery / cage, month and cause.
- Broiler batches: meat sales (through the meat lot's parent batch) in the lifetime P&L and revenue allocation,
  capitalized feed in the feed analysis, broiler sheds in the house analyses.
- Layer culling: sales of the Layer Live Weight product (through the CULL lot's parent flock) are Spent Hen
  Revenue of the flock, by weight. Egg Production Analysis by Egg Collection Location (per cage / per farm store).
    """,
    'author': 'Top Farm ERP Team',
    'depends': ['top_farm_core', 'top_farm_operations', 'top_farm_mortality', 'sale_stock', 'account'],
    'data': [
        'security/ir.access.csv',
        'security/dashboard_security.xml',
        'views/res_users_views.xml',
        'views/stock_lot_views.xml',
        'views/farm_dashboard_config_views.xml',
        'views/farm_profitability_views.xml',
        'views/farm_flock_investment_views.xml',
        'views/farm_mortality_bi_views.xml',
        'views/farm_egg_report_views.xml',
        'views/farm_egg_daily_report_views.xml',
        'views/farm_egg_stock_views.xml',
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
