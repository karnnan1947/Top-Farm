from datetime import datetime, time, timedelta

import pytz
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

MANAGER_GROUP = 'top_farm_mortality.group_mortality_manager'
TODO = 'mail.mail_activity_data_todo'

# Fields that may only be changed by the module's own methods (context flag below).
PROTECTED_FIELDS = {
    'state', 'opening_population', 'cumulative_dead', 'mortality_pct', 'threshold_pct_used',
    'min_dead_count_used', 'threshold_rule_used', 'requires_approval', 'approved_by_id', 'approved_date', 'scrap_move_id', 'reversal_move_id',
    'rejection_reason', 'reversal_reason',
}
SNAPSHOT_FIELDS = {'opening_population', 'cumulative_dead', 'mortality_pct',
                   'threshold_pct_used', 'min_dead_count_used', 'threshold_rule_used', 'requires_approval'}
LOCKED_FIELDS = PROTECTED_FIELDS - SNAPSHOT_FIELDS
# Fields that are frozen once the log leaves draft.
DRAFT_ONLY_FIELDS = SNAPSHOT_FIELDS | {
    'date', 'cage_location_id', 'bird_product_id', 'lot_id', 'dead_bird_count',
    'cause_of_death', 'backdate_reason', 'company_id',
}


class FarmMortalityLog(models.Model):
    _name = 'farm.mortality.log'
    _description = 'Daily Poultry Mortality Log'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True,
                       default=lambda self: _('New'))
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)
    date = fields.Date(string='Incident Date', required=True, default=fields.Date.context_today,
                       tracking=True)
    backdate_reason = fields.Text(string='Backdate Reason')
    is_backdated = fields.Boolean(compute='_compute_ui_flags')
    can_backdate = fields.Boolean(compute='_compute_ui_flags')
    is_manager = fields.Boolean(compute='_compute_ui_flags')

    cage_location_id = fields.Many2one(
        'stock.location', string='Cage Location', required=True, tracking=True,
        domain="[('farm_hierarchy_level', '=', 'cage')]")
    batch_location_id = fields.Many2one(
        'stock.location', string='Flock Batch', related='cage_location_id.parent_batch_location_id',
        store=True, readonly=True)
    bird_product_id = fields.Many2one(
        'product.product', string='Bird Product', required=True, tracking=True,
        domain="[('product_tmpl_id.is_farm_bird', '=', True)]")
    product_tracking = fields.Selection(related='bird_product_id.tracking')
    lot_id = fields.Many2one('stock.lot', string='Flock Lot', tracking=True,
                             domain="[('product_id', '=', bird_product_id)]")
    dead_bird_count = fields.Integer(string='Dead Bird Count', tracking=True)
    cause_of_death = fields.Selection([
        ('disease', 'Disease / Infection'),
        ('heat_stress', 'Heat Stress / Dehydration'),
        ('cannibalism', 'Cannibalism / Pecking'),
        ('smothering', 'Smothering / Piling'),
        ('sudden_death', 'Sudden Death Syndrome (SDS)'),
        ('other', 'Other / Unknown'),
    ], string='Cause of Death', required=True, default='other', tracking=True)
    notes = fields.Text(string='Observations / Symptoms')

    # Snapshots (preview while draft, frozen at submit)
    opening_population = fields.Integer(string='Opening Population', readonly=True)
    cumulative_dead = fields.Integer(string='Cumulative Dead Today', readonly=True)
    mortality_pct = fields.Float(string="Today's Cage Mortality (%)", readonly=True, digits=(16, 2))
    threshold_pct_used = fields.Float(string='Threshold Used (%)', readonly=True, digits=(16, 2))
    threshold_rule_used = fields.Selection(
        [('above', 'Above (>)'), ('at_or_above', 'At or above (≥)')], string='Threshold Rule Used', readonly=True,
        help="Mortality Controls rule in force when the log was submitted.")
    min_dead_count_used = fields.Integer(
        string='Minimum Dead Birds Used', readonly=True,
        help="Minimum dead-bird count in force when the log was submitted: approval is only required when the "
             "cumulative dead count is above it.")
    requires_approval = fields.Boolean(readonly=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting_approval', 'Waiting Manager Approval'),
        ('done', 'Scrapped'),
        ('rejected', 'Rejected'),
        ('reversed', 'Reversed'),
    ], string='Status', default='draft', readonly=True, copy=False, tracking=True)
    rejection_reason = fields.Text(readonly=True, copy=False)
    reversal_reason = fields.Text(readonly=True, copy=False)
    approved_by_id = fields.Many2one('res.users', string='Approved By', readonly=True, copy=False)
    approved_date = fields.Datetime(readonly=True, copy=False)
    scrap_move_id = fields.Many2one('stock.move', string='Stock Scrap', readonly=True, copy=False)
    reversal_move_id = fields.Many2one('stock.move', string='Reversal Move', readonly=True, copy=False)

    # ------------------------------------------------------------------
    # ORM overrides / protection
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        internal = self.env.context.get('mortality_internal') or self.env.su
        for vals in vals_list:
            if not internal and (vals.get('state', 'draft') != 'draft'
                                 or any(vals.get(f) for f in LOCKED_FIELDS - {'state'})):
                raise AccessError(_("These fields are managed by the workflow."))
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('farm.mortality.log') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        if not (self.env.context.get('mortality_internal') or self.env.su):
            if LOCKED_FIELDS & set(vals):
                raise AccessError(_("These fields are managed by the workflow."))
            if DRAFT_ONLY_FIELDS & set(vals) and any(rec.state != 'draft' for rec in self):
                raise UserError(_("Only draft mortality logs can be edited."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft(self):
        if any(rec.state != 'draft' for rec in self):
            raise UserError(_("Only draft mortality logs can be deleted. Use Reverse for scrapped ones."))

    # ------------------------------------------------------------------
    # Computes / constraints / onchange
    # ------------------------------------------------------------------
    @api.depends('date')
    @api.depends_context('uid')
    def _compute_ui_flags(self):
        is_manager = self.env.user.has_group(MANAGER_GROUP)
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_manager = is_manager
            rec.can_backdate = is_manager
            rec.is_backdated = bool(rec.date and rec.date != today)

    @api.constrains('bird_product_id')
    def _check_bird_flag(self):
        for rec in self:
            if not rec.bird_product_id.product_tmpl_id.is_farm_bird:
                raise ValidationError(_("'%s' is not flagged as a Farm Bird product.",
                                        rec.bird_product_id.display_name))

    @api.onchange('cage_location_id', 'bird_product_id', 'lot_id', 'date', 'dead_bird_count')
    def _onchange_preview(self):
        # auto-fill product, then lot, when there is only one possible choice
        if self.cage_location_id and not self.bird_product_id:
            products = self._cage_quants(self.cage_location_id).product_id
            if len(products) == 1:
                self.bird_product_id = products
        if self.cage_location_id and self.bird_product_id:
            if self.lot_id and self.lot_id.product_id != self.bird_product_id:
                self.lot_id = False
            if not self.lot_id:
                lots = self._cage_quants(self.cage_location_id, self.bird_product_id).lot_id
                if len(lots) == 1:
                    self.lot_id = lots
        self.update(self._snapshot_vals())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _cage_quants(self, cage, product=None, lot=None):
        domain = [('location_id', 'child_of', cage.id), ('quantity', '>', 0),
                  ('product_id.product_tmpl_id.is_farm_bird', '=', True)]
        if product:
            domain.append(('product_id', '=', product.id))
        if lot:
            domain.append(('lot_id', '=', lot.id))
        return self.env['stock.quant'].search(domain)

    def _live_qty(self, lot=None):
        quants = self._cage_quants(self.cage_location_id, self.bird_product_id, lot)
        return int(sum(quants.mapped('quantity')))

    def _dead_sum(self, states, date=None, op='=', lot=None, whole_cage=False):
        """Dead birds already logged in this cage (excluding this record). Per product unless
        whole_cage, which is used for the cage-level population/threshold maths."""
        domain = [('cage_location_id', '=', self.cage_location_id.id),
                  ('state', 'in', states), ('id', '!=', self._origin.id or 0)]
        if not whole_cage:
            domain.append(('bird_product_id', '=', self.bird_product_id.id))
        if date:
            domain.append(('date', op, date))
        if lot:
            domain.append(('lot_id', '=', lot.id))
        return sum(self.search(domain).mapped('dead_bird_count'))

    def _birds_moved_in_after(self, date):
        """Net birds that entered the cage (and its sublocations) after the end of `date`: placements and
        transfers in, minus transfers out and sales. Taking them off the live count gives the cage as it was on
        that day, so a backdated log is measured on the birds really there. Mortality scraps and reversals are
        left out: the logs count those, by incident date (their stock is posted on the day they are processed).
        For today's logs nothing has happened after today, so this is 0."""
        self.ensure_one()
        cage = self.cage_location_id
        tz = pytz.timezone(self.env.user.tz or self.env.context.get('tz') or 'UTC')
        boundary = tz.localize(datetime.combine(date + timedelta(days=1), time.min)).astimezone(pytz.utc)
        lines = self.env['stock.move.line'].sudo().search([
            ('state', '=', 'done'), ('date', '>=', boundary.replace(tzinfo=None)),
            ('product_id.product_tmpl_id.is_farm_bird', '=', True),
            ('move_id.farm_mortality_log_id', '=', False),
            '|', ('location_id', 'child_of', cage.id), ('location_dest_id', 'child_of', cage.id),
        ])
        inside = f"{cage.parent_path}"
        net = 0.0
        for line in lines:
            came_in = line.location_dest_id.parent_path.startswith(inside)
            went_out = line.location_id.parent_path.startswith(inside)
            if came_in and not went_out:
                net += line.quantity_product_uom
            elif went_out and not came_in:
                net -= line.quantity_product_uom
        return int(round(net))

    def _snapshot_vals(self):
        """Authoritative numbers for the threshold check (also used as draft preview)."""
        self.ensure_one()
        cfg = self.env['farm.mortality.config']._get_config(self.company_id)
        zero = {'opening_population': 0, 'cumulative_dead': 0, 'mortality_pct': 0.0,
                'threshold_pct_used': cfg.daily_mortality_threshold_pct,
                'min_dead_count_used': cfg.min_dead_count, 'threshold_rule_used': cfg.threshold_rule,
                'requires_approval': False}
        if not (self.cage_location_id and self.bird_product_id and self.date):
            return zero
        # Cage-level maths: live birds come from top_farm_core's count, dead from all logs of the cage.
        opening = (self.cage_location_id.get_live_bird_count()
                   - self._birds_moved_in_after(self.date)
                   + self._dead_sum(['done'], self.date, '>=', whole_cage=True))
        cumulative = (self._dead_sum(['done', 'waiting_approval'], self.date, '=', whole_cage=True)
                      + self.dead_bird_count)
        # The rule is applied to the percentage as shown (2 decimals), so the screen and the message never
        # say "2.00 % above the 2.00 % threshold".
        pct = round(cumulative / opening * 100.0, 2) if opening > 0 else 0.0
        # No population to measure against (e.g. birds booked into the cage after the incident date only):
        # the percentage means nothing, so the manager decides instead of letting the log through at 0 %.
        no_base = cumulative > 0 and opening <= 0
        return {
            'opening_population': opening,
            'cumulative_dead': cumulative,
            'mortality_pct': pct,
            'threshold_pct_used': cfg.daily_mortality_threshold_pct,
            'min_dead_count_used': cfg.min_dead_count,
            'threshold_rule_used': cfg.threshold_rule,
            'requires_approval': no_base or bool(
                self._over_threshold(pct, cfg.daily_mortality_threshold_pct, cfg.threshold_rule)
                and cumulative > cfg.min_dead_count),
        }

    @api.model
    def _over_threshold(self, pct, threshold, rule):
        return pct >= threshold if rule == 'at_or_above' else pct > threshold

    def _below_floor_note(self):
        """Chatter text when the % is over the threshold but the minimum dead-bird count waives approval."""
        self.ensure_one()
        if self.requires_approval or not self._over_threshold(
                self.mortality_pct, self.threshold_pct_used, self.threshold_rule_used):
            return False
        return Markup(_(
            "No manager approval needed: %(pct).2f%% is %(rule)s the %(thr).2f%% threshold, but %(dead)s dead "
            "birds is not above the configured minimum of %(min)s.")) % {
            'pct': self.mortality_pct, 'thr': self.threshold_pct_used, 'rule': self._rule_words(),
            'dead': self.cumulative_dead, 'min': self.min_dead_count_used}

    def _rule_words(self, rule=None):
        rule = rule or self.threshold_rule_used
        return _("at or above") if rule == 'at_or_above' else _("above")

    def _recheck_waiting_logs(self, reason):
        """After a log of a cage-day is rejected or reversed, refresh the figures of the logs of that cage-day
        still waiting for approval (their snapshot counted it). The manager still decides."""
        for rec in self:
            waiting = self.search([('cage_location_id', '=', rec.cage_location_id.id), ('date', '=', rec.date),
                                   ('state', '=', 'waiting_approval'), ('id', '!=', rec.id)])
            for log in waiting:
                old_pct, old_dead = log.mortality_pct, log.cumulative_dead
                snap = log._snapshot_vals()
                log.with_context(mortality_internal=True).write(snap)
                if snap['requires_approval']:
                    verdict = _("still needs approval")
                else:
                    verdict = _("no longer over the threshold: approve to scrap, or reject")
                log.message_post(body=Markup(_(
                    "Figures refreshed after %(reason)s of %(log)s: cumulative dead %(old_dead)s → %(dead)s, "
                    "mortality %(old_pct).2f%% → %(pct).2f%% (%(verdict)s).")) % {
                    'reason': reason, 'log': rec.name, 'old_dead': old_dead, 'dead': snap['cumulative_dead'],
                    'old_pct': old_pct, 'pct': snap['mortality_pct'], 'verdict': verdict})

    def _lock_cage(self):
        self.env.cr.execute("SELECT id FROM stock_location WHERE id = %s FOR UPDATE",
                            (self.cage_location_id.id,))

    def _check_hard_guard(self, count_pending=True):
        """dead <= live birds of the lot in the cage, minus other pending logs of that lot.
        On approval other pending logs are not counted (each re-checks itself)."""
        self.ensure_one()
        lot = self.lot_id or None
        lot_live = self._live_qty(lot)
        pending = self._dead_sum(['waiting_approval'], lot=lot) if count_pending else 0
        available = lot_live - pending
        if self.dead_bird_count > available:
            raise ValidationError(_(
                "Cannot log %(dead)s dead birds. %(live)s live birds are in %(cage)s%(lot)s, "
                "of which %(pending)s are already reserved by logs waiting approval.",
                dead=self.dead_bird_count, live=lot_live, cage=self.cage_location_id.display_name,
                lot=_(" (lot %s)", self.lot_id.name) if self.lot_id else '', pending=pending))

    def _check_manager(self):
        if not self.env.user.has_group(MANAGER_GROUP):
            raise AccessError(_("Only Mortality Managers can do this."))

    def _check_submit_rules(self):
        self.ensure_one()
        if self.dead_bird_count <= 0:
            raise UserError(_("Dead bird count must be greater than zero."))
        if self.product_tracking == 'lot' and not self.lot_id:
            raise UserError(_("Select the flock lot of the dead birds."))
        today = fields.Date.context_today(self)
        if self.date > today:
            raise UserError(_("The incident date cannot be in the future."))
        if self.date != today:
            if not self.env.user.has_group(MANAGER_GROUP):
                raise UserError(_("Only Mortality Managers can log a past date."))
            if not (self.backdate_reason or '').strip():
                raise UserError(_("A backdate reason is required for a past incident date."))

    @api.model
    def _get_scrap_location(self):
        loc = self.env.ref('top_farm_mortality.location_bird_mortality', raise_if_not_found=False)
        return loc or self.env['stock.location'].search([('usage', '=', 'inventory')], limit=1)

    def _managers(self):
        group = self.env.ref(MANAGER_GROUP)
        return self.env['res.users'].sudo().search(
            [('all_group_ids', 'in', group.id), ('share', '=', False)])

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Only draft logs can be submitted."))
            rec._check_submit_rules()
            rec._lock_cage()
            rec._check_hard_guard()
            snap = rec._snapshot_vals()
            rec_i = rec.with_context(mortality_internal=True)
            rec_i.write(snap)
            if snap['requires_approval']:
                rec_i.write({'state': 'waiting_approval'})
                rec._notify_managers(snap)
            else:
                rec_i._create_and_validate_scrap()
                rec_i.write({'state': 'done'})
                note = rec._below_floor_note()
                if note:
                    rec.message_post(body=note)
        return True

    def _notify_managers(self, snap):
        self.ensure_one()
        managers = self._managers()
        # Markup keeps the bold tags; the values themselves are escaped by the % operator
        body = Markup(_(
            "<b>Abnormal mortality:</b> %(cage)s reached <b>%(dead)s dead birds today (%(pct).2f%%)</b> "
            "of an opening population of %(pop)s, %(rule)s the %(thr).2f%% threshold. "
            "Manager approval is required before stock is scrapped.")) % {
            'rule': self._rule_words(snap['threshold_rule_used']),
            'cage': self.cage_location_id.display_name, 'dead': snap['cumulative_dead'],
            'pct': snap['mortality_pct'], 'pop': snap['opening_population'], 'thr': snap['threshold_pct_used']}
        self.message_post(body=body, partner_ids=managers.partner_id.ids)
        for user in managers:
            self.activity_schedule(
                TODO, user_id=user.id,
                summary=_("Approve mortality %s", self.name), note=body)

    def action_manager_approve(self):
        self._check_manager()
        for rec in self:
            if rec.state != 'waiting_approval':
                raise UserError(_("Only logs waiting for approval can be approved."))
            rec._lock_cage()
            rec._check_hard_guard(count_pending=False)
            rec_i = rec.with_context(mortality_internal=True)
            rec_i._create_and_validate_scrap()
            rec_i.write({'state': 'done', 'approved_by_id': self.env.user.id,
                         'approved_date': fields.Datetime.now()})
            rec.message_post(body=_("Approved by %s.", self.env.user.name))
            rec.activity_feedback([TODO], feedback=_("Approved by %s", self.env.user.name))
        return True

    def _do_reject(self, reason):
        self._check_manager()
        if not (reason or '').strip():
            raise UserError(_("A rejection reason is required."))
        for rec in self:
            if rec.state != 'waiting_approval':
                raise UserError(_("Only logs waiting for approval can be rejected."))
            rec.with_context(mortality_internal=True).write(
                {'state': 'rejected', 'rejection_reason': reason})
            rec.message_post(body=_("Rejected by %(user)s. Reason: %(reason)s",
                                    user=self.env.user.name, reason=reason))
            rec.activity_feedback([TODO], feedback=_("Rejected: %s", reason))
        self._recheck_waiting_logs(_("the rejection"))

    def _do_reverse(self, reason):
        self._check_manager()
        if not (reason or '').strip():
            raise UserError(_("A reversal reason is required."))
        for rec in self:
            if rec.state != 'done' or not rec.scrap_move_id:
                raise UserError(_("Only scrapped logs can be reversed."))
            rec._lock_cage()
            scrap = rec.scrap_move_id
            qty = scrap.quantity
            move = self.env['stock.move'].create({
                'product_id': rec.bird_product_id.id,
                'uom_id': scrap.uom_id.id,
                'product_uom_qty': qty,
                'location_id': scrap.location_dest_id.id,
                'location_dest_id': rec.cage_location_id.id,
                'origin': _("%s reversal", rec.name),
                # a move with no picking/scrap/inventory has an empty computed reference and the
                # journal-entry builder crashes on it; inventory_name feeds that reference
                'is_inventory': True,
                'inventory_name': _("%s reversal", rec.name),
                'farm_mortality_log_id': rec.id,
                'picked': True,
                'move_line_ids': [(0, 0, {
                    'product_id': rec.bird_product_id.id,
                    'uom_id': scrap.uom_id.id,
                    'quantity': qty,
                    'location_id': scrap.location_dest_id.id,
                    'location_dest_id': rec.cage_location_id.id,
                    'lot_id': rec.lot_id.id,
                })],
            })
            move._action_done()
            rec.with_context(mortality_internal=True).write(
                {'state': 'reversed', 'reversal_reason': reason, 'reversal_move_id': move.id})
            rec.message_post(body=_("Reversed by %(user)s. Reason: %(reason)s",
                                    user=self.env.user.name, reason=reason))
        self._recheck_waiting_logs(_("the reversal"))

    def _create_and_validate_scrap(self):
        self.ensure_one()
        location = self._get_scrap_location()
        if not location:
            raise UserError(_("No scrap location (usage 'Inventory adjustment') is configured."))
        # Odoo 20 has no stock.scrap document: a scrap is a stock move flagged is_scrap
        move = self.env['stock.move'].create({
            'product_id': self.bird_product_id.id,
            'uom_id': self.bird_product_id.uom_id.id,
            'product_uom_qty': self.dead_bird_count,
            'quantity': self.dead_bird_count,
            'location_id': self.cage_location_id.id,
            'location_dest_id': location.id,
            'lot_ids': [(6, 0, self.lot_id.ids)],
            'is_scrap': True,
            'origin': self.name,
            'company_id': self.company_id.id,
            'farm_mortality_log_id': self.id,
        })
        if not move.check_available_qty():
            raise UserError(_("The stock scrap could not be completed (insufficient stock)."))
        move._action_scrap()
        if move.state != 'done':
            raise UserError(_("The stock scrap could not be completed (insufficient stock)."))
        self.scrap_move_id = move

    # Buttons opening the reason wizard
    def action_open_reject(self):
        return self._open_wizard('reject')

    def action_open_reverse(self):
        return self._open_wizard('reverse')

    def _open_wizard(self, action):
        self._check_manager()
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Reject Mortality") if action == 'reject' else _("Reverse Mortality"),
            'res_model': 'farm.mortality.action.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_log_id': self.id, 'default_action': action},
        }

    def action_view_scrap(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'stock.move',
                'res_id': self.scrap_move_id.id, 'view_mode': 'form',
                'views': [(self.env.ref('stock.view_scrap_move_form').id, 'form')]}
