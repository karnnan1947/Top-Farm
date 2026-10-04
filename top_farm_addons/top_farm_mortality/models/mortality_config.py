from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FarmMortalityConfig(models.Model):
    _name = 'farm.mortality.config'
    _description = 'Mortality Controls (per company)'
    _rec_name = 'company_id'

    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)
    daily_mortality_threshold_pct = fields.Float(
        string='Daily Mortality Approval Threshold (%)', default=2.0,
        help="Cumulative dead birds in one cage on one day, as a percentage of the cage's opening "
             "population, above which Farm Manager approval is mandatory.")
    min_dead_count = fields.Integer(
        string='Minimum Dead Birds For Approval', default=0,
        help="Approval is only required when the cumulative dead count also exceeds this number. "
             "0 = no floor. Useful for very small cages.")
    accounting_warning = fields.Text(compute='_compute_accounting_warning')

    _company_uniq = models.Constraint('unique(company_id)', 'Only one mortality configuration per company.')

    @api.constrains('daily_mortality_threshold_pct', 'min_dead_count')
    def _check_values(self):
        for cfg in self:
            if not 0.0 <= cfg.daily_mortality_threshold_pct <= 100.0:
                raise ValidationError(_("The threshold must be between 0 and 100 %."))
            if cfg.min_dead_count < 0:
                raise ValidationError(_("The minimum dead-bird count cannot be negative."))

    @api.model
    def _get_config(self, company=None):
        """Return the (sudo) configuration of the company, creating it on first use."""
        company = company or self.env.company
        cfg = self.sudo().search([('company_id', '=', company.id)], limit=1)
        return cfg or self.sudo().create({'company_id': company.id})

    @api.model
    def action_open_config(self):
        cfg = self._get_config()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Mortality Controls"),
            'res_model': 'farm.mortality.config',
            'res_id': cfg.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _compute_accounting_warning(self):
        loc = self.env['farm.mortality.log']._get_scrap_location()
        bad_categs = self.env['product.template'].sudo().search(
            [('is_farm_bird', '=', True), ('categ_id.property_valuation', '!=', 'real_time')]
        ).categ_id.mapped('display_name')
        for cfg in self:
            lines = []
            if not loc.valuation_account_id:
                lines.append(_("The location '%s' has no Loss Account: no mortality journal entry "
                               "will be posted (stock and analytic lines still are).",
                               loc.display_name))
            if bad_categs:
                lines.append(_("Bird product categories without Automated valuation: %s. "
                               "No journal entry will be posted for them.", ', '.join(bad_categs)))
            cfg.accounting_warning = '\n'.join(lines)
