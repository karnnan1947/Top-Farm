from odoo import fields, models, tools
from odoo.tools import SQL


class FarmFeedReport(models.Model):
    _name = 'farm.feed.report'
    _description = 'Feed Consumption Analysis (by flock, brooding nursery and cage)'
    _auto = False
    _order = 'date desc, id'

    date = fields.Date(readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    flock_lot_id = fields.Many2one('stock.lot', string='Flock', readonly=True)
    farm_location_id = fields.Many2one('stock.location', string='Farm', readonly=True)
    location_id = fields.Many2one('stock.location', string='Brooding / Cage', readonly=True)
    house_type = fields.Selection(
        [('brooding', 'Brooding Nursery'), ('cage', 'Cage')], string='House Type', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    input_type = fields.Selection(
        [('feed', 'Feed'), ('medication', 'Medication / Vaccine')], string='Type', readonly=True)
    consumption = fields.Selection(
        [('egg_mo', 'Egg production (laying feed)'),
         ('direct', 'Direct expense (brooding, pre-laying, medication, unharvested)')],
        string='Consumed Through', readonly=True)
    uom_id = fields.Many2one('uom.uom', string='Unit', readonly=True)
    quantity = fields.Float(string='Quantity', readonly=True, digits=(16, 2))
    cost = fields.Float(string='Cost', readonly=True, digits=(16, 2))
    cost_per_unit = fields.Float(string='Cost per Unit', readonly=True, digits=(16, 4))

    def _read_group_select(self, table, aggregate_spec):
        # cost / quantity of the group, never a sum or an average of row prices
        if aggregate_spec == 'cost_per_unit:sum':
            return SQL("CASE WHEN SUM(%(qty)s) = 0 THEN 0 ELSE SUM(%(cost)s)::float / SUM(%(qty)s) END",
                       cost=table['cost'], qty=table['quantity'])
        return super()._read_group_select(table, aggregate_spec)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT sm.id, sm.date::date AS date, sm.company_id, sm.farm_flock_lot_id AS flock_lot_id,
                       house.parent_farm_location_id AS farm_location_id,
                       sm.farm_location_id AS location_id, house.farm_hierarchy_level AS house_type,
                       sm.product_id, pt.farm_input_type AS input_type,
                       CASE WHEN sm.raw_material_production_id IS NOT NULL THEN 'egg_mo' ELSE 'direct' END AS consumption,
                       pt.uom_id, sm.product_qty AS quantity,
                       -COALESCE(sm.value, 0) AS cost,
                       CASE WHEN sm.product_qty > 0 THEN -COALESCE(sm.value, 0) / sm.product_qty ELSE 0 END AS cost_per_unit
                  FROM stock_move sm
                  JOIN product_product pp ON pp.id = sm.product_id
                  JOIN product_template pt ON pt.id = pp.product_tmpl_id
                  JOIN stock_location house ON house.id = sm.farm_location_id
                 WHERE sm.state = 'done' AND pt.farm_input_type IS NOT NULL
            )""")
