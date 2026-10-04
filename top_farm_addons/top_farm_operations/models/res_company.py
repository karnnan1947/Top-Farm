# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    farm_feed_consumption_location_id = fields.Many2one(
        'stock.location', string='Feed Consumption Location',
        domain="[('usage', '=', 'inventory')]",
        help="Virtual location that receives expensed feed (pre-laying feed and unharvested laying feed). "
             "Give it a valuation account (e.g. Feed Expense) to post the cost to the ledger.")
    farm_medication_consumption_location_id = fields.Many2one(
        'stock.location', string='Medication Consumption Location',
        domain="[('usage', '=', 'inventory')]",
        help="Virtual location that receives administered medication and vaccines.")
    farm_egg_location_id = fields.Many2one(
        'stock.location', string='Egg Store Location',
        domain="[('usage', '=', 'internal')]",
        help="Default cold-room location for graded eggs. A batch can override it.")
    farm_egg_medium_product_id = fields.Many2one('product.product', string='Medium Egg Product')
    farm_egg_large_product_id = fields.Many2one('product.product', string='Large Egg Product')
    farm_egg_jumbo_product_id = fields.Many2one('product.product', string='Jumbo Egg Product')
    farm_egg_damage_product_id = fields.Many2one('product.product', string='Damaged / Cracked Egg Product')
