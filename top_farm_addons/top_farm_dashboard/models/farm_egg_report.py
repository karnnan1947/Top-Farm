from odoo import fields, models, tools
from odoo.tools import SQL

GRADES = [('large', 'Large'), ('medium', 'Medium'), ('jumbo', 'Jumbo'), ('damage', 'Damaged / Cracked')]


class FarmEggReport(models.Model):
    _name = 'farm.egg.report'
    _description = 'Egg Production Analysis (by flock, cage and grade)'
    _auto = False
    _order = 'date desc, id'

    date = fields.Date(readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    flock_lot_id = fields.Many2one('stock.lot', string='Flock', readonly=True)
    farm_location_id = fields.Many2one('stock.location', string='Farm', readonly=True)
    cage_location_id = fields.Many2one('stock.location', string='Cage', readonly=True)
    grade = fields.Selection(GRADES, string='Egg Grade', readonly=True)
    product_id = fields.Many2one('product.product', string='Egg Product', readonly=True)
    eggs = fields.Integer(string='Eggs', readonly=True)
    dozens = fields.Float(string='Dozens', readonly=True, digits=(16, 2))
    bird_base = fields.Float(
        string='Birds (share)', readonly=True, digits=(16, 2),
        help="Live-bird snapshot of the collection, shared between the grades in proportion to their eggs, "
             "so that every subtotal divides by the birds exactly once.")
    feed_kg = fields.Float(
        string='Feed (kg)', readonly=True, digits=(16, 2),
        help="Feed consumed by the collection, shared between the grades in proportion to their eggs "
             "(the same split as the manufacturing orders).")
    hen_day_pct = fields.Float(string='Hen-Day (%)', readonly=True, digits=(16, 2),
                               help="Eggs / live birds x 100, as a ratio of the sums of the group.")
    fcr = fields.Float(string='FCR (kg/dozen)', readonly=True, digits=(16, 3),
                       help="Feed kg / dozens of eggs, as a ratio of the sums of the group.")

    def _read_group_select(self, table, aggregate_spec):
        # ratios of sums, never a sum or an average of row percentages
        if aggregate_spec == 'hen_day_pct:sum':
            return SQL("CASE WHEN SUM(%(base)s) = 0 THEN 0 ELSE SUM(%(eggs)s)::float / SUM(%(base)s) * 100 END",
                       eggs=table['eggs'], base=table['bird_base'])
        if aggregate_spec == 'fcr:sum':
            return SQL("CASE WHEN SUM(%(dz)s) = 0 THEN 0 ELSE SUM(%(feed)s)::float / SUM(%(dz)s) END",
                       feed=table['feed_kg'], dz=table['dozens'])
        return super()._read_group_select(table, aggregate_spec)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT ec.id * 10 + g.n AS id, ec.date, ec.company_id, ec.flock_lot_id, ec.farm_location_id,
                       ec.cage_location_id, g.grade,
                       CASE g.grade WHEN 'large' THEN ec.product_large_id WHEN 'medium' THEN ec.product_medium_id
                                    WHEN 'jumbo' THEN ec.product_jumbo_id ELSE ec.product_damage_id END AS product_id,
                       g.qty AS eggs,
                       g.qty / 12.0 AS dozens,
                       ec.confirmed_live_bird_count::float * g.qty / ec.total_egg_qty AS bird_base,
                       ec.feed_consumed_qty::float * g.qty / ec.total_egg_qty AS feed_kg,
                       CASE WHEN ec.confirmed_live_bird_count > 0
                            THEN g.qty::float / (ec.confirmed_live_bird_count::float * g.qty / ec.total_egg_qty) * 100
                            ELSE 0 END AS hen_day_pct,
                       CASE WHEN g.qty > 0
                            THEN (ec.feed_consumed_qty::float * g.qty / ec.total_egg_qty) / (g.qty / 12.0)
                            ELSE 0 END AS fcr
                  FROM farm_egg_collection ec
                 CROSS JOIN LATERAL (VALUES (1, 'large', ec.qty_large), (2, 'medium', ec.qty_medium),
                                            (3, 'jumbo', ec.qty_jumbo), (4, 'damage', ec.qty_damage)) AS g(n, grade, qty)
                 WHERE ec.state = 'done' AND ec.total_egg_qty > 0 AND g.qty > 0
            )""")
