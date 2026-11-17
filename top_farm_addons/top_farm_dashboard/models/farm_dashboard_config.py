from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import SQL


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
                ('is_flock_batch', '=', True), ('flock_stage', 'not in', ('spent', 'closed')),
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
            # Feed and medication with no cost are consumed at zero value: the flock reports show the quantity
            # but no expenditure until the product is costed and the consumption revalued.
            uncosted = self.env['product.product'].sudo().with_company(cfg.company_id).search([
                ('farm_input_type', '!=', False), ('company_id', 'in', [cfg.company_id.id, False])]).filtered(
                lambda p: cfg.company_id.currency_id.is_zero(p.standard_price))
            if uncosted:
                lines.append(_("%(count)s feed / medication product(s) have no Cost, so the flocks consume them at "
                               "zero value: %(names)s.",
                               count=len(uncosted), names=', '.join(uncosted.mapped('display_name'))))
            zero_moves = cfg._farm_zero_cost_moves() | cfg._farm_unposted_moves()
            if zero_moves:
                lines.append(_("%(count)s feed / medication consumption(s) of the flocks carry no cost in the "
                               "accounting while the product now has a Cost (%(names)s): click Revalue Zero-Cost "
                               "Consumption.",
                               count=len(zero_moves), names=', '.join(zero_moves.product_id.mapped('display_name'))))
            cfg.accounting_warning = '\n'.join(lines)

    def _farm_zero_cost_moves(self):
        """Done feed and medication moves given to a flock with no stock value (received at zero cost) whose
        product now has a Cost: the moves Revalue Zero-Cost Consumption values."""
        self.ensure_one()
        moves = self.env['stock.move'].sudo().search([
            ('company_id', '=', self.company_id.id), ('state', '=', 'done'), ('farm_flock_lot_id', '!=', False),
            ('product_id.farm_input_type', '!=', False), ('value', '=', 0),
            '|', ('is_in', '=', True), ('is_out', '=', True)])
        return moves.filtered(lambda m: m.product_id.with_company(self.company_id).standard_price > 0
                              and not m.uom_id.is_zero(m.quantity))

    def _farm_unposted_moves(self):
        """Done feed and medication moves given to a flock that have a stock value now, but whose valuation entry
        was posted at zero (consumed while the stock was at zero cost, revalued since, e.g. when the product got
        its Cost): the flock's expense line of that entry is zero, so the cost is missing from the Profit and Loss.
        Only moves whose entry carries their flock expense line (top_farm_core) qualify: a move is never posted
        twice."""
        self.ensure_one()
        self.env.flush_all()
        rows = self.env.execute_query(SQL("""
            SELECT sm.id
              FROM stock_move sm
              JOIN product_product pp ON pp.id = sm.product_id
              JOIN product_template pt ON pt.id = pp.product_tmpl_id
              JOIN account_move am ON am.id = sm.account_move_id AND am.state = 'posted'
             WHERE sm.company_id = %(company)s AND sm.state = 'done' AND sm.farm_flock_lot_id IS NOT NULL
               AND pt.farm_input_type IS NOT NULL AND COALESCE(sm.value, 0) <> 0
               AND EXISTS (SELECT 1 FROM account_move_line aml
                            WHERE aml.move_id = am.id AND aml.farm_stock_move_id = sm.id)
               AND NOT EXISTS (SELECT 1 FROM account_move_line aml
                                WHERE aml.move_id = am.id AND aml.farm_stock_move_id = sm.id AND aml.balance <> 0)
        """, company=self.company_id.id))
        moves = self.env['stock.move'].sudo().browse(row[0] for row in rows)
        return moves.filtered(lambda m: m._should_create_account_move())

    def action_revalue_zero_cost_consumption(self):
        """Value the feed and medication the flocks consumed at zero cost at the current Cost of the product, as if
        the stock had been received at that cost (the standard Adjust Valuation, made for the farm):
        - average cost / FIFO: the receipts valued at zero (until the last such consumption) are valued at the
          current cost, then Odoo replays the valuation of the product, consumption included;
        - standard price: the current cost applies from the first zero-valued consumption, then Odoo replays.
        Consumptions in real-time valuation then get the valuation entry they missed (expense on the flock's
        analytic account, credit on the stock account), so the flock's cost is in the Profit and Loss too. This
        also covers consumptions Odoo already revalued itself when the product got its Cost (receipts without a
        purchase price are valued at the product cost), whose valuation entry stayed at zero."""
        if not self.env.user.has_group('top_farm_core.group_farm_manager'):
            raise AccessError(_("Only Farm Managers can revalue the flock consumption."))
        self.ensure_one()
        company = self.company_id
        moves = self._farm_zero_cost_moves()
        Move = self.env['stock.move'].sudo().with_company(company)
        for product, product_moves in moves.grouped('product_id').items():
            product = product.sudo().with_company(company)
            from_date = min(product_moves.mapped('date')) - timedelta(seconds=1)
            if product.cost_method == 'standard':
                product._change_standard_price({product: 0.0}, valuation_date=from_date)
            else:
                receipts = Move.search([
                    ('product_id', '=', product.id), ('company_id', '=', company.id), ('state', '=', 'done'),
                    ('is_in', '=', True), ('value', '=', 0), ('date', '<=', max(product_moves.mapped('date')))])
                receipts = receipts.filtered(lambda m: m._get_valued_qty())
                if receipts:
                    self.env['product.value'].sudo().with_company(company).create([{
                        'move_id': receipt.id, 'company_id': company.id,
                        'value': company.currency_id.round(receipt._get_valued_qty() * product.standard_price),
                    } for receipt in receipts])
                    from_date = min(from_date, min(receipts.mapped('date')) - timedelta(seconds=1))
            product._correct_inventory_valuation(from_date)
        revalued = moves.filtered('value')
        left = moves - revalued
        unposted = self._farm_unposted_moves()
        for move in unposted:
            move._farm_post_missing_valuation()
        (revalued | unposted)._create_analytic_move()
        if not moves and not unposted:
            message = _("No flock consumption is missing its cost: nothing to revalue.")
        else:
            message = _("%(revalued)s zero-cost flock consumption(s) revalued at the current product cost; "
                        "%(posted)s valuation entry(ies) posted to the flocks.",
                        revalued=len(revalued), posted=len(unposted))
        if left:
            message += ' ' + _("Not revalued (the stock they came from was not received at zero cost): %s.",
                               ', '.join(left.mapped('reference')))
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'warning' if left else 'success', 'title': _("Revalue Zero-Cost Consumption"),
            'message': message, 'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}

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
