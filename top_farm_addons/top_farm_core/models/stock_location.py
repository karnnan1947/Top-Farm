# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class StockLocation(models.Model):
    _inherit = 'stock.location'

    farm_hierarchy_level = fields.Selection([
        ('farm', 'Farm Facility'),
        ('batch', 'Batch / Flock'),
        ('cage', 'Cage Sublocation'),
    ], string='Farm Hierarchy Level', index=True,
       help="Categorizes location into Farm Facility, Batch (Flock house), or Cage level.")

    parent_batch_location_id = fields.Many2one(
        'stock.location',
        string='Parent Batch Location',
        compute='_compute_parent_batch_location',
        store=True,
        recursive=True,
        index=True,
        help="Automatically resolved parent batch location for cage sublocations."
    )

    batch_stage = fields.Selection([
        ('pre_laying', 'Pre-Laying (Weeks 1–18)'),
        ('laying', 'Laying Phase (Weeks 19–72)'),
        ('spent', 'Spent Hen / Depleted'),
    ], string='Flock Lifecycle Stage',
       compute='_compute_batch_stage', store=True, readonly=False, recursive=True, index=True,
       help="Current physiological stage of the flock. Set on the batch; its cages follow it.")

    chick_arrival_date = fields.Date(
        string='Chick Arrival Date',
        help="Date when day-old chicks or pullets arrived at the facility."
    )

    flock_age_weeks = fields.Float(
        string='Flock Age (Weeks)',
        compute='_compute_flock_age',
        digits=(16, 1),
        help="Calculated age of the flock in weeks based on arrival date."
    )

    farm_analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Farm Analytic Account',
        copy=False,
        check_company=True,
        help="Analytic account mapped directly to this Batch (in Batch Plan) or Cage (in Cage Plan)."
    )

    live_bird_count = fields.Integer(
        string='Live Birds',
        compute='_compute_live_bird_count',
        help="Current count of live birds on hand at this location and its sublocations (from stock.quant)."
    )

    sub_cage_count = fields.Integer(
        string='Cages Count',
        compute='_compute_sub_cage_count',
        help="Number of active cage sublocations under this batch or farm."
    )

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------
    @api.depends('farm_hierarchy_level', 'location_id.parent_batch_location_id')
    def _compute_parent_batch_location(self):
        """
        A batch is its own parent batch; a farm has none. Everything else (cages, and any
        unclassified row/aisle between a batch and its cages) inherits the nearest batch above it,
        so moving a batch in the tree re-resolves all of its cages.
        """
        for loc in self:
            if loc.farm_hierarchy_level == 'batch':
                loc.parent_batch_location_id = loc
            elif loc.farm_hierarchy_level == 'farm':
                loc.parent_batch_location_id = False
            else:
                loc.parent_batch_location_id = loc.location_id.parent_batch_location_id

    @api.depends('farm_hierarchy_level', 'parent_batch_location_id.batch_stage')
    def _compute_batch_stage(self):
        for loc in self:
            if loc.farm_hierarchy_level == 'batch':
                loc.batch_stage = loc.batch_stage or 'pre_laying'
            elif loc.farm_hierarchy_level == 'cage':
                loc.batch_stage = loc.parent_batch_location_id.batch_stage
            else:
                loc.batch_stage = False

    @api.depends('chick_arrival_date', 'parent_batch_location_id.chick_arrival_date')
    def _compute_flock_age(self):
        """Compute age of flock in weeks based on arrival date."""
        today = fields.Date.context_today(self)
        for loc in self:
            arrival = loc.chick_arrival_date or loc.parent_batch_location_id.chick_arrival_date
            if arrival:
                loc.flock_age_weeks = max(0.0, round((today - arrival).days / 7.0, 1))
            else:
                loc.flock_age_weeks = 0.0

    def _compute_live_bird_count(self):
        counts = self._origin._get_live_bird_counts()
        for loc in self:
            loc.live_bird_count = counts.get(loc._origin.id, 0)

    def _compute_sub_cage_count(self):
        """Count child cages under this farm or batch."""
        for loc in self:
            if loc.farm_hierarchy_level in ('farm', 'batch') and loc._origin.id:
                loc.sub_cage_count = self.search_count([
                    ('id', 'child_of', loc._origin.id),
                    ('farm_hierarchy_level', '=', 'cage'),
                ])
            else:
                loc.sub_cage_count = 0

    # -------------------------------------------------------------------------
    # CONSTRAINTS
    # -------------------------------------------------------------------------
    @api.constrains('farm_hierarchy_level', 'parent_batch_location_id')
    def _check_cage_parent_batch(self):
        """Ensure every cage sublocation belongs to an ancestor Batch / Flock."""
        for loc in self:
            if loc.farm_hierarchy_level == 'cage' and not loc.parent_batch_location_id:
                raise ValidationError(_(
                    "Cage location '%s' must be located under a parent location classified as 'Batch / Flock'.",
                    loc.display_name
                ))

    @api.constrains('farm_analytic_account_id', 'parent_batch_location_id')
    def _check_farm_analytic_plans(self):
        """
        A cage's cost lands on ONE analytic line holding both its batch account and its own account,
        one per plan column. Two accounts from the same root plan would share a column, so one of
        them would be silently dropped: the batch and cage accounts must come from different plans.
        """
        for loc in self:
            if loc.farm_hierarchy_level == 'batch':
                cages = self.search([
                    ('parent_batch_location_id', '=', loc.id),
                    ('farm_hierarchy_level', '=', 'cage'),
                ])
            else:
                cages = loc.filtered(lambda l: l.farm_hierarchy_level == 'cage')
            for cage in cages:
                batch_account = cage.parent_batch_location_id.farm_analytic_account_id
                cage_account = cage.farm_analytic_account_id
                if batch_account and cage_account and batch_account.root_plan_id == cage_account.root_plan_id:
                    raise ValidationError(_(
                        "Cage '%(cage)s' and its batch '%(batch)s' both use analytic accounts from the plan "
                        "'%(plan)s'. Map batches and cages to accounts of two different root plans "
                        "(e.g. a Flock Batch Plan and a Cage Row Plan).",
                        cage=cage.display_name,
                        batch=cage.parent_batch_location_id.display_name,
                        plan=cage_account.root_plan_id.display_name,
                    ))

    # -------------------------------------------------------------------------
    # PUBLIC HELPER METHODS
    # -------------------------------------------------------------------------
    def _get_live_bird_counts(self):
        """Return {location id: live birds on hand in it and all its sublocations}, in one query."""
        locations = self.filtered('id')
        if not locations:
            return {}
        groups = self.env['stock.quant']._read_group(
            [('location_id', 'child_of', locations.ids), ('product_id.is_farm_bird', '=', True)],
            groupby=['location_id'],
            aggregates=['quantity:sum'],
        )
        counts = dict.fromkeys(locations.ids, 0.0)
        for quant_location, quantity in groups:
            # parent_path ('1/7/42/57/') lists the quant's location and every ancestor of it
            for ancestor_id in quant_location.parent_path.split('/')[:-1]:
                if int(ancestor_id) in counts:
                    counts[int(ancestor_id)] += quantity
        return {location_id: round(quantity) for location_id, quantity in counts.items()}

    def get_live_bird_count(self):
        """Query live bird count on hand for single record operations (always read fresh)."""
        self.ensure_one()
        return self._get_live_bird_counts().get(self.id, 0)

    def get_analytic_distribution_for_cage(self):
        """
        Builds the Odoo 19 multi-plan analytic distribution dictionary.
        Returns: {f"{batch_account_id},{cage_account_id}": 100.0}
        Creates ONE single analytic line with both plan columns populated, preventing cost doubling.
        """
        self.ensure_one()
        # Union keeps batch first and drops the duplicate when called on the batch itself
        accounts = self.parent_batch_location_id.farm_analytic_account_id | self.farm_analytic_account_id
        if not accounts:
            return {}
        return {','.join(str(account_id) for account_id in accounts.ids): 100.0}

    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------
    def action_start_laying_phase(self):
        """Transition a batch from Pre-Laying to Laying; its cages follow through batch_stage."""
        self.ensure_one()
        if not self.env.su and not self.env.user.has_group('top_farm_core.group_farm_manager'):
            raise AccessError(_("Only Farm Managers can start the Laying Phase."))
        if self.farm_hierarchy_level != 'batch':
            raise UserError(_("The Laying Phase is started on a 'Batch / Flock' location, not on '%s'.",
                              self.display_name))
        if self.batch_stage != 'pre_laying':
            raise UserError(_("Only flocks in 'Pre-Laying' stage can be transitioned to 'Laying'."))
        self.batch_stage = 'laying'
        return True

    def action_view_cages(self):
        """Action for smart button to view child cages."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('top_farm_core.action_top_farm_locations')
        action['name'] = action['display_name'] = _("Cages of %s", self.display_name)
        action['domain'] = [('id', 'child_of', self.id), ('farm_hierarchy_level', '=', 'cage')]
        action['context'] = {'default_farm_hierarchy_level': 'cage'}
        if self.farm_hierarchy_level == 'batch':
            # A cage created from a farm would have no batch above it, so only default the parent here
            action['context']['default_location_id'] = self.id
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
