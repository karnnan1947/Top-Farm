# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    farm_input_type = fields.Selection([
        ('feed', 'Feed'),
        ('medication', 'Medication / Vaccine'),
    ], string='Farm Input Type', index=True,
       help="Feed is staged during the Laying Phase and consumed by the egg manufacturing orders. "
            "Medication / Vaccine is always expensed immediately. Only these products can be logged "
            "on a Daily Feed & Medication log.")
