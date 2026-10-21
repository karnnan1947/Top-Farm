from odoo import fields, models, tools
from odoo.tools import SQL


class FarmMortalityBI(models.Model):
    _name = 'farm.mortality.bi'
    _description = 'Mortality Analysis (ratio-correct)'
    _auto = False
    _order = 'date desc, id'
    # SQL view: flush these before reading it (e.g. the dashboard right after a log is submitted)
    _depends = {
        'farm.mortality.log': ['date', 'company_id', 'farm_location_id', 'location_id', 'lot_id', 'bird_product_id',
                               'cause_of_death', 'dead_bird_count', 'opening_population', 'state'],
    }

    date = fields.Date(readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    flock_lot_id = fields.Many2one('stock.lot', string='Flock', readonly=True)
    farm_location_id = fields.Many2one('stock.location', string='Farm', readonly=True)
    location_id = fields.Many2one('stock.location', string='Brooding / Cage', readonly=True)
    house_type = fields.Selection(
        [('brooding', 'Brooding Nursery'), ('cage', 'Cage')], string='House Type', readonly=True)
    bird_product_id = fields.Many2one('product.product', string='Bird Product', readonly=True)
    cause_of_death = fields.Selection(
        selection=lambda self: self.env['farm.mortality.log']._fields['cause_of_death'].selection,
        string='Cause of Death', readonly=True)
    dead_bird_count = fields.Integer(string='Dead Birds', readonly=True)
    population_base = fields.Integer(
        string='Population Base', readonly=True,
        help="Opening population of the flock-day in the location, counted once however many logs it had that day.")
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
                SELECT m.id, m.date, m.company_id, m.lot_id AS flock_lot_id, m.farm_location_id, m.location_id,
                       loc.farm_hierarchy_level AS house_type, m.bird_product_id, m.cause_of_death, m.dead_bird_count,
                       CASE WHEN ROW_NUMBER() OVER (PARTITION BY m.location_id, m.lot_id, m.date ORDER BY m.id) = 1
                            THEN m.opening_population ELSE 0 END AS population_base,
                       CASE WHEN m.opening_population > 0
                            THEN m.dead_bird_count::float / m.opening_population * 100 ELSE 0 END AS mortality_pct
                  FROM farm_mortality_log m
                  JOIN stock_location loc ON loc.id = m.location_id
                 WHERE m.state = 'done'
            )""")
