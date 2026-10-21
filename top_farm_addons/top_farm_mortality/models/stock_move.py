from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    farm_mortality_log_id = fields.Many2one('farm.mortality.log', string='Mortality Log',
                                            copy=False, index='btree_not_null', readonly=True)

    def _get_analytic_distribution(self):
        """top_farm_core already tags the outgoing scrap (it carries the flock and its location). It does not
        tag an incoming move, so the Reverse move is tagged here with the same Flock (+ Cage) distribution,
        which makes its analytic line offset the original one."""
        distribution = super()._get_analytic_distribution()
        if distribution or not self.farm_mortality_log_id:
            return distribution
        log = self.farm_mortality_log_id
        return log.lot_id.get_flock_analytic_distribution(log.location_id)
