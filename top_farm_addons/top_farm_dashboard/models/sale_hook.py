from odoo import models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        res = super()._action_done()
        self.move_ids.sale_line_id.sudo()._farm_update_batch_distribution()
        return res


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _farm_batch_accounts(self):
        """Analytic accounts of all farm batches (the ones this hook owns on a sale line)."""
        batches = self.env['stock.location'].sudo().search([('farm_hierarchy_level', '=', 'batch')])
        return batches.farm_analytic_account_id

    def _farm_update_batch_distribution(self):
        """Tag the line with the batch(es) of the egg lots really delivered, by net delivered quantity."""
        batch_accounts = self._farm_batch_accounts()
        for line in self:
            move_lines = self.env['stock.move.line'].search([
                ('move_id.sale_line_id', '=', line.id), ('move_id.state', '=', 'done'),
                ('lot_id.farm_batch_location_id', '!=', False)])
            qty = {}
            for ml in move_lines:
                if ml.location_dest_id.usage == 'customer':
                    sign = 1
                elif ml.location_id.usage == 'customer':
                    sign = -1
                else:
                    continue
                account = ml.lot_id.farm_batch_location_id.farm_analytic_account_id
                if account:
                    qty[account.id] = qty.get(account.id, 0.0) + sign * ml.quantity
            qty = {acc: q for acc, q in qty.items() if q > 0}
            if not qty:
                continue
            total = sum(qty.values())
            shares = {str(acc): round(q / total * 100.0, 4) for acc, q in qty.items()}
            biggest = max(shares, key=shares.get)
            shares[biggest] = round(shares[biggest] + 100.0 - sum(shares.values()), 4)
            kept = {k: v for k, v in (line.analytic_distribution or {}).items()
                    if not any(int(i) in batch_accounts.ids for i in k.split(','))}
            line.analytic_distribution = {**kept, **shares}


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        """A draft invoice created before the delivery picks the batch tag up from its sale line."""
        batch_ids = None
        for move in self.filtered(lambda m: m.state == 'draft' and m.move_type in ('out_invoice', 'out_refund')):
            for line in move.invoice_line_ids.filtered('sale_line_ids'):
                if batch_ids is None:
                    batch_ids = line.sale_line_ids[0]._farm_batch_accounts().ids
                sale_dist = line.sale_line_ids[0].analytic_distribution or {}
                have = line.analytic_distribution or {}
                has_batch = any(int(i) in batch_ids for k in have for i in k.split(','))
                missing = {k: v for k, v in sale_dist.items()
                           if any(int(i) in batch_ids for i in k.split(','))}
                if missing and not has_batch:
                    line.analytic_distribution = {**have, **missing}
        return super()._post(soft=soft)
