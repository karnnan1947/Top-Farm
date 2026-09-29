# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_farm_bird = fields.Boolean(
        string='Is Live Farm Bird',
        default=False,
        index=True,
        help="Check this box if the product represents live poultry layers (Day-Old Chicks or Adult Birds)."
    )
