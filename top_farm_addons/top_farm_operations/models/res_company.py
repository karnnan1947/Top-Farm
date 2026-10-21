# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    farm_feed_consumption_location_id = fields.Many2one(
        'stock.location', string='Feed Consumption Location',
        domain="[('usage', '=', 'inventory')]",
        help="Virtual location that receives expensed feed (brooding and pre-laying feed, unharvested laying feed). "
             "Give it a valuation account (e.g. Feed Expense) to post the cost to the ledger.")
    farm_medication_consumption_location_id = fields.Many2one(
        'stock.location', string='Medication Consumption Location',
        domain="[('usage', '=', 'inventory')]",
        help="Virtual location that receives administered medication and vaccines.")
    farm_egg_location_id = fields.Many2one(
        'stock.location', string='Egg Store Location',
        domain="[('usage', '=', 'internal')]",
        help="Default cold-room location for graded eggs. A farm can override it.")
    farm_egg_medium_product_id = fields.Many2one('product.product', string='Medium Egg Product')
    farm_egg_large_product_id = fields.Many2one('product.product', string='Large Egg Product')
    farm_egg_jumbo_product_id = fields.Many2one('product.product', string='Jumbo Egg Product')
    farm_egg_damage_product_id = fields.Many2one('product.product', string='Damaged / Cracked Egg Product')

    laying_transition_mode = fields.Selection([
        ('manual', 'Alert the Farm Managers, a manager confirms'),
        ('automatic', 'Start the Laying Phase automatically'),
    ], string='Laying Transition Mode', default='manual', required=True,
       help="What happens when a rearing flock sustains the hen-day benchmark. The Start Laying Phase button "
            "stays available to the Farm Managers in both modes.")
    laying_min_age_weeks = fields.Float(
        string='Minimum Laying Age (Weeks)', default=17.0, digits=(16, 1),
        help="The hen-day benchmark is only checked once the flock is at least this old.")
    laying_hen_day_threshold_pct = fields.Float(
        string='Laying Hen-Day Benchmark (%)', default=50.0, digits=(16, 1),
        help="Rolling hen-day rate (eggs / live bird days) a flock must reach to enter the Laying Phase.")
    laying_rolling_days = fields.Integer(
        string='Rolling Window (Days)', default=7,
        help="Number of days the hen-day rate is averaged over, so that the benchmark must be sustained.")

    @api.constrains('laying_min_age_weeks', 'laying_hen_day_threshold_pct', 'laying_rolling_days')
    def _check_laying_benchmark(self):
        for company in self:
            if company.laying_min_age_weeks < 0:
                raise ValidationError(_("The minimum laying age cannot be negative."))
            if not 0 < company.laying_hen_day_threshold_pct <= 100:
                raise ValidationError(_("The laying hen-day benchmark must be between 0 and 100 %."))
            if company.laying_rolling_days < 1:
                raise ValidationError(_("The rolling window must be at least one day."))
