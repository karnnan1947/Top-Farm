from odoo import fields, models, tools

from .report_sql import REVENUE_CTES


class FarmRevenueAllocation(models.Model):
    _name = 'farm.revenue.allocation'
    _description = 'Flock Revenue Allocation (eggs to cages, spent hens to the flock)'
    _auto = False
    _order = 'date desc, id'

    date = fields.Date(string='Invoice Date', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)
    flock_lot_id = fields.Many2one('stock.lot', string='Flock', readonly=True)
    farm_location_id = fields.Many2one('stock.location', string='Farm', readonly=True)
    cage_location_id = fields.Many2one('stock.location', string='Cage', readonly=True)
    production_date = fields.Date(string='Egg Production Date', readonly=True)
    grade = fields.Selection([('medium', 'Medium'), ('large', 'Large'), ('jumbo', 'Jumbo'),
                              ('damage', 'Damaged / Cracked'), ('spent_hen', 'Spent Hens')],
                             string='Egg Grade / Birds', readonly=True)
    product_id = fields.Many2one('product.product', readonly=True)
    eggs_sold = fields.Float(string='Eggs Sold', readonly=True, digits=(16, 2))
    birds_sold = fields.Float(string='Birds Sold', readonly=True, digits=(16, 2))
    revenue = fields.Monetary(string='Allocated Revenue', currency_field='currency_id', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                WITH {REVENUE_CTES}
                SELECT row_number() OVER () AS id, rev.date, rev.company_id, rc.currency_id,
                       rev.flock_lot_id, rev.farm_location_id, rev.cage_location_id, rev.production_date,
                       rev.grade, rev.product_id, rev.eggs_sold, rev.birds_sold, rev.revenue
                  FROM rev JOIN res_company rc ON rc.id = rev.company_id
            )""")
