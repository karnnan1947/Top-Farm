from odoo import fields, models, tools
from odoo.tools import SQL

from .report_sql import REVENUE_CTES, cost_ctes


class FarmProfitabilityReport(models.Model):
    _name = 'farm.profitability.report'
    _description = 'Cage & Batch Profitability'
    _auto = False
    _order = 'date desc, id'

    date = fields.Date(readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)
    batch_location_id = fields.Many2one('stock.location', string='Flock Batch', readonly=True)
    cage_location_id = fields.Many2one('stock.location', string='Cage', readonly=True)
    production_date = fields.Date(string='Egg Production Date', readonly=True)
    eggs_sold = fields.Float(string='Eggs Sold', readonly=True, digits=(16, 2))
    revenue = fields.Monetary(string='Egg Revenue', currency_field='currency_id', readonly=True)
    feed_cost = fields.Monetary(string='Feed Cost', currency_field='currency_id', readonly=True)
    medication_cost = fields.Monetary(string='Medication Cost', currency_field='currency_id', readonly=True)
    mortality_cost = fields.Monetary(string='Mortality Loss', currency_field='currency_id', readonly=True)
    total_cost = fields.Monetary(string='Total Direct Cost', currency_field='currency_id', readonly=True)
    gross_profit = fields.Monetary(string='Gross Operating Profit', currency_field='currency_id', readonly=True)
    operating_margin_pct = fields.Float(string='Operating Margin (%)', readonly=True, digits=(16, 2))
    low_margin = fields.Boolean(
        string='Low Margin Cage', readonly=True,
        help="The cage's overall margin (all dates) is below the Low Margin Warning of the Dashboard Settings, "
             "or the cage has costs and no revenue.")

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
                WITH {REVENUE_CTES}, {cost_ctes(self.env)}
                SELECT row_number() OVER () AS id, u.date, u.company_id, rc.currency_id, u.batch_location_id,
                       u.cage_location_id, u.production_date, u.eggs_sold, u.revenue, u.feed_cost,
                       u.medication_cost, u.mortality_cost,
                       u.feed_cost + u.medication_cost + u.mortality_cost AS total_cost,
                       u.revenue - (u.feed_cost + u.medication_cost + u.mortality_cost) AS gross_profit,
                       CASE WHEN u.revenue <> 0
                            THEN (u.revenue - (u.feed_cost + u.medication_cost + u.mortality_cost)) / u.revenue * 100
                            ELSE 0 END AS operating_margin_pct,
                       CASE WHEN SUM(u.revenue) OVER w > 0
                            THEN (SUM(u.revenue) OVER w
                                  - SUM(u.feed_cost + u.medication_cost + u.mortality_cost) OVER w)
                                 / SUM(u.revenue) OVER w * 100
                                 < COALESCE((SELECT cfg.low_margin_pct FROM farm_dashboard_config cfg
                                              WHERE cfg.company_id = u.company_id LIMIT 1), 30.0)
                            ELSE SUM(u.feed_cost + u.medication_cost + u.mortality_cost) OVER w > 0
                       END AS low_margin
                  FROM (
                        SELECT rev.date, rev.company_id, rev.batch_location_id, rev.cage_location_id,
                               rev.production_date, rev.eggs_sold, rev.revenue,
                               0.0 AS feed_cost, 0.0 AS medication_cost, 0.0 AS mortality_cost
                          FROM rev
                        UNION ALL
                        SELECT c.date, c.company_id, c.batch_location_id, c.cage_location_id,
                               NULL::date, 0.0, 0.0,
                               CASE WHEN c.cost_type = 'feed' THEN c.cost ELSE 0.0 END,
                               CASE WHEN c.cost_type = 'medication' THEN c.cost ELSE 0.0 END,
                               CASE WHEN c.cost_type = 'mortality' THEN c.cost ELSE 0.0 END
                          FROM costs c WHERE c.cost_type IS NOT NULL
                  ) u
                  JOIN res_company rc ON rc.id = u.company_id
                WINDOW w AS (PARTITION BY u.cage_location_id)
            )""")
