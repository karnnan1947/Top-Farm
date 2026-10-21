{
    'name': 'Top Farm Mortality - Poultry Loss Tracking & Approvals',
    'version': '20.0.2.0.0',
    'category': 'Inventory/Poultry',
    'summary': 'Daily mortality logging with live-stock guard, cumulative daily approval threshold, and automated scrap',
    'description': """
Top Farm Mortality
==================
Built on top_farm_core (farm infrastructure, flock lots, Farm Bird flag, live bird count, Flock/Cage analytic tagging).
- Daily mortality log per flock, in a brooding nursery (weeks 0-4) or a cage, with cause of death.
- Hard stock guard: dead birds cannot exceed live birds (per lot, pending-aware).
- Anti-bypass cumulative daily threshold on the opening population; manager approval above it.
- Automated scrap move (is_scrap) charged to the Flock analytic account (and the Cage account in a cage).
- Manager reject (mandatory reason) and reverse (mandatory reason).
    """,
    'author': 'Top Farm ERP Team',
    'depends': ['top_farm_core'],
    'data': [
        'security/security.xml',
        'security/ir.access.csv',
        'data/stock_location_data.xml',
        'data/ir_sequence_data.xml',
        'views/mortality_config_views.xml',
        'views/farm_mortality_log_views.xml',
        'wizard/mortality_action_wizard_views.xml',
        'views/mortality_menus.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
