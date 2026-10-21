# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    farm_stock_move_id = fields.Many2one(
        'stock.move',
        string='Farm Stock Move',
        index='btree_not_null',
        copy=False,
        readonly=True,
        help="Valuation entry line carrying the flock analytic distribution of this stock move: its analytic "
             "items are the move's analytic items, so the Profit and Loss by analytic account shows the flock cost."
    )
