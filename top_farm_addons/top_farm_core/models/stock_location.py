# -*- coding: utf-8 -*-
from datetime import timedelta

from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import format_date

POINT_OF_LAY_ACTIVITY = 'top_farm_core.mail_activity_type_point_of_lay'


class StockLocation(models.Model):
    _name = 'stock.location'
    _inherit = ['stock.location', 'mail.thread', 'mail.activity.mixin']

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

    parent_farm_location_id = fields.Many2one(
        'stock.location',
        string='Farm',
        compute='_compute_parent_farm_location',
        store=True,
        recursive=True,
        index=True,
        help="Automatically resolved farm facility above a batch or cage (a farm is its own farm)."
    )

    unallocated_bird_count = fields.Integer(
        string='Unallocated Birds', compute='_compute_unallocated_bird_count',
        help="Birds sitting in the batch location itself, not yet allocated to a cage.")

    batch_stage = fields.Selection([
        ('pre_laying', 'Pre-Laying'),
        ('laying', 'Laying Phase'),
        ('spent', 'Spent Hen / Depleted'),
    ], string='Flock Lifecycle Stage',
       compute='_compute_batch_stage', store=True, readonly=False, recursive=True, index=True, tracking=True,
       help="Current physiological stage of the flock. Set on the batch; its cages follow it.")

    chick_arrival_date = fields.Date(
        string='Chick Arrival Date',
        help="Date when day-old chicks or pullets arrived at the facility."
    )

    laying_notification_sent = fields.Boolean(
        string='Laying Advance Warning Sent',
        compute='_compute_laying_notification_sent',
        store=True,
        readonly=False,
        copy=False,
        help="Set once the point-of-lay inspection alert has been sent for this flock. "
             "Cleared when a new chick arrival date is entered, i.e. for the next flock cycle."
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

    @api.depends('farm_hierarchy_level', 'location_id.parent_farm_location_id')
    def _compute_parent_farm_location(self):
        """A farm is its own farm; everything below it inherits the nearest farm above, so moving a
        batch to another farm re-resolves it and all of its cages. Locations outside a farm have none."""
        for loc in self:
            if loc.farm_hierarchy_level == 'farm':
                loc.parent_farm_location_id = loc
            else:
                loc.parent_farm_location_id = loc.location_id.parent_farm_location_id

    @api.depends('farm_hierarchy_level', 'parent_batch_location_id.batch_stage')
    def _compute_batch_stage(self):
        for loc in self:
            if loc.farm_hierarchy_level == 'batch':
                loc.batch_stage = loc.batch_stage or 'pre_laying'
            elif loc.farm_hierarchy_level == 'cage':
                loc.batch_stage = loc.parent_batch_location_id.batch_stage
            else:
                loc.batch_stage = False

    @api.depends('chick_arrival_date')
    def _compute_laying_notification_sent(self):
        self.laying_notification_sent = False

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

    def _compute_unallocated_bird_count(self):
        batches = self.filtered(lambda l: l.farm_hierarchy_level == 'batch' and l._origin.id)
        counts = {}
        if batches:
            for location, quantity in self.env['stock.quant']._read_group(
                    [('location_id', 'in', batches._origin.ids), ('product_id.is_farm_bird', '=', True)],
                    ['location_id'], ['quantity:sum']):
                counts[location.id] = quantity
        for loc in self:
            loc.unallocated_bird_count = round(counts.get(loc._origin.id, 0))

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
        Builds the Odoo 20 multi-plan analytic distribution dictionary.
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
        """Manager button: transition a batch from Pre-Laying to Laying (available in both transition modes)."""
        self.ensure_one()
        if not self.env.su and not self.env.user.has_group('top_farm_core.group_farm_manager'):
            raise AccessError(_("Only Farm Managers can start the Laying Phase."))
        self._start_laying_phase()
        return True

    def _check_batch_stage_change(self, from_stage):
        """Manager-only correction of the flock stage (never callable by an operator, whatever the context)."""
        self.ensure_one()
        if not self.env.su and not self.env.user.has_group('top_farm_core.group_farm_manager'):
            raise AccessError(_("Only Farm Managers can change the stage of a flock."))
        if self.farm_hierarchy_level != 'batch':
            raise UserError(_("The stage is changed on a 'Batch / Flock' location, not on '%s'.", self.display_name))
        if self.batch_stage != from_stage:
            raise UserError(_("This flock is not in the '%(stage)s' stage.",
                              stage=dict(self._fields['batch_stage'].selection).get(from_stage)))

    def action_allocate_birds(self):
        """Manager button on a batch: open the wizard that moves its birds into its cages."""
        self.ensure_one()
        if not self.env.su and not self.env.user.has_group('top_farm_core.group_farm_manager'):
            raise AccessError(_("Only Farm Managers can allocate birds to cages."))
        if self.farm_hierarchy_level != 'batch':
            raise UserError(_("Birds are allocated from a 'Batch / Flock' location, not from '%s'.", self.display_name))
        return {
            'type': 'ir.actions.act_window',
            'name': _("Allocate Birds to Cages"),
            'res_model': 'farm.cage.allocation.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_batch_location_id': self.id},
        }

    def action_back_to_pre_laying(self):
        """Manager button: correct a flock that was moved to Laying by mistake. Its cages follow."""
        self.ensure_one()
        self._check_batch_stage_change('laying')
        company = self.company_id or self.env.company
        if (company.laying_transition_mode == 'automatic' and self.chick_arrival_date
                and self.flock_age_weeks >= company.laying_start_age_weeks):
            raise UserError(_(
                "The daily check is in automatic mode and this flock is already %(age)s weeks old "
                "(target %(target)s): it would start the Laying Phase again tonight. Switch the "
                "Laying Phase Transition to manual in the Top Farm settings, or correct the Chick "
                "Arrival Date, before moving it back.",
                age=f"{self.flock_age_weeks:.1f}", target=f"{company.laying_start_age_weeks:g}"))
        self.batch_stage = 'pre_laying'
        self.message_post(body=_("Flock moved back to Pre-Laying by %(user)s at %(age)s weeks.",
                                 user=self.env.user.name, age=f"{self.flock_age_weeks:.1f}"),
                          subtype_xmlid='mail.mt_note')
        return True

    def action_mark_spent(self):
        """Manager button: the laying cycle is over; the flock becomes Spent Hen / Depleted. Its cages follow."""
        self.ensure_one()
        self._check_batch_stage_change('laying')
        self.batch_stage = 'spent'
        self.message_post(body=_("Flock marked as Spent Hen / Depleted by %(user)s at %(age)s weeks.",
                                 user=self.env.user.name, age=f"{self.flock_age_weeks:.1f}"),
                          subtype_xmlid='mail.mt_note')
        return True

    def _start_laying_phase(self, automatic=False):
        """Move the batch to Laying; its cages follow through batch_stage. Private so that the daily
        check can call it, while RPC callers always go through the manager check above."""
        self.ensure_one()
        if self.farm_hierarchy_level != 'batch':
            raise UserError(_("The Laying Phase is started on a 'Batch / Flock' location, not on '%s'.",
                              self.display_name))
        if self.batch_stage != 'pre_laying':
            raise UserError(_("Only flocks in 'Pre-Laying' stage can be transitioned to 'Laying'."))
        self.batch_stage = 'laying'
        self.activity_feedback([POINT_OF_LAY_ACTIVITY], feedback=_("Laying Phase started."))
        age = f"{self.flock_age_weeks:.1f}"
        if automatic:
            body = _("Laying Phase started automatically: the flock reached %(age)s weeks.", age=age)
        else:
            body = _("Laying Phase started by %(user)s at %(age)s weeks.", user=self.env.user.name, age=age)
        self.message_post(body=body, subtype_xmlid='mail.mt_note')

    def _get_laying_due_date(self, target_age):
        self.ensure_one()
        return self.chick_arrival_date + timedelta(days=round(target_age * 7))

    def _send_laying_advance_warning(self):
        """Post the point-of-lay inspection alert and give each Farm Manager a To-Do on the batch."""
        self.ensure_one()
        company = self.company_id or self.env.company
        target_age = company.laying_start_age_weeks
        due_date = self._get_laying_due_date(target_age)
        if company.laying_transition_mode == 'automatic':
            next_step = _("The flock will switch to Laying automatically on that date. A Farm Manager "
                          "can click Start Laying Phase earlier if egg production has already begun.")
        else:
            next_step = _("A Farm Manager must click Start Laying Phase once the flock is ready.")
        today = fields.Date.context_today(self)
        values = {'name': self.display_name, 'age': f"{self.flock_age_weeks:.1f}",
                  'target': f"{target_age:.1f}", 'date': format_date(self.env, due_date)}
        if due_date >= today:
            intro = _("Flock %(name)s has reached %(age)s weeks. The Laying Phase is due at %(target)s weeks "
                      "(%(date)s). Please inspect the flock:", **values)
        else:
            intro = _("Flock %(name)s has reached %(age)s weeks and is past the Laying Phase target of "
                      "%(target)s weeks (%(date)s). Please inspect the flock:", **values)
        note = Markup("<p>%s</p><ul><li>%s</li><li>%s</li><li>%s</li></ul><p>%s</p>") % (
            intro,
            _("Body weight uniformity (around 1.45 kg)"),
            _("Comb and wattle development"),
            _("First sample eggs / egg drop"),
            next_step,
        )
        managers = self.env.ref('top_farm_core.group_farm_manager').all_user_ids.filtered(
            lambda u: u.active and not u.share and company in u.company_ids)
        for manager in managers:
            self.activity_schedule(
                POINT_OF_LAY_ACTIVITY,
                date_deadline=max(due_date, today),
                note=note,
                user_id=manager.id,
            )
        self.message_post(body=note, subtype_xmlid='mail.mt_note')
        self.laying_notification_sent = True

    @api.model
    def _cron_check_flock_lifecycle(self):
        """Daily check of Pre-Laying flocks: send the advance warning once, then in automatic mode
        start the Laying Phase when the target age is reached."""
        batches = self.search([
            ('farm_hierarchy_level', '=', 'batch'),
            ('batch_stage', '=', 'pre_laying'),
            ('chick_arrival_date', '!=', False),
        ])
        for batch in batches:
            company = batch.company_id or self.env.company
            target_age = company.laying_start_age_weeks
            warning_age = target_age - company.laying_notification_advance_weeks
            if company.laying_transition_mode == 'automatic' and batch.flock_age_weeks >= target_age:
                # No warning first: an inspection To-Do that is closed in the same run is just noise
                batch._start_laying_phase(automatic=True)
            elif batch.flock_age_weeks >= warning_age and not batch.laying_notification_sent:
                batch._send_laying_advance_warning()

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
