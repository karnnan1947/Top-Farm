# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_date

_logger = logging.getLogger(__name__)


class FarmFeedLog(models.Model):
    _name = 'farm.feed.log'
    _description = 'Daily Feed & Medication Log'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Log Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    company_id = fields.Many2one('res.company', required=True, index=True, default=lambda self: self.env.company)
    date = fields.Date(string='Feeding Date', required=True, default=fields.Date.context_today, tracking=True)
    location_id = fields.Many2one(
        'stock.location', string='Brooding / Cage', required=True, tracking=True, check_company=True, index=True,
        domain="[('farm_hierarchy_level', 'in', ('brooding', 'cage')), ('quant_ids.lot_id', '=?', flock_lot_id)]",
        help="Brooding nursery (weeks 0-4) or cage the feed and medication were given in."
    )
    flock_lot_id = fields.Many2one(
        'stock.lot', string='Flock Lot', required=True, tracking=True, index=True,
        compute='_compute_flock_lot', store=True, readonly=False, precompute=True,
        domain="[('is_flock_batch', '=', True), ('flock_stage', '!=', 'spent'), ('quant_ids.location_id', '=?', location_id)]",
        help="Flock fed. Filled with the flock living in the brooding nursery or cage; its analytic account "
             "carries the cost."
    )
    farm_location_id = fields.Many2one(
        related='location_id.parent_farm_location_id', string='Farm', store=True, index=True)
    feeding_phase = fields.Selection([
        ('pre_laying', 'Pre-Laying (Direct Expense)'),
        ('laying', 'Laying Phase (Staged for Egg Harvest)'),
    ], string='Feeding Phase', compute='_compute_feeding_phase', store=True, tracking=True,
       help="Brooding and rearing feed is a direct expense of the flock. Once the flock is in the Laying Phase, "
            "cage feed is staged for the day's egg harvest. Follows the flock while the log is a draft and is "
            "fixed when it is confirmed, so a later stage change never rewrites how past feed was accounted for.")

    line_ids = fields.One2many('farm.feed.log.line', 'log_id', string='Feed & Medication Lines', copy=True)
    total_feed_qty = fields.Float(string='Total Feed (kg)', compute='_compute_totals', store=True, digits='Product Unit')
    total_med_qty = fields.Float(string='Total Medication', compute='_compute_totals', store=True, digits='Product Unit')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed (Staged)'),
        ('reconciled', 'Reconciled / Produced'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False, index=True)

    picking_ids = fields.One2many('stock.picking', 'farm_feed_log_id', string='Consumption Transfers', readonly=True)
    picking_count = fields.Integer(compute='_compute_picking_count')
    egg_collection_id = fields.Many2one('farm.egg.collection', string='Linked Egg Collection', readonly=True, copy=False)

    # -------------------------------------------------------------------------
    # CRUD / COMPUTE
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('farm.feed.log') or _('New')
        return super().create(vals_list)

    def unlink(self):
        if any(log.state not in ('draft', 'cancelled') for log in self):
            raise UserError(_("Only draft or cancelled feed logs can be deleted."))
        return super().unlink()

    @api.depends('location_id')
    def _compute_flock_lot(self):
        for log in self:
            location = log.location_id._origin
            flocks = location._get_flock_lots() if location else self.env['stock.lot']
            log.flock_lot_id = flocks if len(flocks) == 1 else log.flock_lot_id

    @api.depends('flock_lot_id.flock_stage', 'location_id.farm_hierarchy_level', 'state')
    def _compute_feeding_phase(self):
        for log in self:
            if log.state == 'draft':
                laying = log.flock_lot_id.flock_stage == 'laying' and log.location_id.farm_hierarchy_level == 'cage'
                log.feeding_phase = 'laying' if laying else 'pre_laying'
            else:
                log.feeding_phase = log.feeding_phase

    @api.depends('line_ids.quantity', 'line_ids.is_medication', 'line_ids.product_id')
    def _compute_totals(self):
        kg = self.env.ref('uom.product_uom_kgm')
        for log in self:
            feed_lines = log.line_ids.filtered(lambda l: not l.is_medication)
            log.total_feed_qty = sum(line._get_qty_in(kg) for line in feed_lines)
            log.total_med_qty = sum((log.line_ids - feed_lines).mapped('quantity'))

    @api.depends('picking_ids')
    def _compute_picking_count(self):
        for log in self:
            log.picking_count = len(log.picking_ids)

    @api.constrains('location_id', 'flock_lot_id')
    def _check_location_and_flock(self):
        for log in self:
            if log.location_id.farm_hierarchy_level not in ('brooding', 'cage'):
                raise ValidationError(_("%s is neither a brooding nursery nor a cage.", log.location_id.display_name))
            if not log.flock_lot_id.is_flock_batch:
                raise ValidationError(_("%s is not a flock lot.", log.flock_lot_id.display_name))

    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------
    def action_confirm(self):
        for log in self:
            if log.state != 'draft':
                raise UserError(_("Only draft feed logs can be confirmed."))
            if not log.line_ids:
                raise UserError(_("Please add at least one feed or medication line before confirming."))
            if not log.location_id.get_live_bird_count(log.flock_lot_id):
                raise UserError(_("Flock %(flock)s has no live birds in %(location)s.",
                                  flock=log.flock_lot_id.name, location=log.location_id.display_name))
            med_lines = log.line_ids.filtered('is_medication')
            feed_lines = log.line_ids - med_lines
            staged = log.feeding_phase == 'laying' and feed_lines
            consume_now = med_lines if staged else log.line_ids
            log._check_availability(consume_now)
            if med_lines:
                log._consume(med_lines, log.company_id.farm_medication_consumption_location_id)
            if feed_lines and not staged:
                log._consume(feed_lines, log.company_id.farm_feed_consumption_location_id)
            log.state = 'confirmed' if staged else 'reconciled'
        return True

    def action_cancel(self):
        if any(log.state not in ('draft', 'confirmed') or log.picking_ids for log in self):
            raise UserError(_("Only draft logs, or staged logs with no stock moved yet, can be cancelled."))
        self.state = 'cancelled'
        return True

    def action_draft(self):
        if any(log.state != 'cancelled' for log in self):
            raise UserError(_("Only cancelled feed logs can be reset to draft."))
        self.state = 'draft'
        return True

    def action_view_pickings(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('stock.action_picking_tree_all')
        action['domain'] = [('id', 'in', self.picking_ids.ids)]
        action['context'] = {'create': False}
        if len(self.picking_ids) == 1:
            action.update(views=[(False, 'form')], res_id=self.picking_ids.id)
        return action

    # -------------------------------------------------------------------------
    # STOCK CONSUMPTION
    # -------------------------------------------------------------------------
    def _check_availability(self, lines):
        """Refuse to consume more than the silo / store holds, before any stock is moved."""
        shortages = []
        for (product, source), group in lines.grouped(lambda l: (l.product_id, l.source_location_id)).items():
            needed = sum(line._get_qty_in(product.uom_id) for line in group)
            available = product.with_context(location=source.id).free_qty
            if product.is_storable and product.uom_id.compare(available, needed) < 0:
                shortages.append(_("%(product)s in %(location)s: %(needed)s %(uom)s needed, %(available)s available",
                                   product=product.display_name, location=source.display_name, needed=needed,
                                   available=available, uom=product.uom_id.name))
        if shortages:
            raise UserError(_("Not enough stock to record this feeding:\n%s", "\n".join(shortages)))

    def _get_consumption_picking_type(self):
        self.ensure_one()
        warehouse = self.location_id.warehouse_id or self.env['stock.warehouse'].search(
            [('company_id', '=', self.company_id.id)], limit=1)
        if not warehouse.int_type_id:
            raise UserError(_("No internal transfer operation type found for %s.", self.company_id.name))
        return warehouse.int_type_id

    def _consume(self, lines, destination):
        """Post validated transfers from each source silo / store to a consumption location.
        Every move carries the flock and its brooding nursery or cage, so top_farm_core charges it to the
        Flock account (and the Cage account in a cage)."""
        self.ensure_one()
        if not destination:
            raise UserError(_("Set the Feed and Medication Consumption locations in Top Farm > Farm "
                              "Configuration > Settings first."))
        picking_type = self._get_consumption_picking_type()
        for source, group in lines.grouped('source_location_id').items():
            picking = self.env['stock.picking'].create({
                'picking_type_id': picking_type.id,
                'location_id': source.id,
                'location_dest_id': destination.id,
                'origin': self.name,
                'farm_feed_log_id': self.id,
                'company_id': self.company_id.id,
                'move_ids': [Command.create({
                    'product_id': line.product_id.id,
                    'uom_id': line.uom_id.id,
                    'product_uom_qty': line.quantity,
                    'location_id': source.id,
                    'location_dest_id': destination.id,
                    'farm_location_id': self.location_id.id,
                    'farm_flock_lot_id': self.flock_lot_id.id,
                    'company_id': self.company_id.id,
                }) for line in group],
            })
            picking.action_confirm()
            picking.action_assign()
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
            picking.move_ids.picked = True
            if picking.button_validate() is not True or picking.state != 'done':
                raise UserError(_("The consumption transfer %s could not be validated automatically.", picking.name))

    @api.model
    def _cron_reconcile_unharvested_feed(self):
        """Expense laying feed that no egg collection consumed, once its day is over."""
        logs = self.search([
            ('state', '=', 'confirmed'),
            ('feeding_phase', '=', 'laying'),
            ('date', '<', fields.Date.context_today(self)),
        ])
        for log in logs:
            try:
                with self.env.cr.savepoint():
                    log._flush_unharvested_feed()
            except UserError as error:
                # One silo short of stock must not block every other cage; tell the farm on the log
                _logger.warning("Top Farm: could not expense unharvested feed of %s: %s", log.name, error)
                log.message_post(body=_("The staged feed could not be expensed automatically: %s", error))

    def _flush_unharvested_feed(self):
        self.ensure_one()
        feed_lines = self.line_ids.filtered(lambda l: not l.is_medication)
        if feed_lines:
            self._check_availability(feed_lines)
            self._consume(feed_lines, self.company_id.farm_feed_consumption_location_id)
        self.state = 'reconciled'
        self.message_post(body=_(
            "No egg harvest was recorded for this cage on %(date)s. The staged feed (%(qty)s kg) has been "
            "expensed to the flock as maintenance feed.",
            date=format_date(self.env, self.date), qty=self.total_feed_qty,
        ))


class FarmFeedLogLine(models.Model):
    _name = 'farm.feed.log.line'
    _description = 'Feed & Medication Line'
    _check_company_auto = True

    log_id = fields.Many2one('farm.feed.log', string='Feed Log Reference', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='log_id.company_id', store=True)
    product_id = fields.Many2one(
        'product.product', string='Product', required=True, check_company=True,
        domain="[('farm_input_type', '!=', False)]")
    is_medication = fields.Boolean(string='Is Medication', compute='_compute_is_medication', store=True)
    source_location_id = fields.Many2one(
        'stock.location', string='Source Silo / Store', required=True, check_company=True,
        domain="[('usage', '=', 'internal')]")
    quantity = fields.Float(string='Quantity', required=True, digits='Product Unit')
    uom_id = fields.Many2one('uom.uom', string='UoM', related='product_id.uom_id', readonly=True)

    @api.depends('product_id.farm_input_type')
    def _compute_is_medication(self):
        for line in self:
            line.is_medication = line.product_id.farm_input_type == 'medication'

    @api.constrains('quantity', 'product_id')
    def _check_line(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_("Quantities on a feed log must be positive."))
            if not line.product_id.farm_input_type:
                raise ValidationError(_("%s is not a farm feed or medication product (set its Farm Input Type).",
                                        line.product_id.display_name))

    def _get_qty_in(self, uom):
        """Line quantity in `uom` when both units share a reference (e.g. bags of 50 kg into kg)."""
        self.ensure_one()
        if self.uom_id._has_common_reference(uom):
            return self.uom_id._compute_quantity(self.quantity, uom, round=False)
        return self.quantity
