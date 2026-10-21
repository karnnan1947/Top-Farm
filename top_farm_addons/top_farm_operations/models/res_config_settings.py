# -*- coding: utf-8 -*-
from odoo import fields, models

EGG_PRODUCT_DOMAIN = "[('type', '=', 'consu'), ('company_id', 'in', [company_id, False])]"


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    farm_feed_consumption_location_id = fields.Many2one(
        related='company_id.farm_feed_consumption_location_id', readonly=False,
        domain="[('usage', '=', 'inventory'), ('company_id', 'in', [company_id, False])]")
    farm_medication_consumption_location_id = fields.Many2one(
        related='company_id.farm_medication_consumption_location_id', readonly=False,
        domain="[('usage', '=', 'inventory'), ('company_id', 'in', [company_id, False])]")
    farm_egg_location_id = fields.Many2one(
        related='company_id.farm_egg_location_id', readonly=False,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [company_id, False])]")
    farm_egg_medium_product_id = fields.Many2one(
        related='company_id.farm_egg_medium_product_id', readonly=False, domain=EGG_PRODUCT_DOMAIN)
    farm_egg_large_product_id = fields.Many2one(
        related='company_id.farm_egg_large_product_id', readonly=False, domain=EGG_PRODUCT_DOMAIN)
    farm_egg_jumbo_product_id = fields.Many2one(
        related='company_id.farm_egg_jumbo_product_id', readonly=False, domain=EGG_PRODUCT_DOMAIN)
    farm_egg_damage_product_id = fields.Many2one(
        related='company_id.farm_egg_damage_product_id', readonly=False, domain=EGG_PRODUCT_DOMAIN)
    laying_transition_mode = fields.Selection(related='company_id.laying_transition_mode', readonly=False)
    laying_min_age_weeks = fields.Float(related='company_id.laying_min_age_weeks', readonly=False)
    laying_hen_day_threshold_pct = fields.Float(related='company_id.laying_hen_day_threshold_pct', readonly=False)
    laying_rolling_days = fields.Integer(related='company_id.laying_rolling_days', readonly=False)
