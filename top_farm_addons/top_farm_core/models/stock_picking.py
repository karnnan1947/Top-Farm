# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    farm_to_brooding = fields.Boolean(
        string='Dispatch to Brooding', compute='_compute_farm_to_brooding',
        help="The transfer brings birds into a brooding nursery: each line can carry the flock lot.")
    farm_show_flock_lot = fields.Boolean(
        string='Show Flock Lot', compute='_compute_farm_show_flock_lot',
        help="Show the Flock Lot column on brooding dispatches and on consumption transfers (feed or medication "
             "given, scrap): the flock lot and its house carry the cost to the flock and cage analytic accounts.")

    @api.depends('location_dest_id.farm_hierarchy_level', 'move_ids.location_dest_id.farm_hierarchy_level')
    def _compute_farm_to_brooding(self):
        for picking in self:
            picking.farm_to_brooding = 'brooding' in (
                picking.location_dest_id | picking.move_ids.location_dest_id).mapped('farm_hierarchy_level')

    @api.depends('farm_to_brooding', 'location_dest_id.usage', 'move_ids.location_dest_id.usage')
    def _compute_farm_show_flock_lot(self):
        # A consumption transfer leaves stock for an inventory loss location (Feed / Medication Consumption,
        # scrap): only such a move is a cost, which the flock analytic hook tags.
        for picking in self:
            picking.farm_show_flock_lot = picking.farm_to_brooding or 'inventory' in (
                picking.location_dest_id | picking.move_ids.location_dest_id).mapped('usage')
