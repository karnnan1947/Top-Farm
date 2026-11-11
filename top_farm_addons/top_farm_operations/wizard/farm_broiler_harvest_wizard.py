# -*- coding: utf-8 -*-
import re

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import format_amount, formatLang

# A broiler batch is harvested once Growing (never in Brooding); the hens of a layer flock are culled into meat
# while it is Laying, or once it is Spent.
BROILER_HARVEST_STAGES = ('growing', 'harvesting')
LAYER_CULL_STAGES = ('laying', 'spent')


class FarmBroilerHarvestWizard(models.TransientModel):
    _name = 'farm.broiler.harvest.wizard'
    _description = 'Bird Harvest & Meat Conversion Wizard (broiler harvest, layer culling)'

    flock_lot_id = fields.Many2one(
        'stock.lot', string='Flock / Batch', required=True, readonly=True,
        domain="[('is_flock_batch', '=', True), "
               "'|', '&', ('flock_type', '=', 'broiler'), ('flock_stage', 'in', ('growing', 'harvesting')), "
               "'&', ('flock_type', '=', 'layer'), ('flock_stage', 'in', ('laying', 'spent'))]")
    flock_type = fields.Selection(related='flock_lot_id.flock_type')
    company_id = fields.Many2one('res.company', compute='_compute_company_id')
    currency_id = fields.Many2one('res.currency', compute='_compute_company_id')
    shed_location_ids = fields.Many2many('stock.location', compute='_compute_shed_location_ids')
    location_id = fields.Many2one(
        'stock.location', string='Broiler Shed / Layer Cage', required=True,
        domain="[('id', 'in', shed_location_ids)]",
        help="Broiler shed or layer cage the birds are picked up from.")
    available_birds = fields.Integer(
        string='Live Birds Available', compute='_compute_available_birds',
        help="Free live birds of the flock in the shed or cage.")
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
        string='Cost of These Birds', currency_field='currency_id', compute='_compute_amounts',
        help="Broiler batch: their share of the batch value in the shed (chicks plus capitalized feed, medication "
             "and mortality). Layer flock: the stock value of the hens culled. It becomes the stock value of the "
             "meat.")
    cost_per_kg = fields.Monetary(string='Meat Cost / kg', currency_field='currency_id', compute='_compute_amounts')
    remaining_birds = fields.Integer(string='Birds Left in Flock', compute='_compute_amounts')
    remaining_house_birds = fields.Integer(string='Birds Left in This Shed / Cage', compute='_compute_amounts')

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
        if lot.exists():
            houses = lot.flock_location_ids
            # launched from a cage: that cage, when the flock really lives in it
            if res.get('location_id') and res['location_id'] not in houses.ids:
                res.pop('location_id')
            if not res.get('location_id') and len(houses) == 1:
                res['location_id'] = houses.id
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

    @api.depends('flock_lot_id', 'location_id', 'birds_count', 'total_weight_kg', 'price_per_kg')
    def _compute_amounts(self):
        for wizard in self:
            sale = wizard.total_weight_kg * wizard.price_per_kg if wizard.price_per_kg else 0.0
            cost = wizard._get_harvest_cost()[0]
            wizard.total_sale_amount = sale
            wizard.harvest_cost = cost
            wizard.cost_per_kg = cost / wizard.total_weight_kg if wizard.total_weight_kg else 0.0
            wizard.estimated_margin = sale - cost if sale else 0.0
            wizard.remaining_birds = max(wizard.flock_lot_id._origin.live_bird_count - wizard.birds_count, 0)
            wizard.remaining_house_birds = max(wizard.available_birds - wizard.birds_count, 0)

    def _get_harvest_cost(self):
        """(cost, Broiler Cost Pool share) of the birds harvested, by bird count.
        Broiler batch: their share of the batch value in the shed and of its pool; the last birds of the batch
        take all of it. Layer flock: the stock value of the hens culled and no pool (the feed of a layer flock is
        expensed or consumed by its eggs, never capitalized in the birds)."""
        self.ensure_one()
        lot = self.flock_lot_id._origin
        live = lot.live_bird_count if lot else 0
        if not live or self.birds_count <= 0:
            return 0.0, 0.0
        share = min(self.birds_count / live, 1.0)
        currency = self.currency_id
        if lot.flock_type != 'broiler':
            product = lot.product_id.with_company(self.company_id)
            if product.lot_valuated:
                live_value = lot.sudo().with_company(self.company_id).total_value
            else:
                live_value = product.standard_price * live
            return currency.round(live_value * share), 0.0
        batch = lot._get_broiler_cost_figures()[lot.id]
        return currency.round(batch['remaining'] * share), currency.round(batch['pool'] * share)

    # ------------------------------------------------------------------ harvest
    def action_confirm_harvest(self):
        self.ensure_one()
        lot = self.flock_lot_id
        layer = lot.flock_type == 'layer'
        if not self.env.su and not self.env.user.has_group('top_farm_core.group_farm_manager'):
            raise AccessError(_("Only Farm Managers can record a harvest or a culling."))
        lot._farm_check_harvestable()
        if self.birds_count <= 0 or self.birds_count > self.available_birds:
            raise ValidationError(_("Invalid bird count. Available in %(house)s: %(birds)s",
                                    house=self.location_id.display_name, birds=self.available_birds))
        if self.total_weight_kg <= 0:
            raise ValidationError(_("Enter the net weight of the birds harvested."))
        meat = self._get_meat_product()
        meat_qty = self._get_meat_qty(meat)

        # 1. Conversion MO: the birds (carrying their cost) become meat by weight
        production = self._create_and_process_harvest_mo(meat, meat_qty, self._get_harvest_cost()[1])

        remaining = lot._get_live_bird_counts().get(lot.id, 0)
        values = dict(
            order=production.name, birds=self.birds_count, weight=formatLang(self.env, self.total_weight_kg),
            avg=formatLang(self.env, self.net_average_weight, digits=3), product=meat.display_name,
            house=self.location_id.display_name, left=remaining,
            cost=format_amount(self.env, production.farm_broiler_batch_cost, self.currency_id),
            per_kg=format_amount(self.env, production.farm_broiler_batch_cost / self.total_weight_kg, self.currency_id),
        )
        if layer:
            body = _(
                "Culling %(order)s: %(birds)s hens from %(house)s, %(weight)s kg (%(avg)s kg/bird) converted into "
                "%(product)s. Stock value of the hens moved to it: %(cost)s (%(per_kg)s/kg). %(left)s hens left "
                "in the flock.", **values)
        else:
            body = _(
                "Harvest %(order)s: %(birds)s birds, %(weight)s kg (%(avg)s kg/bird) converted into %(product)s. "
                "Batch cost released to meat inventory: %(cost)s (%(per_kg)s/kg).", **values)
        lot.message_post(body=body, subtype_xmlid='mail.mt_note')

        # 2. Lifecycle: a layer flock keeps laying while hens remain; a broiler batch moves to Harvesting on its
        #    first partial harvest and is closed with its last bird.
        if layer:
            if not remaining and lot.flock_stage == 'laying':
                lot._mark_spent(reason=_("Its last hens were culled (%s).", production.name))
        elif not remaining:
            lot._close_broiler_batch()
        else:
            lot._broiler_start_harvesting()

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
        """Broiler Meat for a broiler batch, the separate Layer Live Weight product for culled layer hens."""
        self.ensure_one()
        if self.flock_lot_id.flock_type == 'layer':
            meat = self.company_id.farm_layer_meat_product_id
            if not meat:
                raise UserError(_("Choose the Layer Live Weight Product in Top Farm > Farm Configuration > "
                                  "Settings first."))
            if meat.tracking != 'lot':
                raise UserError(_(
                    "The Layer Live Weight product %s must be tracked by lots: the lot of each culling carries the "
                    "flock its sales are reported to.", meat.display_name))
        else:
            meat = self.company_id.farm_broiler_meat_product_id
            if not meat:
                raise UserError(_("Choose the Broiler Meat Product in Top Farm > Farm Configuration > Settings first."))
        if meat.is_farm_bird:
            raise UserError(_("%s is a live bird product: choose a meat product sold by weight.", meat.display_name))
        if not meat.is_storable:
            raise UserError(_("The meat product %s must be tracked in inventory.", meat.display_name))
        if meat.with_company(self.company_id).cost_method not in ('fifo', 'average'):
            raise UserError(_(
                "The meat product %s must use the FIFO or Average costing method: a standard price would "
                "ignore the cost of the birds.", meat.display_name))
        return meat

    def _get_meat_qty(self, meat):
        """Net weight in the meat product's unit, which must be a weight unit."""
        kg = self.env.ref('uom.product_uom_kgm')
        if not kg._has_common_reference(meat.uom_id):
            raise UserError(_("The meat product %s must be measured by weight (e.g. kg).", meat.display_name))
        return kg._compute_quantity(self.total_weight_kg, meat.uom_id, round=False)

    def _get_meat_lot(self, meat):
        """Daily meat lot of the flock, MEAT-<batch>-<YYYYMMDD> for a broiler batch and CULL-<flock>-<YYYYMMDD>
        for culled layer hens, stamped with the flock as its parent so the meat sales (order lines, invoices,
        profitability) are reported to it."""
        self.ensure_one()
        if not meat.tracking or meat.tracking == 'none':
            return self.env['stock.lot']
        batch = self.flock_lot_id
        today = fields.Date.context_today(self)
        code = re.sub(r'[^A-Za-z0-9]+', '-', batch.name).strip('-')
        prefix = 'CULL' if batch.flock_type == 'layer' else 'MEAT'
        name = f"{prefix}-{code}-{today.strftime('%Y%m%d')}"
        Lot = self.env['stock.lot'].sudo()
        lot = Lot.search([('product_id', '=', meat.id), ('name', '=', name),
                          ('company_id', 'in', [self.company_id.id, False])], limit=1) \
            or Lot.create({'product_id': meat.id, 'name': name, 'company_id': self.company_id.id})
        if not lot.farm_flock_lot_id:
            lot.write({'farm_flock_lot_id': batch.id, 'farm_production_date': today})
        return lot

    def _get_meat_destination(self, warehouse):
        self.ensure_one()
        company = self.company_id
        if self.flock_lot_id.flock_type == 'layer':
            return company.farm_layer_meat_location_id or warehouse.lot_stock_id
        return company.farm_broiler_meat_location_id or warehouse.lot_stock_id

    def _create_and_process_harvest_mo(self, meat, meat_qty, pool_cost):
        """Single-component conversion: the flock's birds (units) out of the shed or cage, the meat (weight) into
        the dispatch store. The birds carry their stock value; for a broiler batch their share of the Broiler
        Cost Pool is added as the order's extra cost, so the meat is valued at the cost of the birds harvested."""
        self.ensure_one()
        lot, shed, company = self.flock_lot_id, self.location_id, self.company_id
        bird = lot.product_id
        warehouse = shed.warehouse_id or self.env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
        if not warehouse.manu_type_id:
            raise UserError(_("No manufacturing operation type found for %s.", warehouse.display_name or company.name))
        destination = self._get_meat_destination(warehouse)
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
