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
    collection_id = fields.Many2one('farm.egg.collection', string='Egg Collection', readonly=True)
    flock_lot_id = fields.Many2one('stock.lot', string='Flock', readonly=True)
    farm_location_id = fields.Many2one('stock.location', string='Farm', readonly=True)
    cage_location_id = fields.Many2one('stock.location', string='Cage', readonly=True)
    destination_location_id = fields.Many2one(
        'stock.location', string='Egg Collection Location', readonly=True,
        help="Warehouse location the eggs were produced into: the Egg Collection Location of the cage.")
    grade = fields.Selection(GRADES, string='Egg Grade', readonly=True)
    product_id = fields.Many2one('product.product', string='Egg Product', readonly=True)
    eggs = fields.Integer(string='Eggs', readonly=True)
    live_bird_count = fields.Integer(
        string='Live Birds', readonly=True,
        help="Live birds of the flock in the cage when the eggs were produced (snapshot of the collection). "
             "A subtotal counts the birds of each collection once, whatever grades it shows.")
    collection_egg_qty = fields.Integer(
        string='Collection Total Eggs', readonly=True,
        help="All the eggs of the collection, every grade. A subtotal counts each collection once.")
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
    on_hand_qty = fields.Float(
        string='On Hand Quantity', readonly=True, digits=(16, 2),
        help="Current real-time physical quantity of eggs on hand in this egg location.")

    def _read_group_select(self, table, aggregate_spec):
        # ratios of sums, never a sum or an average of row percentages
        if aggregate_spec == 'hen_day_pct:sum':
            return SQL("CASE WHEN SUM(%(base)s) = 0 THEN 0 ELSE SUM(%(eggs)s)::float / SUM(%(base)s) * 100 END",
                       eggs=table['eggs'], base=table['bird_base'])
        if aggregate_spec in ('live_bird_count:sum', 'collection_egg_qty:sum'):
            # once per collection of the group (its grade rows repeat the collection's figure)
            column = 'confirmed_live_bird_count' if aggregate_spec.startswith('live') else 'total_egg_qty'
            return SQL("(SELECT COALESCE(SUM(c.%(column)s), 0) FROM farm_egg_collection c "
                       "WHERE c.id = ANY(ARRAY_AGG(DISTINCT %(collection)s)))",
                       column=SQL.identifier(column), collection=table['collection_id'])
        if aggregate_spec == 'fcr:sum':
            return SQL("CASE WHEN SUM(%(dz)s) = 0 THEN 0 ELSE SUM(%(feed)s)::float / SUM(%(dz)s) END",
                       feed=table['feed_kg'], dz=table['dozens'])
        return super()._read_group_select(table, aggregate_spec)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT ec.id * 10 + g.n AS id, ec.id AS collection_id, ec.date, ec.company_id, ec.flock_lot_id,
                       ec.farm_location_id,
                       ec.cage_location_id, ec.destination_location_id, g.grade,
                       CASE g.grade WHEN 'large' THEN ec.product_large_id WHEN 'medium' THEN ec.product_medium_id
                                    WHEN 'jumbo' THEN ec.product_jumbo_id ELSE ec.product_damage_id END AS product_id,
                       g.qty AS eggs,
                       COALESCE(ec.confirmed_live_bird_count, 0) AS live_bird_count,
                       ec.total_egg_qty AS collection_egg_qty,
                       g.qty / 12.0 AS dozens,
                       ec.confirmed_live_bird_count::float * g.qty / ec.total_egg_qty AS bird_base,
                       ec.feed_consumed_qty::float * g.qty / ec.total_egg_qty AS feed_kg,
                       CASE WHEN ec.confirmed_live_bird_count > 0
                            THEN g.qty::float / (ec.confirmed_live_bird_count::float * g.qty / ec.total_egg_qty) * 100
                            ELSE 0 END AS hen_day_pct,
                       CASE WHEN g.qty > 0
                            THEN (ec.feed_consumed_qty::float * g.qty / ec.total_egg_qty) / (g.qty / 12.0)
                            ELSE 0 END AS fcr,
                       COALESCE((
                           SELECT SUM(q.quantity)
                             FROM stock_quant q
                             JOIN stock_location sl ON sl.id = q.location_id AND sl.usage = 'internal'
                             JOIN mrp_production mo ON mo.farm_collection_id = ec.id AND mo.product_id = (
                                 CASE g.grade WHEN 'large' THEN ec.product_large_id 
                                              WHEN 'medium' THEN ec.product_medium_id 
                                              WHEN 'jumbo' THEN ec.product_jumbo_id 
                                              ELSE ec.product_damage_id END
                             )
                             JOIN mrp_production_stock_lot_rel rel ON rel.mrp_production_id = mo.id
                            WHERE q.lot_id = rel.stock_lot_id
                              AND q.location_id = ec.destination_location_id
                              AND q.quantity > 0
                       ), 0.0) AS on_hand_qty
                  FROM farm_egg_collection ec
                 CROSS JOIN LATERAL (VALUES (1, 'large', ec.qty_large), (2, 'medium', ec.qty_medium),
                                            (3, 'jumbo', ec.qty_jumbo), (4, 'damage', ec.qty_damage)) AS g(n, grade, qty)
                 WHERE ec.state = 'done' AND ec.total_egg_qty > 0 AND g.qty > 0
            )""")
