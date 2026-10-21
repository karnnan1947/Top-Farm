# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

# Bird houses: the locations live birds are kept in. Sheds only group cages.
BIRD_HOUSE_LEVELS = ('brooding', 'cage')


class StockLocation(models.Model):
    _inherit = 'stock.location'

    farm_hierarchy_level = fields.Selection([
        ('farm', 'Farm Facility'),
        ('brooding', 'Brooding Nursery'),
        ('shed', 'Laying Shed'),
        ('cage', 'Cage'),
    ], string='Farm Hierarchy Level', index=True,
       help="Permanent farm infrastructure. Farm Facility: an estate. Brooding Nursery: heated house where "
            "day-old chicks spend their first weeks. Laying Shed: groups cages. Cage: where pullets and hens "
            "live from the cage allocation on. Flocks are lots that move through these locations.")

    farm_code = fields.Char(
        string='Estate Code',
        help="Short code of the farm estate (e.g. IHL), used to name its flock lots (IHL-19-10-2026).")

    parent_farm_location_id = fields.Many2one(
        'stock.location',
        string='Farm',
        compute='_compute_parent_farm_location',
        store=True,
        recursive=True,
        index=True,
        help="Automatically resolved farm facility above a brooding nursery, shed or cage (a farm is its own farm)."
    )

    farm_analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Cage Analytic Account',
        copy=False,
        check_company=True,
        help="Analytic account of the cage. Cage costs are tagged to it together with the flock's own account, "
             "so it must belong to another root plan than the Flock Analytic Plan."
    )

    live_bird_count = fields.Integer(
        string='Live Birds',
        compute='_compute_live_bird_count',
        help="Current count of live birds on hand at this location and its sublocations (from stock.quant)."
    )

    sub_cage_count = fields.Integer(
        string='Cages Count',
        compute='_compute_sub_cage_count',
        help="Number of cages under this farm or shed."
    )

    flock_lot_ids = fields.Many2many(
        'stock.lot', string='Flocks Present', compute='_compute_flock_lot_ids',
        help="Flock lots with live birds in this location (and its sublocations) now.")

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------
    @api.depends('farm_hierarchy_level', 'location_id.parent_farm_location_id')
    def _compute_parent_farm_location(self):
        """A farm is its own farm; everything below it inherits the nearest farm above, so moving a shed
        to another farm re-resolves it and all of its cages. Locations outside a farm have none."""
        for loc in self:
            if loc.farm_hierarchy_level == 'farm':
                loc.parent_farm_location_id = loc
            else:
                loc.parent_farm_location_id = loc.location_id.parent_farm_location_id

    def _compute_live_bird_count(self):
        counts = self._origin._get_live_bird_counts()
        for loc in self:
            loc.live_bird_count = counts.get(loc._origin.id, 0)

    def _compute_sub_cage_count(self):
        """Count the cages under this farm or shed."""
        for loc in self:
            if loc.farm_hierarchy_level in ('farm', 'shed') and loc._origin.id:
                loc.sub_cage_count = self.search_count([
                    ('id', 'child_of', loc._origin.id),
                    ('farm_hierarchy_level', '=', 'cage'),
                ])
            else:
                loc.sub_cage_count = 0

    def _compute_flock_lot_ids(self):
        for loc in self:
            loc.flock_lot_ids = loc._origin._get_flock_lots() if loc._origin.id else False

    # -------------------------------------------------------------------------
    # CONSTRAINTS
    # -------------------------------------------------------------------------
    @api.constrains('farm_hierarchy_level', 'parent_farm_location_id')
    def _check_inside_farm(self):
        """Brooding nurseries, sheds and cages belong to an estate: its code names the flock lots."""
        for loc in self:
            if loc.farm_hierarchy_level in ('brooding', 'shed', 'cage') and not loc.parent_farm_location_id:
                raise ValidationError(_(
                    "'%(location)s' must be located under a location classified as 'Farm Facility'.",
                    location=loc.display_name))

    @api.constrains('farm_code', 'farm_hierarchy_level', 'company_id')
    def _check_farm_code(self):
        for loc in self.filtered(lambda l: l.farm_hierarchy_level == 'farm' and l.farm_code):
            if self.search_count([('id', '!=', loc.id), ('farm_hierarchy_level', '=', 'farm'),
                                  ('farm_code', '=ilike', loc.farm_code), ('company_id', '=', loc.company_id.id)]):
                raise ValidationError(_("Another farm already uses the estate code %s.", loc.farm_code))

    @api.constrains('farm_analytic_account_id')
    def _check_cage_analytic_plan(self):
        """A cage's cost lands on ONE analytic line holding both the flock account and the cage account, one
        column per root plan. Two accounts of the same root plan would share a column and one of them would be
        silently dropped, so a cage account must not come from a plan used by flock accounts."""
        for loc in self.filtered('farm_analytic_account_id'):
            plan = loc.farm_analytic_account_id.root_plan_id
            company = loc.company_id or self.env.company
            if plan == company._get_farm_flock_plan().root_id or self.env['stock.lot'].search_count(
                    [('flock_analytic_account_id.root_plan_id', '=', plan.id)], limit=1):
                raise ValidationError(_(
                    "The analytic account of %(cage)s belongs to the plan '%(plan)s', which holds flock accounts. "
                    "Use an account of another root plan for cages (e.g. Farm Cages).",
                    cage=loc.display_name, plan=plan.display_name))

    # -------------------------------------------------------------------------
    # PUBLIC HELPER METHODS
    # -------------------------------------------------------------------------
    def _get_live_bird_counts(self, lot=None):
        """Return {location id: live birds on hand in it and all its sublocations}, in one query.
        With `lot`, only the birds of that flock."""
        locations = self.filtered('id')
        if not locations:
            return {}
        domain = [('location_id', 'child_of', locations.ids), ('product_id.is_farm_bird', '=', True)]
        if lot is not None:
            domain.append(('lot_id', '=', lot.id))
        groups = self.env['stock.quant']._read_group(domain, groupby=['location_id'], aggregates=['quantity:sum'])
        counts = dict.fromkeys(locations.ids, 0.0)
        for quant_location, quantity in groups:
            # parent_path ('1/7/42/57/') lists the quant's location and every ancestor of it
            for ancestor_id in quant_location.parent_path.split('/')[:-1]:
                if int(ancestor_id) in counts:
                    counts[int(ancestor_id)] += quantity
        return {location_id: round(quantity) for location_id, quantity in counts.items()}

    def get_live_bird_count(self, lot=None):
        """Query live bird count on hand for single record operations (always read fresh)."""
        self.ensure_one()
        return self._get_live_bird_counts(lot).get(self.id, 0)

    def _get_flock_lots(self):
        """Flock lots with live birds in this location and its sublocations."""
        self.ensure_one()
        quants = self.env['stock.quant'].search([
            ('location_id', 'child_of', self.id), ('product_id.is_farm_bird', '=', True),
            ('quantity', '>', 0), ('lot_id.is_flock_batch', '=', True)])
        return quants.lot_id

    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------
    def action_allocate_birds(self):
        """Manager button on a brooding nursery: open the wizard that moves its flock into the farm's cages."""
        self.ensure_one()
        if not self.env.su and not self.env.user.has_group('top_farm_core.group_farm_manager'):
            raise AccessError(_("Only Farm Managers can allocate birds to cages."))
        if self.farm_hierarchy_level != 'brooding':
            raise UserError(_("Birds are allocated to cages from a 'Brooding Nursery', not from '%s'.",
                              self.display_name))
        return {
            'type': 'ir.actions.act_window',
            'name': _("Allocate Flock to Cages"),
            'res_model': 'farm.cage.allocation.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_brooding_location_id': self.id},
        }

    def action_view_cages(self):
        """Action for smart button to view the cages of a farm or shed."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('top_farm_core.action_top_farm_locations')
        action['name'] = action['display_name'] = _("Cages of %s", self.display_name)
        action['domain'] = [('id', 'child_of', self.id), ('farm_hierarchy_level', '=', 'cage')]
        action['context'] = {'default_farm_hierarchy_level': 'cage', 'default_location_id': self.id}
        return action

    def action_view_live_birds(self):
        """Action for smart button to view quants of live birds."""
        self.ensure_one()
        action = self.env['stock.quant']._get_quants_action()
        action['name'] = action['display_name'] = _("Live Birds in %s", self.display_name)
        action['domain'] = [
            ('location_id', 'child_of', self.id),
            ('product_id.is_farm_bird', '=', True),
        ]
        return action

    def action_view_flocks(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('top_farm_core.action_farm_flock_lots')
        action['name'] = action['display_name'] = _("Flocks in %s", self.display_name)
        action['domain'] = [('id', 'in', self._get_flock_lots().ids)]
        action['context'] = {'create': False}
        return action
