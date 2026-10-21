from odoo import fields, models, tools
from odoo.tools import SQL

from .report_sql import cost_ctes

COMPONENTS = [
    ('chick', 'Day-Old Chick Purchase'),
    ('feed', 'Starter & Grower Feed'),
    ('medication', 'Vaccines & Medications'),
    ('other', 'Heating, Labour & Other Direct Costs'),
]


class FarmFlockInvestmentReport(models.Model):
    _name = 'farm.flock.investment.report'
    _description = 'Pre-Laying Flock Investment'
    _auto = False
    _order = 'date desc, id'

    date = fields.Date(readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)
    flock_lot_id = fields.Many2one('stock.lot', string='Flock', readonly=True)
    farm_location_id = fields.Many2one('stock.location', string='Farm', readonly=True)
    flock_stage = fields.Selection(
        selection=lambda self: self.env['stock.lot']._fields['flock_stage'].selection,
        string='Flock Stage', readonly=True)
    component = fields.Selection(COMPONENTS, string='Cost Component', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    quantity = fields.Float(string='Quantity', readonly=True, digits=(16, 2))
    cost = fields.Monetary(string='Expenditure', currency_field='currency_id', readonly=True)
    placed_bird_count = fields.Integer(
        string='Placed Birds', readonly=True,
        help="Chicks placed in the brooding nursery under the flock lot, dead or alive.")
    cost_per_placed_bird = fields.Monetary(
        string='Cost / Placed Bird', currency_field='currency_id', readonly=True,
        help="Expenditure per chick placed: the baseline input cost.")
    bird_count = fields.Integer(
        string='Live Birds', readonly=True,
        help="Birds the investment is spread over: the live birds of the flock now, or at the start of the "
             "Laying Phase once it is locked.")
    cost_per_bird = fields.Monetary(
        string='Cost / Live Bird', currency_field='currency_id', readonly=True,
        help="Expenditure per surviving bird: the cost each hen carries, the cost of the birds lost included.")

    def _read_group_select(self, table, aggregate_spec):
        # A cost per bird (and the bird basis) only adds up within one flock: leave mixed groups empty
        if aggregate_spec in ('cost_per_bird:sum', 'cost_per_placed_bird:sum'):
            return SQL("CASE WHEN COUNT(DISTINCT %(flock)s) = 1 THEN SUM(%(value)s) END",
                       flock=table['flock_lot_id'], value=table[aggregate_spec.split(':')[0]])
        if aggregate_spec in ('bird_count:sum', 'placed_bird_count:sum'):
            return SQL("CASE WHEN COUNT(DISTINCT %(flock)s) = 1 THEN MAX(%(value)s) END",
                       flock=table['flock_lot_id'], value=table[aggregate_spec.split(':')[0]])
        return super()._read_group_select(table, aggregate_spec)

    def init(self):
        """Cumulative investment in a flock from day 0 until the Laying Phase starts: the chicks placed under
        the flock lot, then the feed, medication and other direct costs tagged to its analytic account. Laying
        feed (egg production orders, unharvested laying feed) and the mortality scraps are left out (the chick
        cost already counts every bird placed, dead or alive)."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                WITH {cost_ctes(self.env)},
                flock AS (
                    SELECT lot.id, lot.farm_location_id, lot.flock_stage, lot.laying_start_date,
                           COALESCE(lot.initial_bird_count, 0) AS placed_birds,
                           CASE WHEN lot.laying_start_date IS NOT NULL THEN lot.laying_start_bird_count
                                ELSE COALESCE((SELECT SUM(q.quantity) FROM stock_quant q
                                                 JOIN stock_location l ON l.id = q.location_id
                                                WHERE q.lot_id = lot.id AND l.usage = 'internal'), 0)
                           END AS birds
                      FROM stock_lot lot
                     WHERE lot.is_flock_batch
                ),
                chicks AS (
                    SELECT sm.date::date AS date, sm.company_id, sml.lot_id AS flock_lot_id, sm.product_id,
                           SUM(sml.quantity_product_uom) AS quantity,
                           COALESCE(sm.value, 0) * SUM(sml.quantity_product_uom) / NULLIF(sm.product_qty, 0) AS cost
                      FROM stock_move sm
                      JOIN stock_move_line sml ON sml.move_id = sm.id
                      JOIN stock_lot lot ON lot.id = sml.lot_id AND lot.is_flock_batch
                     WHERE sm.state = 'done' AND sm.is_in AND sm.farm_mortality_log_id IS NULL
                     GROUP BY sm.id, sml.lot_id
                )
                SELECT row_number() OVER () AS id, u.date, u.company_id, rc.currency_id, u.flock_lot_id,
                       f.farm_location_id, f.flock_stage, u.component, u.product_id, u.quantity, u.cost,
                       f.placed_birds AS placed_bird_count,
                       CASE WHEN f.placed_birds > 0 THEN u.cost / f.placed_birds ELSE 0 END AS cost_per_placed_bird,
                       f.birds AS bird_count,
                       CASE WHEN f.birds > 0 THEN u.cost / f.birds ELSE 0 END AS cost_per_bird
                  FROM (
                        SELECT c.date, c.company_id, c.flock_lot_id, 'chick' AS component, c.product_id,
                               c.quantity, c.cost
                          FROM chicks c
                        UNION ALL
                        SELECT co.date, co.company_id, co.flock_lot_id, co.cost_type, co.product_id,
                               co.quantity, co.cost
                          FROM costs co
                         WHERE co.flock_lot_id IS NOT NULL AND co.cost_type IN ('feed', 'medication', 'other')
                           AND NOT co.laying_phase
                  ) u
                  JOIN flock f ON f.id = u.flock_lot_id
                  JOIN res_company rc ON rc.id = u.company_id
                 WHERE f.laying_start_date IS NULL OR u.date <= f.laying_start_date
            )""")
