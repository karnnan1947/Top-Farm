# -*- coding: utf-8 -*-
import re
from collections import defaultdict

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError

GRADES = ('large', 'medium', 'jumbo', 'damage')


class FarmEggCollection(models.Model):
    _name = 'farm.egg.collection'
    _description = 'Daily Graded Egg Collection & MO Engine'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Collection Ref', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    company_id = fields.Many2one('res.company', required=True, index=True, default=lambda self: self.env.company)
    date = fields.Date(string='Collection Date', required=True, default=fields.Date.context_today, tracking=True)
    cage_location_id = fields.Many2one(
        'stock.location', string='Cage Location', required=True, tracking=True, check_company=True, index=True,
        domain="[('farm_hierarchy_level', '=', 'cage'), ('quant_ids.lot_id', '=?', flock_lot_id)]"
    )
    flock_lot_id = fields.Many2one(
        'stock.lot', string='Flock Lot', required=True, tracking=True, index=True,
        compute='_compute_flock_lot', store=True, readonly=False, precompute=True,
        domain="[('is_flock_batch', '=', True), ('flock_stage', 'in', ('rearing', 'laying'))]",
        help="Flock living in the cage. The eggs are lotted under it and their revenue is reported to it."
    )
    farm_location_id = fields.Many2one(
        related='cage_location_id.parent_farm_location_id', string='Farm', store=True, index=True)
    destination_location_id = fields.Many2one(
        'stock.location', string='Egg Warehouse Location', required=True, check_company=True,
        compute='_compute_destination_location', store=True, readonly=False, precompute=True,
        domain="[('usage', '=', 'internal')]",
        help="Warehouse cold-room destination for graded eggs: the farm's Egg Store Location, "
             "else the company default from the Top Farm settings."
    )

    product_medium_id = fields.Many2one(
        'product.product', string='Medium Egg Product', check_company=True,
        default=lambda self: self.env.company.farm_egg_medium_product_id)
    product_large_id = fields.Many2one(
        'product.product', string='Large Egg Product', check_company=True,
        default=lambda self: self.env.company.farm_egg_large_product_id)
    product_jumbo_id = fields.Many2one(
        'product.product', string='Jumbo Egg Product', check_company=True,
        default=lambda self: self.env.company.farm_egg_jumbo_product_id)
    product_damage_id = fields.Many2one(
        'product.product', string='Damaged / Cracked Product', check_company=True,
        default=lambda self: self.env.company.farm_egg_damage_product_id)

    qty_medium = fields.Integer(string='Medium Eggs (qty)', default=0, tracking=True)
    qty_large = fields.Integer(string='Large Eggs (qty)', default=0, tracking=True)
    qty_jumbo = fields.Integer(string='Jumbo Eggs (qty)', default=0, tracking=True)
    qty_damage = fields.Integer(string='Damaged Eggs (qty)', default=0, tracking=True)
    total_egg_qty = fields.Integer(string='Total Eggs Collected', compute='_compute_total_eggs', store=True)

    confirmed_live_bird_count = fields.Integer(
        string='Live Birds Snapshot', readonly=True, copy=False,
        help="Permanent snapshot of the flock's live birds in the cage at collection time, for historical "
             "Hen-Day accuracy."
    )
    hen_day_rate = fields.Float(
        string='Hen-Day Rate (%)', compute='_compute_kpis', store=True, digits=(16, 2), aggregator='avg',
        help="(Total Eggs / Live Birds) * 100"
    )
    feed_log_ids = fields.Many2many(
        'farm.feed.log', string='Staged Feed Logs', copy=False, check_company=True,
        compute='_compute_feed_log_ids', store=True, readonly=False,
        domain="[('state', '=', 'confirmed'), ('feeding_phase', '=', 'laying'), ('location_id', '=', cage_location_id)]",
        help="Laying-phase feed staged for this cage. Filled with the cage's feed logs of the same day."
    )
    feed_consumed_qty = fields.Float(
        string='Feed Consumed (kg)', compute='_compute_feed_consumed', store=True, digits='Product Unit')
    fcr = fields.Float(
        string='FCR (kg/dozen)', compute='_compute_kpis', store=True, digits=(16, 3), aggregator='avg',
        help="kg of feed consumed per dozen eggs produced."
    )

    production_ids = fields.One2many('mrp.production', 'farm_collection_id', string='Manufacturing Orders', readonly=True)
    mo_count = fields.Integer(string='MO Count', compute='_compute_mo_count')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done / Produced'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False, index=True)

    # -------------------------------------------------------------------------
    # CRUD / COMPUTE
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('farm.egg.collection') or _('New')
        return super().create(vals_list)

    def unlink(self):
        if any(collection.state == 'done' for collection in self):
            raise UserError(_("Produced egg collections cannot be deleted."))
        return super().unlink()

    @api.depends('cage_location_id')
    def _compute_flock_lot(self):
        for rec in self:
            cage = rec.cage_location_id._origin
            flocks = cage._get_flock_lots() if cage else self.env['stock.lot']
            rec.flock_lot_id = flocks if len(flocks) == 1 else rec.flock_lot_id

    @api.depends('cage_location_id.parent_farm_location_id.farm_egg_location_id')
    def _compute_destination_location(self):
        for rec in self:
            rec.destination_location_id = (rec.cage_location_id.parent_farm_location_id.farm_egg_location_id
                                           or rec.company_id.farm_egg_location_id
                                           or rec.destination_location_id)

    @api.depends('qty_medium', 'qty_large', 'qty_jumbo', 'qty_damage')
    def _compute_total_eggs(self):
        for rec in self:
            rec.total_egg_qty = rec.qty_medium + rec.qty_large + rec.qty_jumbo + rec.qty_damage

    @api.depends('cage_location_id', 'date')
    def _compute_feed_log_ids(self):
        for rec in self:
            if rec.state == 'draft':
                rec.feed_log_ids = rec._find_staged_feed_logs()
            else:
                rec.feed_log_ids = rec.feed_log_ids

    @api.depends('feed_log_ids.total_feed_qty')
    def _compute_feed_consumed(self):
        for rec in self:
            rec.feed_consumed_qty = sum(rec.feed_log_ids.mapped('total_feed_qty'))

    @api.depends('total_egg_qty', 'confirmed_live_bird_count', 'feed_consumed_qty')
    def _compute_kpis(self):
        for rec in self:
            if rec.confirmed_live_bird_count > 0:
                rec.hen_day_rate = (rec.total_egg_qty / rec.confirmed_live_bird_count) * 100.0
            else:
                rec.hen_day_rate = 0.0

            dozen_eggs = rec.total_egg_qty / 12.0
            if dozen_eggs > 0:
                rec.fcr = round(rec.feed_consumed_qty / dozen_eggs, 3)
            else:
                rec.fcr = 0.0

    @api.depends('production_ids')
    def _compute_mo_count(self):
        for rec in self:
            rec.mo_count = len(rec.production_ids)

    @api.constrains('qty_medium', 'qty_large', 'qty_jumbo', 'qty_damage')
    def _check_quantities(self):
        for rec in self:
            if min(rec.qty_medium, rec.qty_large, rec.qty_jumbo, rec.qty_damage) < 0:
                raise ValidationError(_("Egg quantities cannot be negative."))

    @api.constrains('cage_location_id', 'flock_lot_id', 'date', 'state')
    def _check_one_collection_per_cage_and_day(self):
        for rec in self:
            if not rec.flock_lot_id.is_flock_batch:
                raise ValidationError(_("%s is not a flock lot.", rec.flock_lot_id.display_name))
            if rec.state != 'cancelled' and self.search_count([
                ('id', '!=', rec.id), ('cage_location_id', '=', rec.cage_location_id.id),
                ('date', '=', rec.date), ('state', '!=', 'cancelled'),
            ]):
                raise ValidationError(_("Cage %(cage)s already has an egg collection on %(date)s.",
                                        cage=rec.cage_location_id.display_name, date=rec.date))

    def _find_staged_feed_logs(self):
        self.ensure_one()
        if not self.cage_location_id or not self.date:
            return self.env['farm.feed.log']
        return self.env['farm.feed.log'].search([
            ('location_id', '=', self.cage_location_id.id),
            ('date', '=', self.date),
            ('state', '=', 'confirmed'),
            ('feeding_phase', '=', 'laying'),
        ])

    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------
    def action_cancel(self):
        if any(rec.state != 'draft' for rec in self):
            raise UserError(_("Only draft egg collections can be cancelled."))
        self.state = 'cancelled'
        return True

    def action_draft(self):
        if any(rec.state != 'cancelled' for rec in self):
            raise UserError(_("Only cancelled egg collections can be reset to draft."))
        self.state = 'draft'
        return True

    def action_view_mos(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('mrp.mrp_production_action')
        action['domain'] = [('farm_collection_id', '=', self.id)]
        action['context'] = {'create': False}
        return action

    def _get_grades(self):
        """(product, egg quantity) for every grade collected, largest quantity first."""
        self.ensure_one()
        grades = []
        for grade in GRADES:
            qty = self[f'qty_{grade}']
            if qty > 0:
                product = self[f'product_{grade}_id']
                if not product:
                    raise UserError(_("Choose the %s egg product (Top Farm > Farm Configuration > Settings) "
                                      "before producing.", self._fields[f'product_{grade}_id'].string))
                grades.append((product, qty))
        return sorted(grades, key=lambda grade: grade[1], reverse=True)

    def _allocate_feed(self, grades):
        """Split every staged feed line over the grades in proportion to their egg counts.
        Shares are rounded to the product's unit precision and the rounding residue goes to the
        largest grade, so the manufacturing orders consume exactly the staged quantity.
        Returns [[(product, source location, qty), ...] per grade]."""
        components = defaultdict(float)
        for line in self.feed_log_ids.line_ids.filtered(lambda l: not l.is_medication):
            components[line.product_id, line.source_location_id] += line._get_qty_in(line.product_id.uom_id)
        allocation = [[] for __ in grades]
        for (product, source), total in components.items():
            uom = product.uom_id
            total = uom.round(total)
            shares = [uom.round(total * qty / self.total_egg_qty) for __, qty in grades]
            shares[0] = uom.round(shares[0] + total - sum(shares))
            for index, share in enumerate(shares):
                if not uom.is_zero(share):
                    allocation[index].append((product, source, share))
        return allocation

    def _get_egg_lot(self, product):
        """Daily lot per flock: LOT-EGG-<flock lot>-<YYYYMMDD>, shared by all cages of the flock and stamped with
        its parent flock and production day (used for traceability and revenue reporting)."""
        self.ensure_one()
        if product.tracking == 'none':
            return self.env['stock.lot']
        flock_code = re.sub(r'[^A-Za-z0-9]+', '-', self.flock_lot_id.name).strip('-')
        name = f"LOT-EGG-{flock_code}-{self.date.strftime('%Y%m%d')}"
        Lot = self.env['stock.lot'].sudo()
        lot = Lot.search([('product_id', '=', product.id), ('name', '=', name),
                          ('company_id', '=', self.company_id.id)], limit=1) \
            or Lot.create({'product_id': product.id, 'name': name, 'company_id': self.company_id.id})
        if not lot.farm_flock_lot_id:
            lot.write({'farm_flock_lot_id': self.flock_lot_id.id, 'farm_production_date': self.date})
        return lot

    def action_generate_split_manufacturing_orders(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("This egg collection has already been processed."))
        if self.total_egg_qty <= 0:
            raise UserError(_("Cannot generate manufacturing orders for 0 eggs."))
        flock, cage = self.flock_lot_id, self.cage_location_id
        live_birds = cage.get_live_bird_count(flock)
        if not live_birds:
            raise UserError(_("Flock %(flock)s has no live birds in %(cage)s.", flock=flock.name, cage=cage.display_name))
        laying = flock.flock_stage == 'laying'
        self.feed_log_ids |= self._find_staged_feed_logs()
        if laying and (not self.feed_log_ids or self.feed_consumed_qty <= 0):
            raise UserError(_("No staged laying feed for %(cage)s on %(date)s. Log and confirm the day's feed "
                              "(Farm Operations > Daily Feed & Medication) first.",
                              cage=cage.display_name, date=self.date))
        if any(log.state != 'confirmed' for log in self.feed_log_ids):
            raise UserError(_("Some linked feed logs are no longer staged; refresh the Staged Feed Logs tab."))

        grades = self._get_grades()
        # Before the Laying Phase the feed is a direct expense of the flock: the first eggs carry no feed cost
        allocation = self._allocate_feed(grades) if self.feed_log_ids else [[] for __ in grades]
        feed_lines = self.feed_log_ids.line_ids.filtered(lambda l: not l.is_medication)
        if feed_lines:
            self.feed_log_ids[:1]._check_availability(feed_lines)
        self.confirmed_live_bird_count = live_birds

        warehouse = cage.warehouse_id or self.env['stock.warehouse'].search(
            [('company_id', '=', self.company_id.id)], limit=1)
        # Operators record collections but are not Manufacturing users: the orders are generated
        # by the system from the data validated above.
        Production = self.env['mrp.production'].sudo().with_company(self.company_id)
        productions = Production
        for (product, qty), components in zip(grades, allocation):
            production = Production.create({
                'product_id': product.id,
                'product_qty': qty,
                'uom_id': product.uom_id.id,
                'bom_id': False,
                'picking_type_id': warehouse.manu_type_id.id,
                'location_src_id': components[0][1].id if components else warehouse.lot_stock_id.id,
                'location_dest_id': self.destination_location_id.id,
                'lot_producing_ids': [Command.set(self._get_egg_lot(product).ids)],
                'origin': self.name,
                'farm_collection_id': self.id,
                'company_id': self.company_id.id,
                'move_raw_ids': [Command.create({
                    'product_id': feed.id,
                    'uom_id': feed.uom_id.id,
                    'product_uom_qty': feed_qty,
                    'location_id': source.id,
                    'farm_location_id': cage.id,
                    'farm_flock_lot_id': flock.id,
                }) for feed, source, feed_qty in components],
            })
            production.action_confirm()
            production.qty_producing = qty
            production._set_qty_producing()
            production.move_raw_ids.picked = True
            production.with_context(skip_redirection=True).button_mark_done()
            if production.state != 'done':
                raise UserError(_("Manufacturing order %s could not be completed automatically.", production.name))
            productions |= production

        self.state = 'done'
        self.feed_log_ids.write({'state': 'reconciled', 'egg_collection_id': self.id})
        if laying:
            body = _("Successfully generated and completed %(count)s graded Manufacturing Orders. "
                     "Total feed consumed: %(qty)s kg.", count=len(productions), qty=self.feed_consumed_qty)
        else:
            body = _("Successfully generated and completed %(count)s graded Manufacturing Orders. The flock is "
                     "still in Rearing / Pre-Laying: its feed is a direct flock expense, so these eggs carry no "
                     "feed cost.", count=len(productions))
        self.message_post(body=body)
        if not laying:
            flock._farm_check_laying_transition(self.date)
        return True
