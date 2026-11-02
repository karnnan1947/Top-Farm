# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

FLOCK_TYPES = [
    ('layer', 'Layer'),
    ('broiler', 'Broiler'),
]


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_farm_bird = fields.Boolean(
        string='Is Live Farm Bird',
        default=False,
        index=True,
        help="Check this box if the product represents live poultry, layers or broilers (Day-Old Chicks or Adult "
             "Birds). Birds are tracked by lots: the hatchery lot on receipt, then the flock lot."
    )
    farm_flock_type = fields.Selection(
        FLOCK_TYPES, string='Bird Type', default='layer', required=True,
        help="Layer: a 2 to 2.5-year egg-laying flock (brooding nursery, then cages).\n"
             "Broiler: a 35 to 45-day meat batch reared in one broiler shed; its feed, medication and mortality "
             "stay capitalized in the batch until the harvest converts the birds into meat by weight.")

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

    def write(self, vals):
        # The flock lots of a bird product follow its type (layer flock or broiler batch): it cannot change once
        # flocks exist.
        if 'farm_flock_type' in vals:
            changed = self.filtered(lambda t: t.farm_flock_type != vals['farm_flock_type'])
            flocks = self.env['stock.lot'].sudo().search(
                [('product_id.product_tmpl_id', 'in', changed.ids), ('is_flock_batch', '=', True)], limit=5)
            if flocks:
                raise UserError(_("%(product)s already has flock lots (%(lots)s): its bird type cannot be changed.",
                                  product=flocks.product_id[:1].display_name, lots=", ".join(flocks.mapped('name'))))
        return super().write(vals)
