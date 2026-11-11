# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from ..wizard.farm_broiler_harvest_wizard import LAYER_CULL_STAGES


class StockLocation(models.Model):
    _inherit = 'stock.location'

    farm_egg_location_id = fields.Many2one(
        'stock.location', string='Egg Collection Location', check_company=True,
        domain="[('usage', '=', 'internal'), ('farm_hierarchy_level', '=', False)]",
        help="Dedicated warehouse location where eggs produced from this cage are stored. Group the cage "
             "locations of a farm under one parent (e.g. Farm A / Egg Store / Cage A1) to read the stock per "
             "cage and per farm, and to transfer it to the dispatch warehouse.")

    @api.constrains('farm_egg_location_id')
    def _check_farm_egg_location(self):
        for location in self.filtered('farm_egg_location_id'):
            store = location.farm_egg_location_id
            if store.usage != 'internal' or store.farm_hierarchy_level:
                raise ValidationError(_(
                    "The Egg Collection Location of %(cage)s must be an internal storage location, not a farm "
                    "house (%(store)s).", cage=location.display_name, store=store.display_name))

    def action_open_cull_wizard(self):
        """Manager button on a cage: cull all or part of its hens into Layer Live Weight (kg)."""
        self.ensure_one()
        if self.farm_hierarchy_level != 'cage':
            raise UserError(_("Hens are culled from a cage, not from '%s'.", self.display_name))
        flocks = self._get_flock_lots().filtered(
            lambda lot: lot.flock_type == 'layer' and lot.flock_stage in LAYER_CULL_STAGES)
        if not flocks:
            raise UserError(_("%s holds no layer flock in the Laying or Spent stage to cull.", self.display_name))
        if len(flocks) > 1:
            raise UserError(_("%(cage)s holds several flocks (%(flocks)s): cull from the flock form.",
                              cage=self.display_name, flocks=", ".join(flocks.mapped('name'))))
        action = flocks.action_open_broiler_harvest_wizard()
        action['context'] = {**action['context'], 'default_location_id': self.id}
        return action
