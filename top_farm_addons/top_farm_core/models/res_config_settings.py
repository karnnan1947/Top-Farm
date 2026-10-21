# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    farm_lot_generation_mode = fields.Selection(
        related='company_id.farm_lot_generation_mode',
        readonly=False,
    )
    farm_lot_date_source = fields.Selection(
        related='company_id.farm_lot_date_source',
        readonly=False,
    )
    farm_flock_auto_analytic = fields.Boolean(
        related='company_id.farm_flock_auto_analytic',
        readonly=False,
    )
    farm_flock_analytic_plan_id = fields.Many2one(
        related='company_id.farm_flock_analytic_plan_id',
        readonly=False,
    )
