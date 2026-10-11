from odoo import fields, models, tools
from odoo.tools import SQL


class FarmMortalityBI(models.Model):
    _name = 'farm.mortality.bi'
    _description = 'Mortality Analysis (ratio-correct)'
    _auto = False
    _order = 'date desc, id'

    date = fields.Date(readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    batch_location_id = fields.Many2one('stock.location', string='Flock Batch', readonly=True)
    cage_location_id = fields.Many2one('stock.location', string='Cage', readonly=True)
    bird_product_id = fields.Many2one('product.product', string='Bird Product', readonly=True)
    cause_of_death = fields.Selection(
        selection=lambda self: self.env['farm.mortality.log']._fields['cause_of_death'].selection,
        string='Cause of Death', readonly=True)
    dead_bird_count = fields.Integer(string='Dead Birds', readonly=True)
    population_base = fields.Integer(
        string='Population Base', readonly=True,
        help="Opening population of the cage-day, counted once however many logs the cage had that day.")
    mortality_pct = fields.Float(string='Mortality (%)', readonly=True, digits=(16, 3))

    def _read_group_select(self, table, aggregate_spec):
        # dead / population of the group, never a sum or average of percentages
        if aggregate_spec == 'mortality_pct:sum':
            return SQL("CASE WHEN SUM(%(base)s) = 0 THEN 0 ELSE SUM(%(dead)s)::float / SUM(%(base)s) * 100 END",
                       dead=table['dead_bird_count'], base=table['population_base'])
        return super()._read_group_select(table, aggregate_spec)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT m.id, m.date, m.company_id, m.batch_location_id, m.cage_location_id, m.bird_product_id,
                       m.cause_of_death, m.dead_bird_count,
                       CASE WHEN ROW_NUMBER() OVER (PARTITION BY m.cage_location_id, m.date ORDER BY m.id) = 1
                            THEN m.opening_population ELSE 0 END AS population_base,
                       CASE WHEN m.opening_population > 0
                            THEN m.dead_bird_count::float / m.opening_population * 100 ELSE 0 END AS mortality_pct
                  FROM farm_mortality_log m
                 WHERE m.state = 'done'
            )""")
