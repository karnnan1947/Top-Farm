# -*- coding: utf-8 -*-
from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    farm_cage_location_id = fields.Many2one(
        'stock.location',
        string='Farm Cage Location',
        index='btree_not_null',
        copy=False,
        domain="[('farm_hierarchy_level', '=', 'cage')]",
        help="Explicit cage reference set by farm operations (feed log, cron fallback, scrap) for analytic tagging."
    )

    def _prepare_merge_moves_distinct_fields(self):
        # Feed for two cages in one picking must stay two moves, or confirming the picking merges
        # them and the whole quantity is charged to the first cage.
        return super()._prepare_merge_moves_distinct_fields() + ['farm_cage_location_id']

    def _get_analytic_distribution(self):
        """
        The Single Odoo 19 Analytic Hook:
        Captures cage and batch analytic distribution across:
        1. Pre-laying feed & medication pickings to virtual consumption locations.
        2. Raw material feed consumption in egg harvest MOs (mrp.production).
        3. Bird mortality scrap moves (stock.scrap).
        4. Nightly unharvested feed fallback write-offs.
        """
        # Retain any explicit project/higher-priority distribution
        distribution = super()._get_analytic_distribution()
        if distribution:
            return distribution

        # Tag only cost-bearing outgoing moves: finished eggs entering stock must stay untagged
        cage = self._get_farm_cage_location()
        if cage and self._is_out():
            return cage.get_analytic_distribution_for_cage()
        return distribution

    def _prepare_analytic_line_values(self, account_field_values, amount, unit_amount):
        values = super()._prepare_analytic_line_values(account_field_values, amount, unit_amount)
        # Core names the line after move.reference, which is empty for a move with no picking,
        # scrap or inventory (e.g. a farm cron write-off); account.analytic.line.name is NOT NULL.
        if not values.get('name'):
            values['name'] = self.product_id.display_name
        return values

    def _get_farm_cage_location(self):
        """Return the cage whose Batch/Cage analytic accounts carry this move's cost (may be empty)."""
        self.ensure_one()
        # Case A: Explicit cage reference stamped on the move (Feed log, medication, cron)
        if self.farm_cage_location_id:
            return self.farm_cage_location_id

        # Case B: Source location is directly a cage (e.g. Mortality Scrap from Cage)
        if self.location_id.farm_hierarchy_level == 'cage':
            return self.location_id

        # Case C: Raw component of an Egg Collection MO. mrp.production and its farm_collection_id
        # come from mrp / top_farm_operations, which this module does not depend on.
        production = self['raw_material_production_id'] if 'raw_material_production_id' in self._fields else False
        if production and 'farm_collection_id' in production._fields:
            return production.farm_collection_id.cage_location_id
        return self.env['stock.location']
