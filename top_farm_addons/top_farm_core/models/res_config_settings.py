# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    laying_transition_mode = fields.Selection(
        related='company_id.laying_transition_mode',
        readonly=False,
    )
    laying_start_age_weeks = fields.Float(
        related='company_id.laying_start_age_weeks',
        readonly=False,
    )
    laying_notification_advance_weeks = fields.Float(
        related='company_id.laying_notification_advance_weeks',
        readonly=False,
    )
