# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    laying_transition_mode = fields.Selection([
        ('manual', 'Manual (Manager Button Only)'),
        ('automatic', 'Automatic by Flock Age'),
    ], string='Laying Transition Mode', default='manual', required=True,
       help="Manual: a Farm Manager must click 'Start Laying Phase'.\n"
            "Automatic: the daily check starts the Laying Phase when the flock reaches the target age. "
            "The button stays available in both modes for an early start.")

    laying_start_age_weeks = fields.Float(
        string='Laying Phase Start Age (Weeks)',
        default=19.0,
        digits=(16, 1),
        help="Target age in weeks when flock is considered entering commercial egg production."
    )

    laying_notification_advance_weeks = fields.Float(
        string='Advance Warning (Weeks Before Laying)',
        default=1.0,
        digits=(16, 1),
        help="Number of weeks before the laying start age to send the point-of-lay inspection alert "
             "to the Farm Managers."
    )

    @api.constrains('laying_start_age_weeks', 'laying_notification_advance_weeks')
    def _check_laying_ages(self):
        for company in self:
            if company.laying_start_age_weeks <= 0:
                raise ValidationError(_("The Laying Phase start age must be greater than 0 weeks."))
            if not 0 <= company.laying_notification_advance_weeks < company.laying_start_age_weeks:
                raise ValidationError(_(
                    "The advance warning must be at least 0 weeks and less than the Laying Phase start age."))
