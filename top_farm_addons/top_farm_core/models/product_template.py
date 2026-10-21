# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_farm_bird = fields.Boolean(
        string='Is Live Farm Bird',
        default=False,
        index=True,
        help="Check this box if the product represents live poultry layers (Day-Old Chicks or Adult Birds). "
             "Birds are tracked by lots: the hatchery lot on receipt, then the flock lot."
    )

    @api.onchange('is_farm_bird')
    def _onchange_is_farm_bird(self):
        if self.is_farm_bird:
            self.is_storable = True
            self.tracking = 'lot'

    @api.constrains('is_farm_bird', 'is_storable', 'tracking')
    def _check_farm_bird_tracking(self):
        for template in self:
            if template.is_farm_bird and (not template.is_storable or template.tracking != 'lot'):
                raise ValidationError(_(
                    "Live farm bird products must be tracked in inventory by lots: flocks are lots. "
                    "Check 'Track Inventory' with 'By Lots' on %s.", template.display_name))
