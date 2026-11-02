# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    farm_lot_generation_mode = fields.Selection([
        ('manual', 'Approach A: Manual Entry'),
        ('auto', 'Approach B: Automated Estate Lot Allocation'),
    ], string='Flock Lot Generation Mode', default='auto', required=True,
       help="How the flock lot is set when chicks are dispatched to a brooding nursery.\n"
            "Manual: the warehouse clerk enters the flock lot on each transfer line before validating.\n"
            "Automated: the system names the lot [Estate Code]-[Date] (e.g. IHL-19-10-2026) when the transfer "
            "is validated; a lot entered on the line still takes precedence.")
    farm_lot_date_source = fields.Selection([
        ('arrival', 'Chick Arrival Date'),
        ('transfer', 'Transfer Validation Date'),
    ], string='Estate Lot Date Source', default='arrival', required=True,
       help="Date embedded in automatically generated flock lots: the date the chicks arrived from the "
            "hatchery at the main warehouse, or the date the dispatch to the estate is validated.")
    farm_flock_auto_analytic = fields.Boolean(
        string='Auto-create Flock Analytic Account', default=True,
        help="Give every new flock lot its own analytic account in the Flock Analytic Plan.")
    farm_flock_analytic_plan_id = fields.Many2one(
        'account.analytic.plan', string='Flock Analytic Plan',
        help="Plan of the flock analytic accounts. Cage analytic accounts must belong to another root plan.")
    farm_broiler_cost_location_id = fields.Many2one(
        'stock.location', string='Broiler Cost Pool Location',
        domain="[('usage', '=', 'inventory')]",
        help="Virtual location receiving the feed, medication and dead birds of broiler batches, so that their "
             "cost stays capitalized in the batch until harvest. Give it a current asset valuation account.")

    def write(self, vals):
        res = super().write(vals)
        if vals.get('farm_broiler_cost_location_id'):
            self.farm_broiler_cost_location_id.sudo().farm_broiler_cost_pool = True
        return res

    def _get_farm_flock_plan(self):
        self.ensure_one()
        return self.farm_flock_analytic_plan_id or self.env.ref(
            'top_farm_core.analytic_plan_flock_batches', raise_if_not_found=False)

    def _get_farm_broiler_cost_location(self):
        """The company's Broiler Cost Pool location, created on first use (without a valuation account: the
        accountant gives it one, otherwise the capitalized costs are tracked in stock only)."""
        self.ensure_one()
        if not self.farm_broiler_cost_location_id:
            Location = self.env['stock.location'].sudo()
            location = Location.search([('farm_broiler_cost_pool', '=', True), ('usage', '=', 'inventory'),
                                        ('company_id', 'in', [self.id, False])], limit=1) \
                or Location.create({'name': 'Broiler Rearing Costs', 'usage': 'inventory', 'company_id': self.id,
                                    'farm_broiler_cost_pool': True})
            self.sudo().farm_broiler_cost_location_id = location
        return self.farm_broiler_cost_location_id
