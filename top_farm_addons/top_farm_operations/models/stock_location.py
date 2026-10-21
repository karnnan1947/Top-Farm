# -*- coding: utf-8 -*-
from odoo import fields, models


class StockLocation(models.Model):
    _inherit = 'stock.location'

    farm_egg_location_id = fields.Many2one(
        'stock.location', string='Egg Store Location',
        domain="[('usage', '=', 'internal')]",
        help="Where this farm's graded eggs are received (e.g. WH/Stock/Eggs/IHL). "
             "Empty: the company's Egg Store Location from the Top Farm settings.")
