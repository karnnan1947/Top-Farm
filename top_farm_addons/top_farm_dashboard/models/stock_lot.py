from odoo import fields, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    farm_batch_location_id = fields.Many2one(
        'stock.location', string='Farm Batch', index='btree_not_null', copy=False, readonly=True,
        help="Flock batch that produced this egg lot. Set when the egg collection creates the lot; "
             "never parsed from the lot name.")
    farm_production_date = fields.Date(
        string='Egg Production Date', index='btree_not_null', copy=False, readonly=True)


class FarmEggCollection(models.Model):
    _inherit = 'farm.egg.collection'

    def _get_egg_lot(self, product):
        """Stamp the daily egg lot with its batch and production day (used for invoice tagging)."""
        lot = super()._get_egg_lot(product)
        if lot and not lot.farm_batch_location_id:
            lot.sudo().write({'farm_batch_location_id': self.batch_location_id.id,
                              'farm_production_date': self.date})
        return lot
