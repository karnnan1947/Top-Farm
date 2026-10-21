# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import _, api, Command, fields, models
from odoo.exceptions import UserError


class FarmCageAllocationWizard(models.TransientModel):
    _name = 'farm.cage.allocation.wizard'
    _description = 'Allocate a Flock from its Brooding Nursery to Cages'

    brooding_location_id = fields.Many2one(
        'stock.location', string='Brooding Nursery', required=True, readonly=True,
        domain="[('farm_hierarchy_level', '=', 'brooding')]")
    farm_location_id = fields.Many2one(related='brooding_location_id.parent_farm_location_id', string='Farm')
    company_id = fields.Many2one(related='brooding_location_id.company_id')
    available_lot_ids = fields.Many2many('stock.lot', compute='_compute_available_lots')
    lot_id = fields.Many2one(
        'stock.lot', string='Flock Lot', required=True, domain="[('id', 'in', available_lot_ids)]",
        help="The flock lot is kept: the birds keep their flock number in the cages.")
    product_id = fields.Many2one(related='lot_id.product_id', string='Bird Product')
    available_qty = fields.Float(
        string='Live Birds in Brooding', compute='_compute_available_qty', digits='Product Unit',
        help="Free birds of this flock in the brooding nursery.")
    line_ids = fields.One2many('farm.cage.allocation.wizard.line', 'wizard_id', string='Cages')
    allocated_qty = fields.Float(string='To Allocate', compute='_compute_totals', digits='Product Unit')
    remaining_qty = fields.Float(string='Remaining', compute='_compute_totals', digits='Product Unit')

    # ------------------------------------------------------------------ defaults and computes
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        context = self.env.context
        brooding = self.env['stock.location'].browse(
            res.get('brooding_location_id') or context.get('default_brooding_location_id') or context.get('active_id'))
        if brooding.exists() and brooding.farm_hierarchy_level == 'brooding':
            res['brooding_location_id'] = brooding.id
            lots = brooding._get_flock_lots()
            if not res.get('lot_id') and len(lots) == 1:
                res['lot_id'] = lots.id
            cages = self.env['stock.location'].search([
                ('parent_farm_location_id', '=', brooding.parent_farm_location_id.id),
                ('farm_hierarchy_level', '=', 'cage')], order='complete_name')
            res['line_ids'] = [Command.create({'cage_location_id': cage.id, 'quantity': 0.0}) for cage in cages]
        return res

    @api.depends('brooding_location_id')
    def _compute_available_lots(self):
        for wiz in self:
            brooding = wiz.brooding_location_id._origin
            wiz.available_lot_ids = brooding._get_flock_lots() if brooding else False

    def _available_for(self, brooding, lot):
        """Free birds of the flock in the brooding nursery itself."""
        # while the form is open the records are temporary copies (NewId): the stock query needs the real ones
        brooding, lot = brooding._origin, lot._origin
        if not (brooding and lot):
            return 0.0
        return self.env['stock.quant']._get_available_quantity(lot.product_id, brooding, lot_id=lot, strict=True)

    @api.depends('brooding_location_id', 'lot_id')
    def _compute_available_qty(self):
        for wiz in self:
            wiz.available_qty = self._available_for(wiz.brooding_location_id, wiz.lot_id)

    @api.depends('line_ids.quantity', 'available_qty')
    def _compute_totals(self):
        for wiz in self:
            wiz.allocated_qty = sum(wiz.line_ids.mapped('quantity'))
            wiz.remaining_qty = wiz.available_qty - wiz.allocated_qty

    # ------------------------------------------------------------------ actions
    def _reopen(self):
        return {
            'type': 'ir.actions.act_window', 'name': _("Allocate Flock to Cages"),
            'res_model': self._name, 'res_id': self.id, 'view_mode': 'form', 'target': 'new',
        }

    def action_split_equally(self):
        """Share the birds over the free cages of the list; the remainder goes to the first cages."""
        self.ensure_one()
        lines = self.line_ids.filtered(lambda l: not l.other_flock_ids)
        if not lines:
            raise UserError(_("This farm has no free cage. Create the cages under the farm, or empty them first."))
        total = int(self._available_for(self.brooding_location_id, self.lot_id))
        base, extra = divmod(total, len(lines))
        for index, line in enumerate(lines):
            line.quantity = base + (1 if index < extra else 0)
        return self._reopen()

    def action_allocate(self):
        self.ensure_one()
        brooding, lot = self.brooding_location_id, self.lot_id
        if brooding.farm_hierarchy_level != 'brooding':
            raise UserError(_("Birds are allocated from a 'Brooding Nursery'."))
        if not lot.is_flock_batch:
            raise UserError(_("Choose the flock lot to allocate."))
        per_cage = defaultdict(float)
        for line in self.line_ids:
            if line.quantity < 0:
                raise UserError(_("Quantities cannot be negative."))
            if line.quantity:
                per_cage[line.cage_location_id] += line.quantity
        if not per_cage:
            raise UserError(_("Enter the number of birds for at least one cage."))
        for cage in per_cage:
            if cage.farm_hierarchy_level != 'cage' or cage.parent_farm_location_id != brooding.parent_farm_location_id:
                raise UserError(_("%(cage)s is not a cage of farm %(farm)s.",
                                  cage=cage.display_name, farm=brooding.parent_farm_location_id.display_name))
            # one flock per cage: egg collections and cage costs are charged to the flock living in the cage
            other = cage._get_flock_lots() - lot
            if other:
                raise UserError(_("Cage %(cage)s still holds flock %(flock)s. Deplete and sanitize it first.",
                                  cage=cage.display_name, flock=", ".join(other.mapped('name'))))
        total = sum(per_cage.values())
        product = lot.product_id
        available = self._available_for(brooding, lot)
        if product.uom_id.compare(total, available) > 0:
            raise UserError(_(
                "Only %(available)s birds of flock %(lot)s are available in %(brooding)s, not %(total)s.",
                available=available, lot=lot.name, brooding=brooding.display_name, total=total))
        warehouse = brooding.warehouse_id or self.env['stock.warehouse'].search(
            [('company_id', '=', brooding.company_id.id)], limit=1)
        if not warehouse.int_type_id:
            raise UserError(_("No internal transfer operation type found for %s.", brooding.company_id.name))
        picking = self._move_birds(warehouse.int_type_id, brooding, lot, per_cage)
        lot._advance_to_rearing()
        lot.message_post(body=_(
            "%(user)s allocated %(total)s birds from %(brooding)s to the cages (%(picking)s): %(detail)s. "
            "%(left)s birds remain in brooding.",
            user=self.env.user.name, total=f"{total:g}", brooding=brooding.display_name, picking=picking.name,
            detail=", ".join(f"{cage.name} {qty:g}" for cage, qty in per_cage.items()),
            left=f"{available - total:g}"),
            subtype_xmlid='mail.mt_note')
        return {'type': 'ir.actions.act_window_close'}

    def _move_birds(self, picking_type, brooding, lot, per_cage):
        """One validated internal transfer from the nursery to the cages, on the flock lot only."""
        product = lot.product_id
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': brooding.id,
            'location_dest_id': brooding.parent_farm_location_id.id,
            'origin': _("Cage allocation of %s", lot.name),
            'company_id': brooding.company_id.id,
            'move_ids': [Command.create({
                'product_id': product.id,
                'uom_id': product.uom_id.id,
                'product_uom_qty': qty,
                'location_id': brooding.id,
                'location_dest_id': cage.id,
                'company_id': brooding.company_id.id,
            }) for cage, qty in per_cage.items()],
        })
        picking.action_confirm()
        for move in picking.move_ids:
            move.move_line_ids.unlink()      # never let Odoo reserve another lot of the nursery
            self.env['stock.move.line'].create({
                'move_id': move.id, 'picking_id': picking.id, 'product_id': product.id,
                'lot_id': lot.id, 'quantity': move.product_uom_qty,
                'location_id': brooding.id, 'location_dest_id': move.location_dest_id.id,
            })
        picking.move_ids.picked = True
        picking.with_context(skip_backorder=True, skip_sms=True).button_validate()
        if picking.state != 'done':
            raise UserError(_("The transfer %s could not be validated automatically.", picking.name))
        return picking


class FarmCageAllocationWizardLine(models.TransientModel):
    _name = 'farm.cage.allocation.wizard.line'
    _description = 'Birds to allocate to one cage'

    wizard_id = fields.Many2one('farm.cage.allocation.wizard', required=True, ondelete='cascade')
    cage_location_id = fields.Many2one(
        'stock.location', string='Cage', required=True, domain="[('farm_hierarchy_level', '=', 'cage')]")
    current_bird_count = fields.Integer(string='Birds Now', compute='_compute_occupancy')
    other_flock_ids = fields.Many2many('stock.lot', string='Occupied By', compute='_compute_occupancy')
    quantity = fields.Float(string='Birds', digits='Product Unit', default=0.0)

    @api.depends('cage_location_id', 'wizard_id.lot_id')
    def _compute_occupancy(self):
        for line in self:
            cage = line.cage_location_id._origin
            line.current_bird_count = cage.get_live_bird_count() if cage else 0
            line.other_flock_ids = (cage._get_flock_lots() - line.wizard_id.lot_id._origin) if cage else False
