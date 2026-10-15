# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _correct_inventory_valuation(self, from_date):
        """A revaluation (Adjust Valuation, bill price difference, landed cost) replays the value of past
        moves, but standard Odoo leaves their analytic lines at the old amount: the cage P&L then disagrees
        with the stock value. Re-price those analytic lines once the replay is done."""
        res = super()._correct_inventory_valuation(from_date)
        self._farm_resync_stock_analytics(from_date)
        return res

    def _farm_resync_stock_analytics(self, from_date=None):
        """Bring the analytic lines of the done moves of these products back to the moves' current value.
        Existing lines are updated in place (no reversal, no duplicate). Only moves that still resolve to a
        distribution are touched: a move whose tagging module is not loaded (e.g. during an upgrade) keeps its
        lines instead of losing them."""
        domain = [('product_id', 'in', self.ids), ('state', '=', 'done')]
        if from_date and from_date != datetime.min:
            domain.append(('date', '>=', from_date))
        moves = self.env['stock.move'].sudo().search(domain)
        moves = moves.filtered(lambda m: m._get_analytic_distribution())
        moves._create_analytic_move()
        return moves
