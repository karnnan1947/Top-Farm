# -*- coding: utf-8 -*-
import re

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import format_amount, formatLang


class FarmBroilerHarvestWizard(models.TransientModel):
    _name = 'farm.broiler.harvest.wizard'
    _description = 'Broiler Harvest & Meat Conversion Wizard'

    flock_lot_id = fields.Many2one(
        'stock.lot', string='Broiler Batch', required=True, readonly=True,
        domain="[('flock_type', '=', 'broiler'), ('flock_stage', '=', 'growing')]")
    company_id = fields.Many2one('res.company', compute='_compute_company_id')
    currency_id = fields.Many2one('res.currency', compute='_compute_company_id')
    shed_location_ids = fields.Many2many('stock.location', compute='_compute_shed_location_ids')
    location_id = fields.Many2one(
        'stock.location', string='Broiler Shed', required=True, domain="[('id', 'in', shed_location_ids)]",
        help="Shed the birds are picked up from.")
    available_birds = fields.Integer(
        string='Live Birds Available', compute='_compute_available_birds',
        help="Free live birds of the batch in the shed.")
    birds_count = fields.Integer(string='Birds Harvested (Qty)', required=True)
    average_weight = fields.Float(
        string='Average Weight (kg)', digits=(16, 3), required=True,
        help="Average live weight per bird; the total net weight follows it.")
    total_weight_kg = fields.Float(
        string='Total Net Weight (kg)', digits=(16, 2), compute='_compute_total_weight_kg', store=True,
        readonly=False,
        help="Birds x average weight. Overwrite it with the weighbridge net weight: the meat is produced on it.")
    net_average_weight = fields.Float(
        string='Actual Avg Weight (kg)', digits=(16, 3), compute='_compute_net_average_weight',
        help="Total net weight / birds harvested.")
    harvest_cost = fields.Monetary(
        string='Batch Cost of These Birds', currency_field='currency_id', compute='_compute_amounts',
        help="Their share of the batch value in the shed (chicks plus capitalized feed, medication and "
             "mortality): it becomes the stock value of the meat.")
    cost_per_kg = fields.Monetary(string='Meat Cost / kg', currency_field='currency_id', compute='_compute_amounts')
    remaining_birds = fields.Integer(string='Birds Left in Batch', compute='_compute_amounts')

    # Optional fields preserved for backward compatibility
    partner_id = fields.Many2one('res.partner', string='Customer / Buyer', required=False)
    price_per_kg = fields.Monetary(string='Price / kg', currency_field='currency_id', required=False)
    total_sale_amount = fields.Monetary(
        string='Total Sale Revenue', currency_field='currency_id', compute='_compute_amounts')
    estimated_margin = fields.Monetary(
        string='Estimated Margin', currency_field='currency_id', compute='_compute_amounts')

    # ------------------------------------------------------------------ defaults and computes
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        lot = self.env['stock.lot'].browse(res.get('flock_lot_id'))
        if lot.exists() and not res.get('location_id'):
            sheds = lot.flock_location_ids
            if len(sheds) == 1:
                res['location_id'] = sheds.id
        return res

    @api.depends('flock_lot_id')
    def _compute_company_id(self):
        for wizard in self:
            wizard.company_id = wizard.flock_lot_id.company_id or self.env.company
            wizard.currency_id = wizard.company_id.currency_id

    @api.depends('flock_lot_id')
    def _compute_shed_location_ids(self):
        for wizard in self:
            wizard.shed_location_ids = wizard.flock_lot_id._origin.flock_location_ids

    @api.depends('flock_lot_id', 'location_id')
    def _compute_available_birds(self):
        for wizard in self:
            lot, shed = wizard.flock_lot_id._origin, wizard.location_id._origin
            wizard.available_birds = round(self.env['stock.quant']._get_available_quantity(
                lot.product_id, shed, lot_id=lot, strict=True)) if lot and shed else 0

    @api.depends('birds_count', 'average_weight')
    def _compute_total_weight_kg(self):
        for wizard in self:
            wizard.total_weight_kg = round(wizard.birds_count * wizard.average_weight, 2)

    @api.depends('birds_count', 'total_weight_kg')
    def _compute_net_average_weight(self):
        for wizard in self:
            wizard.net_average_weight = round(wizard.total_weight_kg / wizard.birds_count, 3) \
                if wizard.birds_count else 0.0

    @api.depends('flock_lot_id', 'birds_count', 'total_weight_kg', 'price_per_kg')
    def _compute_amounts(self):
        for wizard in self:
            sale = wizard.total_weight_kg * wizard.price_per_kg if wizard.price_per_kg else 0.0
            cost = wizard._get_harvest_cost()[0]
            wizard.total_sale_amount = sale
            wizard.harvest_cost = cost
            wizard.cost_per_kg = cost / wizard.total_weight_kg if wizard.total_weight_kg else 0.0
            wizard.estimated_margin = sale - cost if sale else 0.0
            wizard.remaining_birds = max(wizard.flock_lot_id._origin.live_bird_count - wizard.birds_count, 0)

    def _get_harvest_cost(self):
        """(batch cost, Broiler Cost Pool share) of the birds harvested: their share of the batch value in the
        shed and of its pool, by bird count. The last birds of the batch take all of it."""
        self.ensure_one()
        lot = self.flock_lot_id._origin
        live = lot.live_bird_count if lot else 0
        if not live or self.birds_count <= 0:
            return 0.0, 0.0
        batch = lot._get_broiler_cost_figures()[lot.id]
        share = min(self.birds_count / live, 1.0)
        currency = self.currency_id
        return currency.round(batch['remaining'] * share), currency.round(batch['pool'] * share)

    # ------------------------------------------------------------------ harvest
    def action_confirm_harvest(self):
        self.ensure_one()
        lot = self.flock_lot_id
        if not self.env.su and not self.env.user.has_group('top_farm_core.group_farm_manager'):
            raise AccessError(_("Only Farm Managers can record a broiler harvest."))
        if lot.flock_type != 'broiler' or lot.flock_stage != 'growing':
            raise UserError(_("%s is not a growing broiler batch.", lot.display_name))
        if self.birds_count <= 0 or self.birds_count > self.available_birds:
            raise ValidationError(_("Invalid bird count. Available: %s", self.available_birds))
        if self.total_weight_kg <= 0:
            raise ValidationError(_("Enter the net weight of the birds harvested."))
        meat = self._get_meat_product()
        meat_qty = self._get_meat_qty(meat)

        # 1. Conversion MO: the birds (carrying their batch cost) become meat by weight
        production = self._create_and_process_harvest_mo(meat, meat_qty, self._get_harvest_cost()[1])

        lot.message_post(body=_(
            "Harvest %(order)s: %(birds)s birds, %(weight)s kg (%(avg)s kg/bird) converted into Broiler Meat. "
            "Batch cost released to meat inventory: %(cost)s (%(per_kg)s/kg).",
            order=production.name, birds=self.birds_count, weight=formatLang(self.env, self.total_weight_kg),
            avg=formatLang(self.env, self.net_average_weight, digits=3),
            cost=format_amount(self.env, production.farm_broiler_batch_cost, self.currency_id),
            per_kg=format_amount(self.env, production.farm_broiler_batch_cost / self.total_weight_kg, self.currency_id),
        ), subtype_xmlid='mail.mt_note')

        # 2. No bird left in the batch: close it
        if not lot._get_live_bird_counts().get(lot.id):
            lot._close_broiler_batch()

        # Return action to view the completed Conversion Manufacturing Order
        if self.env['mrp.production'].has_access('read'):
            return {
                'name': _("Conversion Manufacturing Order"),
                'type': 'ir.actions.act_window',
                'res_model': 'mrp.production',
                'res_id': production.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
            }
        return {'type': 'ir.actions.act_window_close'}

    def _get_meat_product(self):
        meat = self.company_id.farm_broiler_meat_product_id
        if not meat:
            raise UserError(_("Choose the Broiler Meat Product in Top Farm > Farm Configuration > Settings first."))
        if not meat.is_storable:
            raise UserError(_("The broiler meat product %s must be tracked in inventory.", meat.display_name))
        if meat.with_company(self.company_id).cost_method not in ('fifo', 'average'):
            raise UserError(_(
                "The broiler meat product %s must use the FIFO or Average costing method: a standard price would "
                "ignore the batch cost of the birds.", meat.display_name))
        return meat

    def _get_meat_qty(self, meat):
        """Net weight in the meat product's unit, which must be a weight unit."""
        kg = self.env.ref('uom.product_uom_kgm')
        if not kg._has_common_reference(meat.uom_id):
            raise UserError(_("The broiler meat product %s must be measured by weight (e.g. kg).", meat.display_name))
        return kg._compute_quantity(self.total_weight_kg, meat.uom_id, round=False)

    def _get_meat_lot(self, meat):
        """Daily meat lot of the batch, MEAT-<batch>-<YYYYMMDD>, stamped with the batch as its parent flock so
        the meat sales can be reported to the batch."""
        self.ensure_one()
        if meat.tracking == 'none':
            return self.env['stock.lot']
        batch = self.flock_lot_id
        today = fields.Date.context_today(self)
        code = re.sub(r'[^A-Za-z0-9]+', '-', batch.name).strip('-')
        name = f"MEAT-{code}-{today.strftime('%Y%m%d')}"
        Lot = self.env['stock.lot'].sudo()
        lot = Lot.search([('product_id', '=', meat.id), ('name', '=', name),
                          ('company_id', 'in', [self.company_id.id, False])], limit=1) \
            or Lot.create({'product_id': meat.id, 'name': name, 'company_id': self.company_id.id})
        if not lot.farm_flock_lot_id:
            lot.write({'farm_flock_lot_id': batch.id, 'farm_production_date': today})
        return lot

    def _create_and_process_harvest_mo(self, meat, meat_qty, pool_cost):
        """Single-component conversion: the batch's birds (units) out of the shed, the meat (weight) into the
        dispatch store. The birds carry their stock value; their share of the Broiler Cost Pool is added as the
        order's extra cost, so the meat is valued at the batch cost of the birds harvested."""
        self.ensure_one()
        lot, shed, company = self.flock_lot_id, self.location_id, self.company_id
        bird = lot.product_id
        warehouse = shed.warehouse_id or self.env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
        if not warehouse.manu_type_id:
            raise UserError(_("No manufacturing operation type found for %s.", warehouse.display_name or company.name))
        destination = company.farm_broiler_meat_location_id or warehouse.lot_stock_id
        Production = self.env['mrp.production'].sudo().with_company(company)
        production = Production.create({
            'product_id': meat.id,
            'product_qty': meat_qty,
            'uom_id': meat.uom_id.id,
            'bom_id': False,
            'picking_type_id': warehouse.manu_type_id.id,
            'location_src_id': shed.id,
            'location_dest_id': destination.id,
            'lot_producing_ids': [Command.set(self._get_meat_lot(meat).ids)],
            'origin': lot.name,
            'company_id': company.id,
            'farm_broiler_lot_id': lot.id,
            'farm_broiler_bird_count': self.birds_count,
            'farm_broiler_weight_kg': self.total_weight_kg,
            'farm_broiler_pool_cost': pool_cost,
            'move_raw_ids': [Command.create({
                'product_id': bird.id,
                'uom_id': bird.uom_id.id,
                'product_uom_qty': self.birds_count,
                'location_id': shed.id,
                'farm_location_id': shed.id,
                'farm_flock_lot_id': lot.id,
            })],
        })
        production.action_confirm()
        raw = production.move_raw_ids
        raw.move_line_ids.unlink()
        raw.write({
            'move_line_ids': [Command.create({
                'product_id': bird.id,
                'uom_id': bird.uom_id.id,
                'quantity': self.birds_count,
                'location_id': shed.id,
                'location_dest_id': raw.location_dest_id.id,
                'lot_id': lot.id,
            })],
            'picked': True,
        })
        production.qty_producing = meat_qty
        production._set_qty_producing()
        production.with_context(skip_redirection=True).button_mark_done()
        if production.state != 'done':
            raise UserError(_("Harvest order %s could not be completed automatically.", production.name))
        return production
