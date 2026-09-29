# -*- coding: utf-8 -*-
{
    'name': 'Top Farm Core - Poultry Hierarchy & Analytics',
    'version': '19.0.1.0.0',
    'category': 'Poultry Farm Operations',
    'summary': 'Physical farm hierarchy, live bird tracking, and analytic tagging for commercial poultry layers',
    'description': """
Top Farm Core Infrastructure (Odoo 19)
======================================
- 3-Tier Farm / Batch / Cage location hierarchy with automated parent batch detection.
- Flock lifecycle stage management (Pre-Laying, Laying, Spent Hen), set on the batch and followed by its cages.
- Real-time live bird tracking from stock.quant with hatchery lot preservation.
- Odoo 19 single stock.move analytic distribution hook for dual Batch/Cage P&L reporting.
    """,
    'author': 'Top Farm ERP Team',
    'depends': [
        'base',
        'stock',
        'stock_account',
        'analytic',
    ],
    'data': [
        'security/farm_security.xml',
        'security/ir.model.access.csv',
        'views/product_template_views.xml',
        'views/stock_location_views.xml',
        'views/farm_menus.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
