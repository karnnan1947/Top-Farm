from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class FarmDashboardConfig(models.Model):
    _name = 'farm.dashboard.config'
    _description = 'Top Farm Dashboard Settings (per company)'
    _rec_name = 'company_id'

    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company, ondelete='cascade')
    target_hen_day_pct = fields.Float(string='Hen-Day Target (%)', default=92.0)
    target_fcr = fields.Float(string='FCR Target (kg/dozen, at most)', default=1.25, digits=(16, 3))
    mortality_alert_pct = fields.Float(
        string='Mortality Alert (%)', default=0.0, digits=(16, 3),
        help="The mortality card turns red above this rate. 0 = use the Mortality Controls threshold.")
    low_margin_pct = fields.Float(string='Low Margin Warning (%)', default=30.0,
                                  help="Flocks below this lifetime margin are highlighted in the profitability report.")
    currency_id = fields.Many2one(related='company_id.currency_id')
    pre_laying_target_cost = fields.Monetary(
        string='Target Pre-Laying Cost per Bird', default=1200.0,
        help="Expected investment in a pullet at point of lay (chick, feed, medication and direct costs). The "
             "remaining pre-laying budget per bird is measured against it.")
    pre_laying_target_cost_max = fields.Monetary(
        string='Upper Pre-Laying Benchmark per Bird', default=1300.0)
    feed_category_ids = fields.Many2many(
        'product.category', 'farm_dashboard_feed_categ_rel', 'config_id', 'category_id',
        string='Feed Categories',
        help="Analytic costs of products in these categories (and children) also count as Feed, besides the "
             "products whose Farm Input Type is Feed.")
    medication_category_ids = fields.Many2many(
        'product.category', 'farm_dashboard_med_categ_rel', 'config_id', 'category_id',
        string='Medication / Vaccine Categories',
        help="Analytic costs of products in these categories (and children) also count as Medication, besides "
             "the products whose Farm Input Type is Medication / Vaccine.")
    accounting_warning = fields.Text(compute='_compute_accounting_warning')

    _company_unique = models.Constraint('unique(company_id)', 'There is already a dashboard setting for this company.')

    @api.constrains('target_hen_day_pct', 'target_fcr', 'mortality_alert_pct', 'low_margin_pct',
                    'pre_laying_target_cost', 'pre_laying_target_cost_max')
    def _check_values(self):
        for cfg in self:
            if not 0 <= cfg.target_hen_day_pct <= 100 or not 0 <= cfg.mortality_alert_pct <= 100:
                raise ValidationError(_("Percentages must be between 0 and 100."))
            if cfg.target_fcr < 0:
                raise ValidationError(_("The FCR target cannot be negative."))
            if not 0 <= cfg.pre_laying_target_cost <= cfg.pre_laying_target_cost_max:
                raise ValidationError(_("The pre-laying cost target must be positive and at most the upper benchmark."))

    def _compute_accounting_warning(self):
        for cfg in self:
            lines = []
            # Costs reach the profitability and investment reports through the analytic accounts: without one a
            # flock or cage is silently absent from them (it still shows in the Feed Consumption report).
            flocks = self.env['stock.lot'].sudo().search([
                ('is_flock_batch', '=', True), ('flock_stage', '!=', 'spent'),
                ('flock_analytic_account_id', '=', False), ('company_id', 'in', [cfg.company_id.id, False])])
            if flocks:
                lines.append(_("%(count)s active flock(s) have no Flock Analytic Account, so their costs are not in "
                               "the profitability and investment reports: %(names)s.",
                               count=len(flocks), names=', '.join(flocks.mapped('name'))))
            cages = self.env['stock.location'].sudo().search([
                ('farm_hierarchy_level', '=', 'cage'), ('farm_analytic_account_id', '=', False),
                ('company_id', 'in', [cfg.company_id.id, False])])
            if cages:
                lines.append(_("%(count)s cage(s) have no Cage Analytic Account: their costs are still reported per "
                               "flock, but not per cage: %(names)s.",
                               count=len(cages), names=', '.join(cages.mapped('display_name'))))
            cfg.accounting_warning = '\n'.join(lines)

    def action_resync_stock_analytics(self):
        """Re-price the analytic lines of every done farm stock move at the move's current value (repairs lines
        left behind by a revaluation made before the automatic re-sync existed)."""
        if not self.env.user.has_group('top_farm_core.group_farm_manager'):
            raise AccessError(_("Only Farm Managers can re-sync the stock analytics."))
        products = self.env['product.product'].sudo().search(
            ['|', ('farm_input_type', '!=', False), ('is_farm_bird', '=', True)])
        moves = products._farm_resync_stock_analytics()
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'title': _("Stock analytics re-synced"),
            'message': _("%s stock moves checked; their analytic lines now match the stock value.", len(moves))}}

    @api.model
    def _get_config(self, company=None):
        company = company or self.env.company
        cfg = self.sudo().search([('company_id', '=', company.id)], limit=1)
        return cfg or self.sudo().create({'company_id': company.id})

    @api.model
    def action_open_config(self):
        cfg = self._get_config()
        return {'type': 'ir.actions.act_window', 'name': _("Dashboard Settings"),
                'res_model': 'farm.dashboard.config', 'res_id': cfg.id, 'view_mode': 'form', 'target': 'current'}
