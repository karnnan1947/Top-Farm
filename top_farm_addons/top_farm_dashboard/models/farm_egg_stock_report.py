# -*- coding: utf-8 -*-
from odoo import fields, models, tools

GRADES = [
    ('large', 'Large'),
    ('medium', 'Medium'),
    ('jumbo', 'Jumbo'),
    ('damage', 'Damaged / Cracked'),
    ('other', 'Other'),
]


class FarmEggStockReport(models.Model):
    _name = 'farm.egg.stock.report'
    _description = 'Egg Stock & On-Hand Inventory Analysis'
    _auto = False
    _order = 'location_id, product_id'

    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)
    location_id = fields.Many2one(
        'stock.location', string='Egg Storage Location', readonly=True,
        help="Physical warehouse storage location holding the eggs (e.g. WH/Stock/Eggs/Cage A1 Eggs).")
    cage_location_id = fields.Many2one(
        'stock.location', string='Source Cage', readonly=True,
        help="Cage whose hens laid these eggs.")
    farm_location_id = fields.Many2one(
        'stock.location', string='Farm Estate', readonly=True,
        help="Farm Estate the eggs belong to.")
    flock_lot_id = fields.Many2one(
        'stock.lot', string='Flock Batch', readonly=True,
        help="Parent Flock Batch that produced the eggs.")
    lot_id = fields.Many2one(
        'stock.lot', string='Egg Lot / Batch', readonly=True)
    product_id = fields.Many2one(
        'product.product', string='Egg Product', readonly=True)
    grade = fields.Selection(GRADES, string='Egg Grade', readonly=True)
    on_hand_qty = fields.Float(
        string='On Hand Quantity', readonly=True, digits=(16, 2),
        help="Real-time physical quantity currently in stock in this location.")
    dozens = fields.Float(
        string='Dozens', readonly=True, digits=(16, 2))
    value = fields.Monetary(
        string='Inventory Valuation', currency_field='currency_id', readonly=True,
        help="Total asset inventory value of the eggs currently on hand.")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT row_number() OVER () AS id,
                       q.company_id,
                       rc.currency_id,
                       q.location_id,
                       cage.id AS cage_location_id,
                       COALESCE(cage.parent_farm_location_id, flock.farm_location_id, sl.parent_farm_location_id) AS farm_location_id,
                       COALESCE(flock.id, CASE WHEN elot.is_flock_batch THEN elot.id END) AS flock_lot_id,
                       q.lot_id,
                       q.product_id,
                       CASE 
                         WHEN pp.id = rc.farm_egg_large_product_id OR pp.default_code = 'EGG-LRG' OR COALESCE(pt.name->>'en_US', pt.name::text) ILIKE '%Large%' THEN 'large'
                         WHEN pp.id = rc.farm_egg_medium_product_id OR pp.default_code = 'EGG-MED' OR COALESCE(pt.name->>'en_US', pt.name::text) ILIKE '%Medium%' THEN 'medium'
                         WHEN pp.id = rc.farm_egg_jumbo_product_id OR pp.default_code = 'EGG-JMB' OR COALESCE(pt.name->>'en_US', pt.name::text) ILIKE '%Jumbo%' THEN 'jumbo'
                         WHEN pp.id = rc.farm_egg_damage_product_id OR pp.default_code = 'EGG-DMG' OR COALESCE(pt.name->>'en_US', pt.name::text) ILIKE '%Damage%' OR COALESCE(pt.name->>'en_US', pt.name::text) ILIKE '%Crack%' THEN 'damage'
                         ELSE 'other'
                       END AS grade,
                       q.quantity AS on_hand_qty,
                       q.quantity / 12.0 AS dozens,
                       COALESCE(q.value, 0.0) AS value
                  FROM stock_quant q
                  JOIN stock_location sl ON sl.id = q.location_id AND sl.usage = 'internal'
                  JOIN product_product pp ON pp.id = q.product_id
                  JOIN product_template pt ON pt.id = pp.product_tmpl_id
                  JOIN res_company rc ON rc.id = q.company_id
                  LEFT JOIN stock_lot elot ON elot.id = q.lot_id
                  LEFT JOIN stock_lot flock ON flock.id = elot.farm_flock_lot_id
                  LEFT JOIN stock_location cage ON cage.farm_egg_location_id = q.location_id
                 WHERE q.quantity > 0
                   AND (pp.id IN (rc.farm_egg_large_product_id, rc.farm_egg_medium_product_id, rc.farm_egg_jumbo_product_id, rc.farm_egg_damage_product_id)
                        OR pp.default_code IN ('EGG-LRG', 'EGG-MED', 'EGG-JMB', 'EGG-DMG')
                        OR (COALESCE(pt.name->>'en_US', pt.name::text) ILIKE '%Egg%' 
                            AND COALESCE(pt.name->>'en_US', pt.name::text) NOT ILIKE '%Tray%' 
                            AND COALESCE(pt.name->>'en_US', pt.name::text) NOT ILIKE '%Carton%' 
                            AND COALESCE(pt.name->>'en_US', pt.name::text) NOT ILIKE '%Box%'))
            )
        """)
