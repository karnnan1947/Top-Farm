# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import _, api, Command, fields, models
from odoo.exceptions import UserError


class FarmCageAllocationWizard(models.TransientModel):
    _name = 'farm.cage.allocation.wizard'
    _description = 'Allocate Birds of a Batch to its Cages'

    batch_location_id = fields.Many2one(
        'stock.location', string='Flock Batch', required=True, readonly=True,
        domain="[('farm_hierarchy_level', '=', 'batch')]")
    company_id = fields.Many2one(related='batch_location_id.company_id')
    product_id = fields.Many2one(
        'product.product', string='Bird Product', required=True, domain="[('is_farm_bird', '=', True)]")
    tracking = fields.Selection(related='product_id.tracking')
    available_lot_ids = fields.Many2many('stock.lot', compute='_compute_available_lots')
    lot_id = fields.Many2one(
        'stock.lot', string='Batch Lot', domain="[('id', 'in', available_lot_ids)]",
        help="The lot the birds arrived with. It is kept: no new lot is created for a cage.")
    available_qty = fields.Float(
        string='Available in the Batch Location', readonly=True, digits='Product Unit',
        help="Free birds of this product and lot in the batch location itself (not in the cages).")
    line_ids = fields.One2many('farm.cage.allocation.wizard.line', 'wizard_id', string='Cages')
    allocated_qty = fields.Float(string='To Allocate', compute='_compute_totals', digits='Product Unit')
    remaining_qty = fields.Float(string='Remaining', compute='_compute_totals', digits='Product Unit')

    # ------------------------------------------------------------------ defaults and computes
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        context = self.env.context
        batch = self.env['stock.location'].browse(
            res.get('batch_location_id') or context.get('default_batch_location_id') or context.get('active_id'))
        if batch.exists() and batch.farm_hierarchy_level == 'batch':
            res['batch_location_id'] = batch.id
            quants = self.env['stock.quant'].search([
                ('location_id', '=', batch.id), ('product_id.is_farm_bird', '=', True), ('quantity', '>', 0)])
            if len(quants.product_id) == 1:
                res['product_id'] = quants.product_id.id
                if len(quants.lot_id) == 1:
                    res['lot_id'] = quants.lot_id.id
                res['available_qty'] = self._available_for(
                    batch, quants.product_id, quants.lot_id if len(quants.lot_id) == 1 else self.env['stock.lot'])
            cages = self.env['stock.location'].search([
                ('parent_batch_location_id', '=', batch.id), ('farm_hierarchy_level', '=', 'cage')])
            res['line_ids'] = [Command.create({'cage_location_id': cage.id, 'quantity': 0.0}) for cage in cages]
        return res

    @api.depends('batch_location_id', 'product_id')
    def _compute_available_lots(self):
        for wiz in self:
            quants = self.env['stock.quant'].search([
                ('location_id', '=', wiz.batch_location_id.id), ('product_id', '=', wiz.product_id.id),
                ('quantity', '>', 0), ('lot_id', '!=', False)]) if wiz.batch_location_id and wiz.product_id \
                else self.env['stock.quant']
            wiz.available_lot_ids = quants.lot_id

    def _available_for(self, batch, product, lot):
        """Free quantity of the product (and lot) in the batch location itself, never in its cages."""
        # while the form is open the records are temporary copies (NewId): the stock query needs the real ones
        batch, product, lot = batch._origin, product._origin, lot._origin
        if not batch:    # while the form opens, the handlers run before the batch is set on the new record
            batch = self.env['stock.location'].browse(self.env.context.get('default_batch_location_id'))
        if not (batch and product):
            return 0.0
        return self.env['stock.quant']._get_available_quantity(product, batch, lot_id=lot or None, strict=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:    # the figure is read-only on screen, so it is never sent: always recompute it
            vals['available_qty'] = self._available_for(
                self.env['stock.location'].browse(vals.get('batch_location_id')),
                self.env['product.product'].browse(vals.get('product_id')),
                self.env['stock.lot'].browse(vals.get('lot_id')))
        return super().create(vals_list)

    @api.depends('line_ids.quantity', 'available_qty')
    def _compute_totals(self):
        for wiz in self:
            wiz.allocated_qty = sum(wiz.line_ids.mapped('quantity'))
            wiz.remaining_qty = wiz.available_qty - wiz.allocated_qty

    @api.onchange('product_id')
    def _onchange_product_id(self):
        lots = self.available_lot_ids
        self.lot_id = lots if len(lots) == 1 else False
        self.available_qty = self._available_for(self.batch_location_id, self.product_id, self.lot_id)

    @api.onchange('lot_id')
    def _onchange_lot_id(self):
        self.available_qty = self._available_for(self.batch_location_id, self.product_id, self.lot_id)

    # ------------------------------------------------------------------ actions
    def action_split_equally(self):
        """Share the available birds over the cages; the remainder goes to the first cages."""
        self.ensure_one()
        lines = self.line_ids
        if not lines:
            raise UserError(_("This batch has no cages yet. Create the cages under the batch first."))
        total = int(self._available_for(self.batch_location_id, self.product_id, self.lot_id))
        base, extra = divmod(total, len(lines))
        for index, line in enumerate(lines):
            line.quantity = base + (1 if index < extra else 0)
        return {
            'type': 'ir.actions.act_window', 'name': _("Allocate Birds to Cages"),
            'res_model': self._name, 'res_id': self.id, 'view_mode': 'form', 'target': 'new',
        }

    def action_allocate(self):
        self.ensure_one()
        batch, product, lot = self.batch_location_id, self.product_id, self.lot_id
        if batch.farm_hierarchy_level != 'batch':
            raise UserError(_("Birds are allocated from a 'Batch / Flock' location."))
        if product.tracking == 'lot' and not lot:
            raise UserError(_("Choose the batch lot the birds arrived with."))
        per_cage = defaultdict(float)
        for line in self.line_ids:
            if line.quantity < 0:
                raise UserError(_("Quantities cannot be negative."))
            if line.quantity:
                per_cage[line.cage_location_id] += line.quantity
        if not per_cage:
            raise UserError(_("Enter the number of birds for at least one cage."))
        for cage in per_cage:
            if cage.farm_hierarchy_level != 'cage' or cage.parent_batch_location_id != batch:
                raise UserError(_("%(cage)s is not a cage of batch %(batch)s.",
                                  cage=cage.display_name, batch=batch.display_name))
        total = sum(per_cage.values())
        available = self._available_for(batch, product, lot)
        if product.uom_id.compare(total, available) > 0:
            raise UserError(_(
                "Only %(available)s birds of %(product)s are available in %(batch)s, not %(total)s.",
                available=available, product=product.display_name, batch=batch.display_name, total=total))
        warehouse = batch.warehouse_id or self.env['stock.warehouse'].search(
            [('company_id', '=', batch.company_id.id)], limit=1)
        if not warehouse.int_type_id:
            raise UserError(_("No internal transfer operation type found for %s.", batch.company_id.name))
        for cage, qty in per_cage.items():
            self._move_birds(warehouse.int_type_id, batch, cage, product, lot, qty)
        batch.message_post(body=_(
            "%(user)s allocated %(total)s %(product)s%(lot)s to the cages: %(detail)s.",
            user=self.env.user.name, total=f"{total:g}", product=product.display_name,
            lot=_(" (lot %s)", lot.name) if lot else '',
            detail=", ".join(f"{cage.name} {qty:g}" for cage, qty in per_cage.items())),
            subtype_xmlid='mail.mt_note')
        return {'type': 'ir.actions.act_window_close'}

    def _move_birds(self, picking_type, batch, cage, product, lot, qty):
        """One validated internal transfer batch location to cage, on the chosen lot only."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': batch.id,
            'location_dest_id': cage.id,
            'origin': _("Allocation of %s", batch.display_name),
            'company_id': batch.company_id.id,
            'move_ids': [Command.create({
                'product_id': product.id,
                'uom_id': product.uom_id.id,
                'product_uom_qty': qty,
                'location_id': batch.id,
                'location_dest_id': cage.id,
                'company_id': batch.company_id.id,
            })],
        })
        picking.action_confirm()
        move = picking.move_ids
        move.move_line_ids.unlink()      # never let Odoo reserve another lot of the batch
        self.env['stock.move.line'].create({
            'move_id': move.id, 'picking_id': picking.id, 'product_id': product.id,
            'lot_id': lot.id if lot else False, 'quantity': qty,
            'location_id': batch.id, 'location_dest_id': cage.id,
        })
        move.picked = True
        picking.with_context(skip_backorder=True, skip_sms=True).button_validate()
        if picking.state != 'done':
            raise UserError(_("The transfer %s could not be validated automatically.", picking.name))


class FarmCageAllocationWizardLine(models.TransientModel):
    _name = 'farm.cage.allocation.wizard.line'
    _description = 'Birds to allocate to one cage'

    wizard_id = fields.Many2one('farm.cage.allocation.wizard', required=True, ondelete='cascade')
    cage_location_id = fields.Many2one(
        'stock.location', string='Cage', required=True, domain="[('farm_hierarchy_level', '=', 'cage')]")
    quantity = fields.Float(string='Birds', digits='Product Unit', default=0.0)
