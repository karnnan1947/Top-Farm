# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    farm_broiler_lot_id = fields.Many2one(
        'stock.lot', string='Broiler Batch',
        domain="[('flock_type', '=', 'broiler')]",
        help="Optional link to the broiler batch for batch sales revenue and margin reporting."
    )
