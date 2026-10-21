# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    # top_farm_core's analytic hook reads farm_collection_id.flock_lot_id / cage_location_id on raw moves
    farm_collection_id = fields.Many2one(
        'farm.egg.collection',
        string='Source Farm Egg Collection',
        readonly=True,
        index='btree_not_null',
        copy=False,
        help="Links manufacturing order back to the daily poultry egg collection."
    )
