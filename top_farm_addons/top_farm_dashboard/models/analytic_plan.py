from odoo import api, models, tools


class AccountAnalyticPlan(models.Model):
    _inherit = 'account.analytic.plan'

    _FARM_VIEWS = ('farm.profitability.report',)

    def _farm_rebuild_views(self):
        for name in self._FARM_VIEWS:
            self.env[name].init()

    def _farm_drop_views(self):
        for name in self._FARM_VIEWS:
            tools.drop_view_if_exists(self.env.cr, self.env[name]._table)

    @api.model_create_multi
    def create(self, vals_list):
        plans = super().create(vals_list)
        plans._farm_rebuild_views()
        return plans

    def unlink(self):
        self._farm_drop_views()
        res = super().unlink()
        self._farm_rebuild_views()
        return res
