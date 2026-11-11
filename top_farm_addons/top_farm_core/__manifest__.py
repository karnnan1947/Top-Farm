# -*- coding: utf-8 -*-
{
    'name': 'Top Farm Core - Flock Lots, Farm Infrastructure & Analytics',
    'version': '20.0.2.3.0',
    'category': 'Poultry Farm Operations',
    'summary': 'Permanent farm infrastructure, flock batches as lots, brooding-to-cage allocation and flock analytics',
    'description': """
Top Farm Core Infrastructure (Odoo 20)
======================================
- Permanent farm infrastructure: Farm Facility, Brooding Nursery, Laying Shed and Cage locations.
- Flock batches are lots (stock.lot) that move through that infrastructure: chick arrival date, age,
  lifecycle stage (Brooding, Rearing / Pre-Laying, Laying, Spent) and a dedicated Flock analytic account.
- Flock lot creation on dispatch to a brooding nursery, configurable: manual entry by the warehouse clerk
  (Approach A) or automated estate lot allocation named [Estate Code]-[Date] (Approach B), with the date
  taken from the chick arrival or the transfer validation.
- Brooding-to-Cage allocation wizard: moves a flock from its brooding nursery into the farm's cages,
  keeping the flock lot, and advances the flock to Rearing / Pre-Laying.
- Odoo 20 single stock.move analytic hook: brooding costs go 100% to the flock account; cage costs land on
  one analytic line holding both the flock and the cage account.
- The distribution is stamped on the expense line of the stock valuation entry, whose posting creates those
  analytic lines (one set, linked to the move), so the Profit and Loss by analytic account shows each flock.
  Consumption transfers made by hand carry the Flock Lot (and Farm House) of the birds they were given to.
- Broiler batches: a bird product is a Layer or a Broiler. Broiler chicks are placed in a Broiler Shed under a
  batch numbered BR-BATCH-[Year]-[NNN] and stay there until harvest (no nursery or cage), through four stages:
  Brooding, Growing (Start Growing button), Harvesting (first partial harvest) and Closed. Their feed, medication
  and dead birds go to a Broiler Cost Pool location, so the batch cost stays capitalized (current biological
  asset) and the survivors absorb the mortality. The batch form shows the pre-sale estimate: average weight,
  biomass, batch value in the shed, cost per bird and per kg, and market value at the negotiated rate.
    """,
    'author': 'Top Farm ERP Team',
    'depends': [
        'base',
        'mail',
        'stock',
        'stock_account',
        'analytic',
    ],
    'data': [
        'security/farm_security.xml',
        'security/ir.access.csv',
        'data/analytic_plan_data.xml',
        'data/ir_sequence_data.xml',
        'data/stock_location_data.xml',
        'data/mail_activity_type_data.xml',
        'views/res_config_settings_views.xml',
        'views/product_template_views.xml',
        'views/stock_location_views.xml',
        'views/stock_lot_views.xml',
        'views/stock_picking_views.xml',
        'wizard/farm_cage_allocation_views.xml',
        'views/farm_menus.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
