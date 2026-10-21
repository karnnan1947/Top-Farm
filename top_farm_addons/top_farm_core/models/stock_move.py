# -*- coding: utf-8 -*-
import re

from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError

from .stock_location import BIRD_HOUSE_LEVELS


class StockMove(models.Model):
    _inherit = 'stock.move'

    farm_location_id = fields.Many2one(
        'stock.location',
        string='Farm House',
        index='btree_not_null',
        copy=False,
        domain="[('farm_hierarchy_level', 'in', ('brooding', 'cage'))]",
        help="Brooding nursery or cage the move's cost belongs to, set by farm operations (feed log, egg MO, "
             "scrap) for analytic tagging."
    )
    farm_flock_lot_id = fields.Many2one(
        'stock.lot',
        string='Flock Lot',
        index='btree_not_null',
        copy=False,
        domain="[('is_flock_batch', '=', True)]",
        help="On a farm input (feed, medication): the flock it was given to.\n"
             "On chicks dispatched to a brooding nursery: the flock lot they are placed under."
    )
    farm_lot_conversion = fields.Boolean(
        string='Flock Lot Conversion', readonly=True, copy=False,
        help="Re-labelling move of chicks from their hatchery lot to their flock lot.")

    def _prepare_merge_moves_distinct_fields(self):
        # Feed for two cages (or two flocks) in one picking must stay two moves, or confirming the picking
        # merges them and the whole quantity is charged to the first one.
        return super()._prepare_merge_moves_distinct_fields() + ['farm_location_id', 'farm_flock_lot_id']

    # -------------------------------------------------------------------------
    # ANALYTIC HOOK
    # -------------------------------------------------------------------------
    def _get_analytic_distribution(self):
        """
        The Single Odoo 20 Analytic Hook:
        Charges flock costs to the Flock analytic account (and the Cage account in a cage) across:
        1. Brooding / pre-laying feed & medication pickings to virtual consumption locations.
        2. Raw material feed consumption in egg harvest MOs (mrp.production).
        3. Bird mortality scrap moves.
        4. Nightly unharvested feed fallback write-offs.
        5. Birds leaving the farm (spent hens sold, culls), from one or several houses.
        """
        # Retain any explicit project/higher-priority distribution
        distribution = super()._get_analytic_distribution()
        if distribution or self.farm_lot_conversion:
            return distribution

        # Tag only cost-bearing outgoing moves: finished eggs entering stock must stay untagged
        if not self._is_out():
            return distribution
        flock, house = self._get_farm_flock_and_house()
        if flock:
            return flock.get_flock_analytic_distribution(house)
        if house.farm_analytic_account_id:
            return {str(house.farm_analytic_account_id.id): 100.0}
        if self.product_id.is_farm_bird:
            return self._get_farm_bird_distribution()
        return distribution

    def _get_farm_bird_distribution(self):
        """Birds leaving the farm in one move (e.g. a spent hen delivery picking from several cages): each line
        weighs on the accounts of its flock and of the house it leaves, by quantity."""
        weights = {}
        for line in self.move_line_ids.filtered(lambda ml: ml.lot_id.is_flock_batch):
            house = line.location_id if line.location_id.farm_hierarchy_level in BIRD_HOUSE_LEVELS \
                else self.env['stock.location']
            for key in line.lot_id.get_flock_analytic_distribution(house):
                weights[key] = weights.get(key, 0.0) + line.quantity_product_uom
        total = sum(weights.values())
        if not total:
            return {}
        distribution = {key: round(weight / total * 100.0, 4) for key, weight in weights.items()}
        biggest = max(distribution, key=distribution.get)
        distribution[biggest] = round(distribution[biggest] + 100.0 - sum(distribution.values()), 4)
        return distribution

    def _prepare_analytic_line_values(self, account_field_values, amount, unit_amount):
        values = super()._prepare_analytic_line_values(account_field_values, amount, unit_amount)
        # Core names the line after move.reference, which is empty for a move with no picking,
        # scrap or inventory (e.g. a farm cron write-off); account.analytic.line.name is NOT NULL.
        if not values.get('name'):
            values['name'] = self.product_id.display_name
        return values

    # -------------------------------------------------------------------------
    # VALUATION ENTRY: the flock distribution on the expense line
    # -------------------------------------------------------------------------
    def _get_account_move_line_vals(self):
        """Put the flock distribution on the expense side of the valuation entry (e.g. 510100 Feed Expense):
        posting the entry creates the analytic items on that account, so the Profit and Loss by analytic
        account shows the flock cost, not only its Total column."""
        vals_list = super()._get_account_move_line_vals()
        distribution = self._get_analytic_distribution()
        if distribution:
            counterpart = self._farm_valuation_counterpart_account()
            for vals in vals_list:
                if vals['account_id'] == counterpart.id:
                    vals.update(analytic_distribution=distribution, farm_stock_move_id=self.id,
                                quantity=self._get_valued_qty())
                    break
        return vals_list

    def _farm_valuation_counterpart_account(self):
        """The non-stock side of the valuation entry, as chosen by stock_account (expense, loss or WIP)."""
        return self.location_id.valuation_account_id or self.location_dest_id.valuation_account_id

    def _farm_valuation_analytic_lines(self):
        self.ensure_one()
        return self.account_move_id.line_ids.filtered(lambda line: line.farm_stock_move_id == self).analytic_line_ids

    def _create_analytic_move(self):
        # Posting a stamped valuation entry created the analytic items: they become the move's analytic items
        # (the dashboards read them through the move) and replace the estimate made when the move was picked,
        # instead of a second set from the move itself that would double the cost.
        entry_moves = self.env['stock.move']
        for move in self:
            entry_items = move._farm_valuation_analytic_lines()
            if entry_items:
                (move.analytic_account_line_ids - entry_items).unlink()
                move.analytic_account_line_ids = entry_items
                entry_moves |= move
        return super(StockMove, self - entry_moves)._create_analytic_move()

    @api.model
    def _farm_backfill_valuation_analytics(self):
        """Upgrade to 20.0.2.1.0: stamp the flock distribution on the expense line of the valuation entries
        posted before, then let the entry's analytic items replace the move's own (one set, never two).
        A distribution already set by hand on the entry line is kept."""
        for move in self.search([('state', '=', 'done'), ('account_move_id.state', '=', 'posted')]):
            distribution = move._get_analytic_distribution()
            entry_lines = move.account_move_id.line_ids
            if not distribution or entry_lines.filtered(lambda line: line.farm_stock_move_id == move):
                continue
            line = entry_lines.filtered(
                lambda l: not l.farm_stock_move_id
                and l.account_id == move._farm_valuation_counterpart_account()
                and l.product_id == move.product_id
                and l.name == f'{move.reference} - {move.product_id.name}'
                and move.company_id.currency_id.is_zero(abs(l.balance) - abs(move.value)))[:1]
            if not line:
                continue
            line.with_context(skip_analytic_sync=True).write({
                'farm_stock_move_id': move.id, 'quantity': move._get_valued_qty(),
                'analytic_distribution': line.analytic_distribution or distribution})
            # rebuild the line's analytic items with the quantity (also when the distribution is unchanged)
            line.analytic_line_ids.with_context(skip_analytic_sync=True).unlink()
            line._create_analytic_lines()
            move._create_analytic_move()

    def _get_farm_flock_and_house(self):
        """Return the flock lot and the brooding nursery or cage whose analytic accounts carry this move's
        cost (either may be empty)."""
        self.ensure_one()
        # Case A: Explicit references stamped on the move (feed log, medication, mortality scrap)
        if self.farm_flock_lot_id or self.farm_location_id:
            return self.farm_flock_lot_id, self.farm_location_id

        # Case B: Raw component of an Egg Collection MO. mrp.production and its farm_collection_id
        # come from mrp / top_farm_operations, which this module does not depend on.
        production = self['raw_material_production_id'] if 'raw_material_production_id' in self._fields else False
        if production and 'farm_collection_id' in production._fields and production.farm_collection_id:
            collection = production.farm_collection_id
            return collection.flock_lot_id, collection.cage_location_id
        return self.env['stock.lot'], self.env['stock.location']

    # -------------------------------------------------------------------------
    # FLOCK LOTS: hatchery arrival and placement in a brooding nursery
    # -------------------------------------------------------------------------
    def _action_done(self, cancel_backorder=False):
        self._farm_check_flock_lot_entry()
        moves = super()._action_done(cancel_backorder=cancel_backorder)
        moves._farm_stamp_arrival_date()
        moves._farm_place_flocks()
        return moves

    def _farm_brooding_placement_lines(self):
        """Lines of bird moves bringing a hatchery (non-flock) lot into a brooding nursery."""
        return self.filtered(lambda m: m.product_id.is_farm_bird and not m.farm_lot_conversion).move_line_ids.filtered(
            lambda ml: ml.location_dest_id.farm_hierarchy_level == 'brooding' and not ml.lot_id.is_flock_batch)

    def _farm_check_flock_lot_entry(self):
        """Approach A: the clerk must enter the flock lot before chicks reach a brooding nursery."""
        for line in self._farm_brooding_placement_lines():
            move = line.move_id
            flock = move.farm_flock_lot_id
            if flock and flock.product_id != move.product_id:
                raise UserError(_("The flock lot %(lot)s is a lot of %(lot_product)s, not of %(product)s.",
                                  lot=flock.name, lot_product=flock.product_id.display_name,
                                  product=move.product_id.display_name))
            if not flock and move.company_id.farm_lot_generation_mode == 'manual':
                raise UserError(_(
                    "Enter the Flock Lot of the %(product)s dispatched to %(location)s before validating "
                    "(Flock Lot column of the transfer, e.g. %(example)s).",
                    product=move.product_id.display_name, location=line.location_dest_id.display_name,
                    example=move._farm_flock_lot_name(line.location_dest_id, line.lot_id)))

    def _farm_stamp_arrival_date(self):
        """A chick receipt from the hatchery dates its lot: the flock age counts from that day."""
        for move in self.filtered(lambda m: m.state == 'done' and m.product_id.is_farm_bird
                                  and m.location_id.usage == 'supplier'):
            arrival = fields.Date.context_today(move, move.date)
            move.move_line_ids.lot_id.filtered(lambda lot: not lot.farm_arrival_date).farm_arrival_date = arrival

    def _farm_place_flocks(self):
        """Odoo moves a lot unchanged from source to destination, so chicks reach the brooding nursery under
        their hatchery lot. Re-label them there as their flock lot: the one entered on the move (Approach A)
        or the generated estate lot (Approach B)."""
        conversion = self.env.ref('top_farm_core.location_flock_lot_conversion')
        lines = self.filtered(lambda m: m.state == 'done')._farm_brooding_placement_lines().filtered('lot_id')
        placed = {}
        for (move, brooding, source_lot), group in lines.grouped(
                lambda ml: (ml.move_id, ml.location_dest_id, ml.lot_id)).items():
            flock = move.farm_flock_lot_id or move._farm_generate_flock_lot(brooding, source_lot)
            move._farm_relot(brooding, source_lot, flock, sum(group.mapped('quantity_product_uom')), conversion)
            placed[move] = placed.get(move, flock.browse()) | flock
        # show the generated flock lot on the transfer line (Approach B), when the line made only one
        for move, flocks in placed.items():
            if not move.farm_flock_lot_id and len(flocks) == 1:
                move.farm_flock_lot_id = flocks

    def _farm_flock_lot_name(self, brooding, source_lot):
        """[Estate Code]-[DD-MM-YYYY], dated by the chick arrival or the transfer as the settings say."""
        self.ensure_one()
        farm = brooding.parent_farm_location_id
        code = re.sub(r'[^A-Za-z0-9]+', '-', farm.farm_code or farm.name).strip('-').upper()
        lot_date = fields.Date.context_today(self, self.date)
        if self.company_id.farm_lot_date_source == 'arrival' and source_lot.farm_arrival_date:
            lot_date = source_lot.farm_arrival_date
        return f"{code}-{lot_date.strftime('%d-%m-%Y')}"

    def _farm_generate_flock_lot(self, brooding, source_lot):
        """Approach B. A flock of that name still in brooding is reused: more chicks of the same arrival join
        it. A flock of that name that has already left brooding is another flock: the new one gets a suffix."""
        self.ensure_one()
        base = self._farm_flock_lot_name(brooding, source_lot)
        Lot = self.env['stock.lot']
        name, suffix = base, 1
        while True:
            flock = Lot.search([('product_id', '=', self.product_id.id), ('name', '=', name),
                                ('company_id', 'in', [self.company_id.id, False])], limit=1)
            if not flock or (flock.is_flock_batch and flock.flock_stage == 'brooding'):
                break
            if not flock.is_flock_batch:
                raise UserError(_("The lot %s already exists and is not a flock. Rename it, or enter the flock "
                                  "lot on the transfer.", name))
            suffix += 1
            name = f"{base}-{suffix}"
        return flock or Lot.create({
            'name': name,
            'product_id': self.product_id.id,
            'company_id': self.company_id.id,
            'is_flock_batch': True,
            'farm_location_id': brooding.parent_farm_location_id.id,
        })

    def _farm_relot(self, brooding, source_lot, flock, qty, conversion):
        """Re-label `qty` birds of `source_lot` in `brooding` as `flock`: out to the conversion location under
        the hatchery lot, back in under the flock lot. Both moves are valued at the product cost, so the stock
        value does not change and, the conversion location having no account, no journal entry is posted."""
        self.ensure_one()
        product = self.product_id
        label = _("Flock lot %(flock)s from %(lot)s", flock=flock.name, lot=source_lot.name)
        price_unit = self.price_unit or product.standard_price
        moves = self.env['stock.move']
        for source, destination, lot in ((brooding, conversion, source_lot), (conversion, brooding, flock)):
            moves |= self.create({
                'product_id': product.id,
                'uom_id': product.uom_id.id,
                'product_uom_qty': qty,
                'price_unit': price_unit,
                'location_id': source.id,
                'location_dest_id': destination.id,
                'company_id': self.company_id.id,
                'origin': self.reference,
                # a move with no picking has an empty reference unless it is an inventory move
                'is_inventory': True,
                'inventory_name': label,
                'farm_lot_conversion': True,
                'picked': True,
                'move_line_ids': [Command.create({
                    'product_id': product.id,
                    'uom_id': product.uom_id.id,
                    'quantity': qty,
                    'location_id': source.id,
                    'location_dest_id': destination.id,
                    'lot_id': lot.id,
                    'picked': True,
                })],
            })
        moves._action_done()
        if any(move.state != 'done' for move in moves):
            raise UserError(_("The chicks of lot %s could not be re-labelled as their flock lot.", source_lot.name))
        if moves and len(moves) == 2:
            if not moves[1].value and moves[0].value:
                moves[1].value = abs(moves[0].value)
                if not moves[1].price_unit and qty:
                    moves[1].price_unit = moves[1].value / qty
        chick_cost = moves[1].value or (abs(moves[0].value) if moves and moves[0].value else (price_unit * qty))
        values = {
            'is_flock_batch': True,
            'initial_bird_count': flock.initial_bird_count + round(qty),
            'chick_cost': flock.chick_cost + chick_cost,
            'farm_location_id': flock.farm_location_id.id or brooding.parent_farm_location_id.id,
            'farm_arrival_date': (flock.farm_arrival_date or source_lot.farm_arrival_date
                                  or fields.Date.context_today(self, self.date)),
            'farm_source_lot_id': flock.farm_source_lot_id.id or source_lot.id,
        }
        flock.write(values)
        flock.message_post(body=_(
            "%(qty)s chicks placed in %(brooding)s from hatchery lot %(lot)s (%(reference)s).",
            qty=f"{qty:g}", brooding=brooding.display_name, lot=source_lot.name, reference=self.reference),
            subtype_xmlid='mail.mt_note')
