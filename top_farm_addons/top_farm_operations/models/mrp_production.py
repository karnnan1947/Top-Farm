# -*- coding: utf-8 -*-
from odoo import Command, fields, models, _
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    # top_farm_core's analytic hook reads farm_collection_id.flock_lot_id / cage_location_id on raw moves
    farm_collection_id = fields.Many2one(
        'farm.egg.collection',
        string='Source Farm Egg Collection',
        readonly=True,
        index='btree_not_null',
        copy=False,
        help="Links manufacturing order back to the daily poultry egg collection."
    )

    # Broiler harvest: live birds (units) in, meat (kg) out
    farm_broiler_lot_id = fields.Many2one(
        'stock.lot', string='Broiler Batch', readonly=True, index='btree_not_null', copy=False,
        help="Broiler batch harvested by this order: its live birds are converted into meat by weight.")
    farm_broiler_bird_count = fields.Integer(string='Birds Harvested', readonly=True, copy=False)
    farm_broiler_weight_kg = fields.Float(string='Net Weight (kg)', digits=(16, 2), readonly=True, copy=False)
    farm_currency_id = fields.Many2one(related='company_id.currency_id', string='Company Currency')
    farm_broiler_batch_cost = fields.Monetary(
        string='Batch Cost Released', currency_field='farm_currency_id', readonly=True, copy=False,
        help="Batch cost carried by the harvested birds: their stock value plus their share of the Broiler Cost "
             "Pool (capitalized feed, medication and mortality). It is the stock value of the meat.")
    farm_broiler_pool_cost = fields.Monetary(
        string='Released from Cost Pool', currency_field='farm_currency_id', readonly=True, copy=False,
        help="The harvested birds' share of the batch's Broiler Cost Pool (all of it for the last birds), set as "
             "the order's extra cost so the meat carries it.")
    farm_broiler_pool_move_id = fields.Many2one(
        'account.move', string='Cost Pool Release Entry', readonly=True, copy=False)
    farm_broiler_sale_id = fields.Many2one('sale.order', string='Meat Sales Order', readonly=True, copy=False)

    def _farm_check_not_broiler_harvest(self):
        """A broiler harvest is posted at once: its meat carries the batch cost (Broiler Cost Pool entry), a sales
        order bills it and the batch may have closed with it. Reverting its stock would leave those behind."""
        harvests = self.filtered('farm_broiler_lot_id')
        if harvests:
            raise UserError(_(
                "%(orders)s is a broiler harvest of batch %(batch)s: it cannot be reset or unbuilt. Its meat is "
                "valued at the batch cost and sold on %(sale)s.", orders=harvests[0].name,
                batch=harvests[0].farm_broiler_lot_id.name, sale=harvests[0].farm_broiler_sale_id.name or '-'))

    def action_reset_to_progress(self):
        self._farm_check_not_broiler_harvest()
        return super().action_reset_to_progress()

    def action_reset_to_draft(self):
        self._farm_check_not_broiler_harvest()
        return super().action_reset_to_draft()

    def button_unbuild(self):
        self._farm_check_not_broiler_harvest()
        return super().button_unbuild()

    def _cal_price(self, consumed_moves):
        """A broiler harvest gives the meat the batch cost of the birds it took: their stock value (the consumed
        moves) plus their share of the Broiler Cost Pool, which becomes the order's extra unit cost."""
        if self.farm_broiler_lot_id:
            finished_moves = self.move_finished_ids.filtered(
                lambda m: m.product_id == self.product_id and m.state not in ('done', 'cancel')
                and m.uom_id.compare(m.quantity, 0) > 0)
            quantity = sum(m.uom_id._compute_quantity(m.quantity, m.product_id.uom_id) for m in finished_moves)
            pool_cost = self.farm_broiler_pool_cost
            self.write({
                'farm_broiler_batch_cost': abs(sum(consumed_moves.mapped('value'))) + pool_cost,
                'extra_cost': pool_cost / quantity if quantity else 0.0,
            })
        return super()._cal_price(consumed_moves)

    def _post_inventory(self, cancel_backorder=False):
        res = super()._post_inventory(cancel_backorder=cancel_backorder)
        self.filtered(lambda mo: mo.farm_broiler_lot_id and mo.state == 'done')._farm_post_broiler_pool_release()
        return res

    def _farm_post_broiler_pool_release(self):
        """The meat's valuation includes the batch's Broiler Cost Pool share: take it out of the pool account
        into the production WIP account, which the meat's own valuation entry credits (or straight into the
        meat's stock account when the production location has no account)."""
        for production in self.filtered(lambda mo: not mo.farm_broiler_pool_move_id):
            company = production.company_id
            amount = production.farm_broiler_pool_cost
            pool_account = company._get_farm_broiler_cost_location().valuation_account_id
            if company.currency_id.is_zero(amount) or not pool_account:
                continue
            product = production.product_id.with_company(company)
            debit_account = production.production_location_id.valuation_account_id \
                or product._get_product_accounts()['stock_valuation']
            if not debit_account:
                continue
            journal = company.account_stock_journal_id \
                or product.product_tmpl_id.get_product_accounts()['stock_journal']
            label = _("%(order)s - cost of broiler batch %(batch)s released from the cost pool",
                      order=production.name, batch=production.farm_broiler_lot_id.name)
            entry = self.env['account.move'].sudo().with_company(company).create({
                'journal_id': journal.id,
                'date': fields.Date.context_today(production),
                'ref': label,
                'move_type': 'entry',
                'line_ids': [
                    Command.create({'name': label, 'account_id': debit_account.id, 'balance': amount}),
                    Command.create({'name': label, 'account_id': pool_account.id, 'balance': -amount}),
                ],
            })
            entry._post()
            production.farm_broiler_pool_move_id = entry


class MrpUnbuild(models.Model):
    _inherit = 'mrp.unbuild'

    def action_unbuild(self):
        self.mo_id._farm_check_not_broiler_harvest()
        return super().action_unbuild()
