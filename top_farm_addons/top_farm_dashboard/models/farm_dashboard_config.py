from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


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
                                  help="Profitability rows below this margin are highlighted.")
    feed_category_ids = fields.Many2many(
        'product.category', 'farm_dashboard_feed_categ_rel', 'config_id', 'category_id',
        string='Feed Categories', help="Analytic costs of products in these categories (and children) count as Feed.")
    medication_category_ids = fields.Many2many(
        'product.category', 'farm_dashboard_med_categ_rel', 'config_id', 'category_id',
        string='Medication / Vaccine Categories',
        help="Analytic costs of products in these categories (and children) count as Medication.")
    accounting_warning = fields.Text(compute='_compute_accounting_warning')

    _company_unique = models.Constraint('unique(company_id)', 'There is already a dashboard setting for this company.')

    @api.constrains('target_hen_day_pct', 'target_fcr', 'mortality_alert_pct', 'low_margin_pct')
    def _check_values(self):
        for cfg in self:
            if not 0 <= cfg.target_hen_day_pct <= 100 or not 0 <= cfg.mortality_alert_pct <= 100:
                raise ValidationError(_("Percentages must be between 0 and 100."))
            if cfg.target_fcr < 0:
                raise ValidationError(_("The FCR target cannot be negative."))

    @api.depends('feed_category_ids', 'medication_category_ids')
    def _compute_accounting_warning(self):
        for cfg in self:
            lines = []
            if not cfg.feed_category_ids:
                lines.append(_("No Feed categories are set: feed cost will show as 0 in the profitability report."))
            if not cfg.medication_category_ids:
                lines.append(_("No Medication categories are set: medication cost will show as 0."))
            cfg.accounting_warning = '\n'.join(lines)

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
