# -*- coding: utf-8 -*-
from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    farm_feed_log_id = fields.Many2one(
        'farm.feed.log', string='Farm Feed Log', index='btree_not_null', readonly=True, copy=False)
