from odoo import fields, models


class StockScrap(models.Model):
    _inherit = 'stock.scrap'

    farm_mortality_log_id = fields.Many2one('farm.mortality.log', string='Mortality Log',
                                            copy=False, index='btree_not_null', readonly=True)

    def _prepare_move_values(self):
        vals = super()._prepare_move_values()
        if self.farm_mortality_log_id:
            vals['farm_mortality_log_id'] = self.farm_mortality_log_id.id
        return vals
