from odoo import models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        res = super()._action_done()
        self.move_ids.sale_line_id.sudo()._farm_update_flock_distribution()
        return res


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _farm_flock_accounts(self):
        """Analytic accounts of all flocks (the ones this hook owns on a sale line)."""
        flocks = self.env['stock.lot'].sudo().search([('is_flock_batch', '=', True)])
        return flocks.flock_analytic_account_id

    def _farm_update_flock_distribution(self):
        """Tag the line with the flock(s) really delivered, by net delivered quantity: the parent flock of an
        egg lot, or the flock lot itself for birds (e.g. spent hens)."""
        flock_accounts = self._farm_flock_accounts()
        for line in self:
            move_lines = self.env['stock.move.line'].search([
                ('move_id.sale_line_id', '=', line.id), ('move_id.state', '=', 'done'),
                '|', ('lot_id.farm_flock_lot_id', '!=', False), ('lot_id.is_flock_batch', '=', True)])
            qty = {}
            for ml in move_lines:
                if ml.location_dest_id.usage == 'customer':
                    sign = 1
                elif ml.location_id.usage == 'customer':
                    sign = -1
                else:
                    continue
                flock = ml.lot_id.farm_flock_lot_id or ml.lot_id
                account = flock.flock_analytic_account_id
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
                    if not any(int(i) in flock_accounts.ids for i in k.split(','))}
            line.analytic_distribution = {**kept, **shares}


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        """A draft invoice created before the delivery picks the flock tag up from its sale line."""
        flock_ids = None
        for move in self.filtered(lambda m: m.state == 'draft' and m.move_type in ('out_invoice', 'out_refund')):
            for line in move.invoice_line_ids.filtered('sale_line_ids'):
                if flock_ids is None:
                    flock_ids = line.sale_line_ids[0]._farm_flock_accounts().ids
                sale_dist = line.sale_line_ids[0].analytic_distribution or {}
                have = line.analytic_distribution or {}
                has_flock = any(int(i) in flock_ids for k in have for i in k.split(','))
                missing = {k: v for k, v in sale_dist.items()
                           if any(int(i) in flock_ids for i in k.split(','))}
                if missing and not has_flock:
                    line.analytic_distribution = {**have, **missing}
        return super()._post(soft=soft)
