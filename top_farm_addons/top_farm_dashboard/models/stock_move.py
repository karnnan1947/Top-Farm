from odoo import fields, models
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _farm_post_missing_valuation(self):
        """A consumption valued at zero (stock received at zero cost) got a valuation entry of zero, so no analytic
        item reached the flock. Once the move is revalued, post the valuation entry it should have had: the flock's
        expense line (with its analytic distribution, see top_farm_core) against the stock account, dated on the
        consumption, or today when that period is locked. The move is linked to the new entry; the zero entry
        stays as it was."""
        self.ensure_one()
        for date in (fields.Date.context_today(self, self.date), False):
            try:
                with self.env.cr.savepoint():
                    return self.with_context(force_period_date=date)._create_account_move()
            except UserError:
                if not date:
                    raise
        return self.env['account.move']
