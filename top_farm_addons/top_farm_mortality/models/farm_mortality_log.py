from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

MANAGER_GROUP = 'top_farm_mortality.group_mortality_manager'
TODO = 'mail.mail_activity_data_todo'

# Fields that may only be changed by the module's own methods (context flag below).
PROTECTED_FIELDS = {
    'state', 'opening_population', 'cumulative_dead', 'mortality_pct', 'threshold_pct_used',
    'requires_approval', 'approved_by_id', 'approved_date', 'scrap_id', 'reversal_move_id',
    'rejection_reason', 'reversal_reason',
}
SNAPSHOT_FIELDS = {'opening_population', 'cumulative_dead', 'mortality_pct',
                   'threshold_pct_used', 'requires_approval'}
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
    scrap_id = fields.Many2one('stock.scrap', string='Stock Scrap', readonly=True, copy=False)
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

    def _snapshot_vals(self):
        """Authoritative numbers for the threshold check (also used as draft preview)."""
        self.ensure_one()
        cfg = self.env['farm.mortality.config']._get_config(self.company_id)
        zero = {'opening_population': 0, 'cumulative_dead': 0, 'mortality_pct': 0.0,
                'threshold_pct_used': cfg.daily_mortality_threshold_pct, 'requires_approval': False}
        if not (self.cage_location_id and self.bird_product_id and self.date):
            return zero
        # Cage-level maths: live birds come from top_farm_core's count, dead from all logs of the cage.
        opening = (self.cage_location_id.get_live_bird_count()
                   + self._dead_sum(['done'], self.date, '>=', whole_cage=True))
        cumulative = (self._dead_sum(['done', 'waiting_approval'], self.date, '=', whole_cage=True)
                      + self.dead_bird_count)
        pct = cumulative / opening * 100.0 if opening else 0.0
        return {
            'opening_population': opening,
            'cumulative_dead': cumulative,
            'mortality_pct': round(pct, 2),
            'threshold_pct_used': cfg.daily_mortality_threshold_pct,
            'requires_approval': bool(
                pct > cfg.daily_mortality_threshold_pct and cumulative > cfg.min_dead_count),
        }

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
        return True

    def _notify_managers(self, snap):
        self.ensure_one()
        managers = self._managers()
        body = _(
            "<b>Abnormal mortality:</b> %(cage)s reached <b>%(dead)s dead birds today (%(pct).2f%%)</b> "
            "of an opening population of %(pop)s, above the %(thr).2f%% threshold. "
            "Manager approval is required before stock is scrapped.",
            cage=self.cage_location_id.display_name, dead=snap['cumulative_dead'],
            pct=snap['mortality_pct'], pop=snap['opening_population'], thr=snap['threshold_pct_used'])
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

    def _do_reverse(self, reason):
        self._check_manager()
        if not (reason or '').strip():
            raise UserError(_("A reversal reason is required."))
        for rec in self:
            if rec.state != 'done' or not rec.scrap_id:
                raise UserError(_("Only scrapped logs can be reversed."))
            rec._lock_cage()
            scrap = rec.scrap_id
            move = self.env['stock.move'].create({
                'product_id': rec.bird_product_id.id,
                'product_uom': scrap.product_uom_id.id,
                'product_uom_qty': scrap.scrap_qty,
                'location_id': scrap.scrap_location_id.id,
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
                    'product_uom_id': scrap.product_uom_id.id,
                    'quantity': scrap.scrap_qty,
                    'location_id': scrap.scrap_location_id.id,
                    'location_dest_id': rec.cage_location_id.id,
                    'lot_id': rec.lot_id.id,
                })],
            })
            move._action_done()
            rec.with_context(mortality_internal=True).write(
                {'state': 'reversed', 'reversal_reason': reason, 'reversal_move_id': move.id})
            rec.message_post(body=_("Reversed by %(user)s. Reason: %(reason)s",
                                    user=self.env.user.name, reason=reason))

    def _create_and_validate_scrap(self):
        self.ensure_one()
        location = self._get_scrap_location()
        if not location:
            raise UserError(_("No scrap location (usage 'Inventory adjustment') is configured."))
        scrap = self.env['stock.scrap'].create({
            'product_id': self.bird_product_id.id,
            'scrap_qty': self.dead_bird_count,
            'product_uom_id': self.bird_product_id.uom_id.id,
            'location_id': self.cage_location_id.id,
            'scrap_location_id': location.id,
            'lot_id': self.lot_id.id,
            'origin': self.name,
            'company_id': self.company_id.id,
            'farm_mortality_log_id': self.id,
        })
        scrap.action_validate()
        if scrap.state != 'done':
            raise UserError(_("The stock scrap could not be completed (insufficient stock)."))
        self.scrap_id = scrap

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
        return {'type': 'ir.actions.act_window', 'res_model': 'stock.scrap',
                'res_id': self.scrap_id.id, 'view_mode': 'form'}
