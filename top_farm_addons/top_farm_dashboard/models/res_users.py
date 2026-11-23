from odoo import api, fields, models

LAYER_GROUP = 'top_farm_dashboard.group_farm_layer_dashboard'
BROILER_GROUP = 'top_farm_dashboard.group_farm_broiler_dashboard'


class ResUsers(models.Model):
    _inherit = 'res.users'

    # Read from the user's groups each time (not stored): a stored copy could go stale when the groups are changed
    # elsewhere (Access Rights, group form, data files).
    enable_flock_dashboard = fields.Boolean(
        string='Flock / Layer Dashboard', compute='_compute_farm_dashboard_access',
        inverse='_inverse_flock_dashboard', search='_search_flock_dashboard',
        help="The user sees the Layer Performance Dashboard and the layer reports (daily egg production, egg "
             "production analysis, egg stock analysis, pre-laying flock investment).")
    enable_broiler_dashboard = fields.Boolean(
        string='Broiler Dashboard', compute='_compute_farm_dashboard_access',
        inverse='_inverse_broiler_dashboard', search='_search_broiler_dashboard',
        help="The user sees the Broiler Performance Dashboard and the Broiler Lifecycle Investment report.")

    @api.depends('group_ids')
    def _compute_farm_dashboard_access(self):
        layer = self.env.ref(LAYER_GROUP, raise_if_not_found=False)
        broiler = self.env.ref(BROILER_GROUP, raise_if_not_found=False)
        for user in self:
            user.enable_flock_dashboard = bool(layer and layer in user.group_ids)
            user.enable_broiler_dashboard = bool(broiler and broiler in user.group_ids)

    def _farm_set_group(self, xmlid, enabled):
        group = self.env.ref(xmlid)
        for user in self:
            if enabled(user) != (group in user.group_ids):
                user.group_ids = [(4, group.id)] if enabled(user) else [(3, group.id)]

    def _inverse_flock_dashboard(self):
        self._farm_set_group(LAYER_GROUP, lambda user: user.enable_flock_dashboard)

    def _inverse_broiler_dashboard(self):
        self._farm_set_group(BROILER_GROUP, lambda user: user.enable_broiler_dashboard)

    def _farm_search_group(self, xmlid, operator, value):
        if operator not in ('=', '!=', 'in', 'not in'):
            return NotImplemented
        values = value if operator in ('in', 'not in') else [value]
        wanted = any(values) if operator in ('=', 'in') else not any(values)
        group = self.env.ref(xmlid)
        return [('group_ids', 'in' if wanted else 'not in', group.id)]

    def _search_flock_dashboard(self, operator, value):
        return self._farm_search_group(LAYER_GROUP, operator, value)

    def _search_broiler_dashboard(self, operator, value):
        return self._farm_search_group(BROILER_GROUP, operator, value)
