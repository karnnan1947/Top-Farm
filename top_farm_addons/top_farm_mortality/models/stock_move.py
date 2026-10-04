from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    farm_mortality_log_id = fields.Many2one('farm.mortality.log', string='Mortality Log',
                                            copy=False, index='btree_not_null', readonly=True)

    def _get_analytic_distribution(self):
        """top_farm_core already tags outgoing cage moves (the scrap). It does not tag an incoming
        move, so the Reverse move is tagged here with the cage's own Batch+Cage distribution,
        which makes its analytic line offset the original one."""
        distribution = super()._get_analytic_distribution()
        if distribution or not self.farm_mortality_log_id:
            return distribution
        return self.farm_mortality_log_id.cage_location_id.get_analytic_distribution_for_cage()
