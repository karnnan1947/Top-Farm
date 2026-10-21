from odoo import fields, models, tools
from odoo.tools import SQL

from .report_sql import REVENUE_CTES, cost_ctes


class FarmProfitabilityReport(models.Model):
    _name = 'farm.profitability.report'
    _description = 'Flock Lifetime Profitability'
    _auto = False
    _order = 'date desc, id'

    date = fields.Date(readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)
    flock_lot_id = fields.Many2one('stock.lot', string='Flock', readonly=True)
    farm_location_id = fields.Many2one('stock.location', string='Farm', readonly=True)
    cage_location_id = fields.Many2one('stock.location', string='Cage', readonly=True)
    production_date = fields.Date(string='Egg Production Date', readonly=True)
    eggs_sold = fields.Float(string='Eggs Sold', readonly=True, digits=(16, 2))
    birds_sold = fields.Float(string='Birds Sold', readonly=True, digits=(16, 2))
    egg_revenue = fields.Monetary(string='Egg Revenue', currency_field='currency_id', readonly=True)
    bird_revenue = fields.Monetary(
        string='Spent Hen Revenue', currency_field='currency_id', readonly=True,
        help="Invoiced sales of the flock's live birds (spent hens, culls).")
    revenue = fields.Monetary(string='Total Revenue', currency_field='currency_id', readonly=True)
    feed_cost = fields.Monetary(string='Feed Cost', currency_field='currency_id', readonly=True)
    medication_cost = fields.Monetary(string='Medication Cost', currency_field='currency_id', readonly=True)
    mortality_cost = fields.Monetary(string='Mortality Loss', currency_field='currency_id', readonly=True)
    bird_cost = fields.Monetary(
        string='Bird Cost of Sales', currency_field='currency_id', readonly=True,
        help="Stock value of the birds that left the flock other than by mortality (e.g. spent hens sold).")
    other_cost = fields.Monetary(
        string='Other Direct Cost', currency_field='currency_id', readonly=True,
        help="Other costs tagged to the flock: heating, labour and other bills.")
    total_cost = fields.Monetary(string='Total Direct Cost', currency_field='currency_id', readonly=True)
    gross_profit = fields.Monetary(string='Gross Operating Profit', currency_field='currency_id', readonly=True)
    operating_margin_pct = fields.Float(string='Operating Margin (%)', readonly=True, digits=(16, 2))
    low_margin = fields.Boolean(
        string='Low Margin Flock', readonly=True,
        help="The flock's lifetime margin (all dates) is below the Low Margin Warning of the Dashboard Settings, "
             "or the flock has costs and no revenue yet.")

    def _read_group_select(self, table, aggregate_spec):
        # A margin is never the sum of margins: compute it from the summed profit and revenue of each group.
        if aggregate_spec == 'operating_margin_pct:sum':
            return SQL("CASE WHEN SUM(%(rev)s) = 0 THEN 0 ELSE SUM(%(profit)s) / SUM(%(rev)s) * 100 END",
                       rev=table['revenue'], profit=table['gross_profit'])
        return super()._read_group_select(table, aggregate_spec)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                WITH {REVENUE_CTES}, {cost_ctes(self.env)},
                u AS (
                    SELECT rev.date, rev.company_id, rev.flock_lot_id, rev.farm_location_id, rev.cage_location_id,
                           rev.production_date, rev.eggs_sold, rev.birds_sold,
                           CASE WHEN rev.grade = 'spent_hen' THEN 0.0 ELSE rev.revenue END AS egg_revenue,
                           CASE WHEN rev.grade = 'spent_hen' THEN rev.revenue ELSE 0.0 END AS bird_revenue,
                           0.0 AS feed_cost, 0.0 AS medication_cost, 0.0 AS mortality_cost, 0.0 AS bird_cost,
                           0.0 AS other_cost
                      FROM rev
                    UNION ALL
                    SELECT c.date, c.company_id, c.flock_lot_id, c.farm_location_id, c.cage_location_id,
                           NULL::date, 0.0, 0.0, 0.0, 0.0,
                           CASE WHEN c.cost_type = 'feed' THEN c.cost ELSE 0.0 END,
                           CASE WHEN c.cost_type = 'medication' THEN c.cost ELSE 0.0 END,
                           CASE WHEN c.cost_type = 'mortality' THEN c.cost ELSE 0.0 END,
                           CASE WHEN c.cost_type = 'depletion' THEN c.cost ELSE 0.0 END,
                           CASE WHEN c.cost_type = 'other' THEN c.cost ELSE 0.0 END
                      FROM costs c WHERE c.cost_type IS NOT NULL
                ),
                t AS (
                    SELECT u.*, u.egg_revenue + u.bird_revenue AS revenue,
                           u.feed_cost + u.medication_cost + u.mortality_cost + u.bird_cost + u.other_cost AS total_cost
                      FROM u
                )
                SELECT row_number() OVER () AS id, t.date, t.company_id, rc.currency_id, t.flock_lot_id,
                       t.farm_location_id, t.cage_location_id, t.production_date, t.eggs_sold, t.birds_sold,
                       t.egg_revenue, t.bird_revenue, t.revenue,
                       t.feed_cost, t.medication_cost, t.mortality_cost, t.bird_cost, t.other_cost, t.total_cost,
                       t.revenue - t.total_cost AS gross_profit,
                       CASE WHEN t.revenue <> 0 THEN (t.revenue - t.total_cost) / t.revenue * 100 ELSE 0 END
                           AS operating_margin_pct,
                       CASE WHEN SUM(t.revenue) OVER w > 0
                            THEN (SUM(t.revenue) OVER w - SUM(t.total_cost) OVER w) / SUM(t.revenue) OVER w * 100
                                 < COALESCE((SELECT cfg.low_margin_pct FROM farm_dashboard_config cfg
                                              WHERE cfg.company_id = t.company_id LIMIT 1), 30.0)
                            ELSE SUM(t.total_cost) OVER w > 0
                       END AS low_margin
                  FROM t
                  JOIN res_company rc ON rc.id = t.company_id
                WINDOW w AS (PARTITION BY t.flock_lot_id)
            )""")
