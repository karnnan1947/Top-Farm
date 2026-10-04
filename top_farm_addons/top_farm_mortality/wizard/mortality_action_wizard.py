from odoo import _, fields, models
from odoo.exceptions import UserError


class FarmMortalityActionWizard(models.TransientModel):
    _name = 'farm.mortality.action.wizard'
    _description = 'Reject / Reverse Mortality Log (reason required)'

    log_id = fields.Many2one('farm.mortality.log', required=True, ondelete='cascade')
    action = fields.Selection([('reject', 'Reject'), ('reverse', 'Reverse')], required=True)
    reason = fields.Text(string='Reason', required=True)

    def action_confirm(self):
        self.ensure_one()
        if not (self.reason or '').strip():
            raise UserError(_("A reason is required."))
        if self.action == 'reject':
            self.log_id._do_reject(self.reason)
        else:
            self.log_id._do_reverse(self.reason)
        return {'type': 'ir.actions.act_window_close'}
