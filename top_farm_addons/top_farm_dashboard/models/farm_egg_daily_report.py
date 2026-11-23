from odoo import fields, models, tools
from odoo.tools import SQL

# ratio measures: (numerator, denominator, factor). A subtotal is the ratio of the sums of its rows, never a sum or an
# average of the row ratios (list groups, pivot and the pivot's Excel download).
DAILY_RATIOS = {
    'hen_day_pct': ('total_eggs', 'live_bird_count', 100.0),
    'feed_per_bird_g': ('feed_kg', 'fed_bird_count', 1000.0),
    'fcr': ('feed_kg', 'fed_dozens', 1.0),
    'damaged_pct': ('eggs_damage', 'total_eggs', 100.0),
}


class FarmEggDailyReport(models.Model):
    _name = 'farm.egg.daily.report'
    _description = 'Daily Egg Production & Hen-Day %'
    _auto = False
    _order = 'date desc, flock_lot_id, cage_location_id'
    # SQL view: flush the collections before reading it
    _depends = {
        'farm.egg.collection': ['date', 'company_id', 'flock_lot_id', 'farm_location_id', 'cage_location_id',
                                'destination_location_id', 'qty_large', 'qty_medium', 'qty_jumbo', 'qty_damage',
                                'total_egg_qty', 'confirmed_live_bird_count', 'feed_consumed_qty', 'state'],
        'stock.lot': ['flock_stage', 'farm_arrival_date'],
    }

    date = fields.Date(string='Date', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    collection_id = fields.Many2one('farm.egg.collection', string='Egg Collection', readonly=True)
    flock_lot_id = fields.Many2one('stock.lot', string='Flock Batch', readonly=True)
    flock_stage = fields.Selection(
        selection=lambda self: self.env['stock.lot']._fields['flock_stage'].selection,
        string='Flock Stage', readonly=True)
    farm_location_id = fields.Many2one('stock.location', string='Farm Estate', readonly=True)
    cage_location_id = fields.Many2one('stock.location', string='Cage Location', readonly=True)
    destination_location_id = fields.Many2one('stock.location', string='Egg Collection Location', readonly=True)
    flock_age_weeks = fields.Float(
        string='Age (Weeks)', readonly=True, digits=(16, 1), aggregator='max',
        help="Age of the flock on the collection date, from its Chick Arrival Date.")
    live_bird_count = fields.Integer(
        string='Live Birds', readonly=True,
        help="Live birds of the flock in the cage when the eggs were produced (snapshot of the collection).")
    total_eggs = fields.Integer(string='Total Eggs', readonly=True)
    hen_day_pct = fields.Float(
        string='Hen-Day %', readonly=True, digits=(16, 2),
        help="Total eggs / live birds x 100. On a subtotal: the eggs of its rows over their live birds.")
    eggs_large = fields.Integer(string='Large', readonly=True)
    eggs_medium = fields.Integer(string='Medium', readonly=True)
    eggs_jumbo = fields.Integer(string='Jumbo', readonly=True)
    eggs_damage = fields.Integer(string='Damaged / Cracked', readonly=True)
    damaged_pct = fields.Float(string='Damaged %', readonly=True, digits=(16, 2),
                               help="Damaged / cracked eggs over the total eggs x 100.")
    dozens = fields.Float(string='Dozen Eggs', readonly=True, digits=(16, 2), help="Total eggs / 12.")
    feed_kg = fields.Float(string='Feed (kg)', readonly=True, digits=(16, 2),
                           help="Laying feed consumed by the cage for this collection.")
    fed_bird_count = fields.Integer(
        string='Fed Birds', readonly=True,
        help="Live birds of the rows that carry feed: the basis of the feed per bird.")
    fed_dozens = fields.Float(
        string='Fed Dozens', readonly=True, digits=(16, 2),
        help="Dozen eggs of the rows that carry feed: the basis of the FCR (pre-laying eggs carry no feed).")
    feed_per_bird_g = fields.Float(
        string='Feed (g/bird/day)', readonly=True, digits=(16, 1),
        help="Feed consumed x 1000 / live birds of the cages that were fed.")
    fcr = fields.Float(string='FCR (kg/dozen)', readonly=True, digits=(16, 3),
                       help="Feed consumed (kg) / dozen eggs.")

    def _read_group_select(self, table, aggregate_spec):
        name, __, func = aggregate_spec.partition(':')
        if name in DAILY_RATIOS and func == 'sum':
            num, den, factor = DAILY_RATIOS[name]
            return SQL("CASE WHEN SUM(%(den)s) = 0 THEN 0 ELSE SUM(%(num)s)::float / SUM(%(den)s) * %(factor)s END",
                       num=table[num], den=table[den], factor=factor)
        return super()._read_group_select(table, aggregate_spec)

    def init(self):
        """One row per produced egg collection (a cage on a day), with its live-bird snapshot, the eggs of each
        grade and the laying feed consumed: Top Farms' daily production sheet."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(SQL("""
            CREATE OR REPLACE VIEW %(table)s AS (
                SELECT ec.id, ec.id AS collection_id, ec.date, ec.company_id, ec.flock_lot_id, lot.flock_stage,
                       ec.farm_location_id, ec.cage_location_id, ec.destination_location_id,
                       CASE WHEN lot.farm_arrival_date IS NOT NULL
                            THEN GREATEST(ec.date - lot.farm_arrival_date, 0) / 7.0 END AS flock_age_weeks,
                       COALESCE(ec.confirmed_live_bird_count, 0) AS live_bird_count,
                       ec.total_egg_qty AS total_eggs,
                       CASE WHEN ec.confirmed_live_bird_count > 0
                            THEN ec.total_egg_qty::float / ec.confirmed_live_bird_count * 100 ELSE 0 END AS hen_day_pct,
                       COALESCE(ec.qty_large, 0) AS eggs_large,
                       COALESCE(ec.qty_medium, 0) AS eggs_medium,
                       COALESCE(ec.qty_jumbo, 0) AS eggs_jumbo,
                       COALESCE(ec.qty_damage, 0) AS eggs_damage,
                       CASE WHEN ec.total_egg_qty > 0
                            THEN COALESCE(ec.qty_damage, 0)::float / ec.total_egg_qty * 100 ELSE 0 END AS damaged_pct,
                       ec.total_egg_qty / 12.0 AS dozens,
                       COALESCE(ec.feed_consumed_qty, 0) AS feed_kg,
                       CASE WHEN COALESCE(ec.feed_consumed_qty, 0) > 0
                            THEN COALESCE(ec.confirmed_live_bird_count, 0) ELSE 0 END AS fed_bird_count,
                       CASE WHEN COALESCE(ec.feed_consumed_qty, 0) > 0
                            THEN ec.total_egg_qty / 12.0 ELSE 0 END AS fed_dozens,
                       CASE WHEN COALESCE(ec.feed_consumed_qty, 0) > 0 AND ec.confirmed_live_bird_count > 0
                            THEN ec.feed_consumed_qty * 1000.0 / ec.confirmed_live_bird_count ELSE 0 END
                           AS feed_per_bird_g,
                       CASE WHEN ec.total_egg_qty > 0
                            THEN COALESCE(ec.feed_consumed_qty, 0) / (ec.total_egg_qty / 12.0) ELSE 0 END AS fcr
                  FROM farm_egg_collection ec
                  JOIN stock_lot lot ON lot.id = ec.flock_lot_id
                 WHERE ec.state = 'done'
            )""", table=SQL.identifier(self._table)))
