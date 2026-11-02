# -*- coding: utf-8 -*-
from odoo import Command, api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import format_amount

POINT_OF_LAY_ACTIVITY = 'top_farm_core.mail_activity_type_point_of_lay'
FLOCK_STAGES = [
    ('brooding', 'Brooding'),
    ('rearing', 'Rearing / Pre-Laying'),
    ('laying', 'Laying'),
    ('growing', 'Growing (Broiler)'),
    ('spent', 'Spent / Depleted'),
]


class StockLot(models.Model):
    _inherit = 'stock.lot'

    is_farm_bird = fields.Boolean(related='product_id.is_farm_bird')
    is_flock_batch = fields.Boolean(
        string='Flock Batch', index=True, copy=False, tracking=True,
        help="This lot is a flock: a cohort of birds that moves through the farm's brooding nurseries and "
             "cages over its 2 to 2.5-year lifecycle. Hatchery lots received at the main warehouse are not flocks.")
    farm_location_id = fields.Many2one(
        'stock.location', string='Farm Estate', index='btree_not_null', tracking=True,
        domain="[('farm_hierarchy_level', '=', 'farm')]")
    farm_arrival_date = fields.Date(
        string='Chick Arrival Date', tracking=True,
        help="Date the day-old chicks arrived from the hatchery. Set on the hatchery lot when the receipt is "
             "validated and passed on to the flock lots created from it; the flock age counts from it.")
    flock_age_weeks = fields.Float(string='Age (Weeks)', compute='_compute_flock_age', digits=(16, 1))
    flock_age_days = fields.Integer(string='Age (Days)', compute='_compute_flock_age')
    flock_type = fields.Selection(
        related='product_id.farm_flock_type', string='Flock Type', store=True, index=True,
        help="Layer Flock or Broiler Batch, from the Bird Type of the product.")
    flock_stage = fields.Selection(
        FLOCK_STAGES, string='Flock Stage', index=True, copy=False, tracking=True,
        help="Brooding: chicks under heat in the brooding nursery (weeks 0-4).\n"
             "Rearing / Pre-Laying: pullets in cages; their cost accumulates as flock investment.\n"
             "Laying: commercial egg production; feed becomes a component of the eggs.\n"
             "Growing (Broiler): a broiler batch in its shed; its costs are capitalized until harvest.\n"
             "Spent / Depleted: end of the laying cycle, or every bird of the broiler batch harvested.")
    flock_analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Flock Analytic Account', copy=False, tracking=True,
        help="Every cost of the flock (brooding and cage feed, medication, mortality) is tagged to this account.")
    farm_source_lot_id = fields.Many2one(
        'stock.lot', string='Hatchery Lot', readonly=True, copy=False,
        help="Lot the chicks were received under at the main warehouse, before the flock lot was created.")
    initial_bird_count = fields.Integer(
        string='Birds Placed', readonly=True, copy=False,
        help="Chicks placed in the brooding nursery under this flock lot.")
    currency_id = fields.Many2one('res.currency', compute='_compute_currency_id')
    chick_cost = fields.Monetary(
        string='Day-Old Chick Cost', readonly=True, copy=False,
        help="Stock value of the chicks placed under this flock lot.")
    live_bird_count = fields.Integer(string='Live Birds', compute='_compute_live_bird_count')
    flock_location_ids = fields.Many2many(
        'stock.location', string='Housed In', compute='_compute_flock_location_ids',
        help="Brooding nurseries and cages holding live birds of this flock now.")
    cage_allocation_date = fields.Date(string='Cage Allocation Date', readonly=True, copy=False)
    laying_start_date = fields.Date(
        string='Laying Phase Start', readonly=True, copy=False,
        help="Pre-laying cost accumulation stops at this date: the flock investment is locked.")
    laying_start_bird_count = fields.Integer(string='Birds at Point of Lay', readonly=True, copy=False)
    laying_notification_sent = fields.Boolean(
        string='Laying Alert Sent', readonly=True, copy=False,
        help="Set once the Farm Managers were told that the flock is ready for the Laying Phase.")
    depletion_date = fields.Date(string='Depletion Date', readonly=True, copy=False)

    # Broiler batch: pre-sale commercial planning. Feed, medication and dead birds of a broiler batch go to a
    # Broiler Cost Pool location instead of an expense: the batch value stays capitalized (chicks in stock plus
    # the pool) and each harvest releases the share of the birds it takes into the meat.
    broiler_avg_weight = fields.Float(
        string='Estimated Avg Weight (kg)', digits=(16, 3), tracking=True, copy=False,
        help="Sample average live weight per bird, entered by the manager from the supervisor's growth checks.")
    broiler_market_rate = fields.Monetary(
        string='Market Selling Rate / kg', currency_field='currency_id', tracking=True, copy=False,
        help="Negotiated or prevailing market rate per kg of live weight for this batch.")
    broiler_estimated_biomass = fields.Float(
        string='Total Biomass (kg)', compute='_compute_broiler_commercials', digits=(16, 2),
        help="Live birds x estimated average weight.")
    broiler_batch_cost = fields.Monetary(
        string='Total Batch Investment', compute='_compute_broiler_commercials', currency_field='currency_id',
        help="Chicks placed, plus the feed, medication and vaccines capitalized into the batch since placement.")
    broiler_remaining_cost = fields.Monetary(
        string='Batch Value in Shed', compute='_compute_broiler_commercials', currency_field='currency_id',
        help="Batch cost still carried by the live birds: their chick value plus the batch's Broiler Cost Pool. "
             "Mortality is not written off: the surviving birds absorb it.")
    broiler_cost_per_bird = fields.Monetary(
        string='Cost / Live Bird', compute='_compute_broiler_commercials', currency_field='currency_id',
        help="Batch value in shed / live birds.")
    broiler_cost_per_kg = fields.Monetary(
        string='Estimated Cost / kg', compute='_compute_broiler_commercials', currency_field='currency_id',
        help="Batch value in shed / total biomass.")
    broiler_estimated_value = fields.Monetary(
        string='Estimated Market Value', compute='_compute_broiler_commercials', currency_field='currency_id',
        help="Total biomass x market selling rate.")
    broiler_estimated_margin = fields.Monetary(
        string='Estimated Margin', compute='_compute_broiler_commercials', currency_field='currency_id',
        help="Estimated market value less the batch value in shed.")
    broiler_written_off_cost = fields.Monetary(
        string='Written Off at Closing', currency_field='currency_id', readonly=True, copy=False,
        help="Batch cost no harvest released (e.g. a batch lost to the last bird), expensed when it was closed.")

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_flock_batch') and not vals.get('flock_stage'):
                product = self.env['product.product'].browse(vals.get('product_id'))
                vals['flock_stage'] = self._farm_initial_stage(product)
        lots = super().create(vals_list)
        lots.filtered('is_flock_batch')._farm_ensure_analytic_account()
        return lots

    def write(self, vals):
        res = super().write(vals)
        if vals.get('is_flock_batch'):
            for lot in self.filtered(lambda l: not l.flock_stage):
                lot.flock_stage = self._farm_initial_stage(lot.product_id)
            self._farm_ensure_analytic_account()
        return res

    @api.model
    def _farm_initial_stage(self, product):
        return 'growing' if product.farm_flock_type == 'broiler' else 'brooding'

    def _farm_ensure_analytic_account(self):
        """Give each flock its own account in the Flock Analytic Plan, when the company asks for it."""
        for lot in self.filtered(lambda l: l.is_flock_batch and not l.flock_analytic_account_id):
            company = lot.company_id or self.env.company
            plan = company._get_farm_flock_plan()
            if not company.farm_flock_auto_analytic or not plan:
                continue
            lot.flock_analytic_account_id = self.env['account.analytic.account'].sudo().create({
                'name': lot.name,
                'code': lot.name,
                'plan_id': plan.id,
                'company_id': lot.company_id.id,
            })

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------
    @api.depends('company_id')
    def _compute_currency_id(self):
        for lot in self:
            lot.currency_id = (lot.company_id or self.env.company).currency_id

    @api.depends('farm_arrival_date')
    def _compute_flock_age(self):
        today = fields.Date.context_today(self)
        for lot in self:
            days = max(0, (today - lot.farm_arrival_date).days) if lot.farm_arrival_date else 0
            lot.flock_age_days = days
            lot.flock_age_weeks = round(days / 7.0, 1)

    @api.depends('broiler_avg_weight', 'broiler_market_rate')
    def _compute_broiler_commercials(self):
        broilers = self._origin.filtered(lambda l: l.is_flock_batch and l.flock_type == 'broiler')
        figures = broilers._get_broiler_cost_figures()
        for lot in self:
            batch = figures.get(lot._origin.id)
            if not batch:
                lot.update(dict.fromkeys([
                    'broiler_estimated_biomass', 'broiler_batch_cost', 'broiler_remaining_cost',
                    'broiler_cost_per_bird', 'broiler_cost_per_kg', 'broiler_estimated_value',
                    'broiler_estimated_margin'], 0.0))
                continue
            birds = lot.live_bird_count
            biomass = birds * lot.broiler_avg_weight
            value = biomass * lot.broiler_market_rate
            lot.broiler_estimated_biomass = biomass
            lot.broiler_batch_cost = batch['invested']
            lot.broiler_remaining_cost = batch['remaining']
            lot.broiler_cost_per_bird = batch['remaining'] / birds if birds else 0.0
            lot.broiler_cost_per_kg = batch['remaining'] / biomass if biomass else 0.0
            lot.broiler_estimated_value = value
            lot.broiler_estimated_margin = value - batch['remaining'] if value else 0.0

    def _compute_live_bird_count(self):
        counts = self._origin._get_live_bird_counts()
        for lot in self:
            lot.live_bird_count = counts.get(lot._origin.id, 0)

    def _compute_flock_location_ids(self):
        houses = {}
        lots = self._origin.filtered('id')
        if lots:
            for lot, location in self.env['stock.quant']._read_group(
                    [('lot_id', 'in', lots.ids), ('quantity', '>', 0), ('location_id.usage', '=', 'internal')],
                    ['lot_id', 'location_id']):
                houses.setdefault(lot.id, self.env['stock.location'])
                houses[lot.id] |= location
        for lot in self:
            lot.flock_location_ids = houses.get(lot._origin.id, self.env['stock.location'])

    # -------------------------------------------------------------------------
    # CONSTRAINTS
    # -------------------------------------------------------------------------
    @api.constrains('is_flock_batch', 'product_id')
    def _check_flock_product(self):
        for lot in self:
            if lot.is_flock_batch and not lot.product_id.is_farm_bird:
                raise ValidationError(_("Only lots of a live farm bird product can be flocks (%s is not one).",
                                        lot.product_id.display_name))

    @api.constrains('flock_analytic_account_id')
    def _check_flock_analytic_plan(self):
        """See stock.location._check_cage_analytic_plan: flock and cage accounts need two different root plans."""
        for lot in self.filtered('flock_analytic_account_id'):
            plan = lot.flock_analytic_account_id.root_plan_id
            if self.env['stock.location'].search_count(
                    [('farm_hierarchy_level', '=', 'cage'), ('farm_analytic_account_id.root_plan_id', '=', plan.id)],
                    limit=1):
                raise ValidationError(_(
                    "The analytic account of flock %(flock)s belongs to the plan '%(plan)s', which holds cage "
                    "accounts. Use an account of the Flock Analytic Plan.", flock=lot.display_name,
                    plan=plan.display_name))

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------
    def _get_live_bird_counts(self):
        """{lot id: live birds of the lot on hand in internal locations}, in one query."""
        lots = self.filtered('id')
        if not lots:
            return {}
        groups = self.env['stock.quant']._read_group(
            [('lot_id', 'in', lots.ids), ('location_id.usage', '=', 'internal')], ['lot_id'], ['quantity:sum'])
        return {lot.id: round(quantity) for lot, quantity in groups}

    def get_flock_analytic_distribution(self, location=None):
        """
        Builds the Odoo 20 multi-plan analytic distribution dictionary of a flock cost.
        In a brooding nursery: {"flock_account_id": 100.0}.
        In a cage: {"flock_account_id,cage_account_id": 100.0}, i.e. ONE analytic line with both plan
        columns populated, which prevents doubling the cost.
        """
        accounts = self.flock_analytic_account_id
        if location and location.farm_hierarchy_level == 'cage':
            accounts |= location.farm_analytic_account_id
        if not accounts:
            return {}
        return {','.join(str(account_id) for account_id in accounts.ids): 100.0}

    def _get_brooding_locations(self):
        self.ensure_one()
        return self.flock_location_ids.filtered(lambda l: l.farm_hierarchy_level == 'brooding')

    # -------------------------------------------------------------------------
    # BROILER BATCH COSTING
    # -------------------------------------------------------------------------
    def _get_broiler_pool_movements(self):
        """{lot id: [inputs, dead birds]}: value sent to a Broiler Cost Pool location for each batch, net of what
        came back. Inputs are the feed, medication and vaccines stamped with the batch; dead birds are its mortality
        scraps and their reversals, recognised by their lot."""
        lots = self.filtered('id')
        if not lots:
            return {}
        moves = self.env['stock.move'].sudo().search([
            ('state', '=', 'done'),
            '|', ('location_dest_id.farm_broiler_cost_pool', '=', True),
                 ('location_id.farm_broiler_cost_pool', '=', True),
            '|', ('farm_flock_lot_id', 'in', lots.ids), ('move_line_ids.lot_id', 'in', lots.ids),
        ])
        movements = {lot.id: [0.0, 0.0] for lot in lots}
        for move in moves:
            if move.product_id.is_farm_bird:
                batch, index = (move.move_line_ids.lot_id & lots)[:1], 1
            else:
                batch, index = move.farm_flock_lot_id & lots, 0
            if batch:
                # into the pool the move is outgoing (negative value), back from it incoming (positive)
                movements[batch.id][index] -= move.value
        return movements

    def _get_broiler_pool_releases(self):
        """{lot id: value taken out of the batch's Broiler Cost Pool}: written off at closing here;
        top_farm_operations adds the share each harvest gave to the meat."""
        return {lot.id: lot.broiler_written_off_cost for lot in self}

    def _get_broiler_live_values(self):
        """{lot id: stock value of the batch's live birds}: the lot's own value when the product is valued by
        lot, else the live birds at the cost of the chicks placed."""
        values = {}
        for lot in self.filtered('id'):
            if lot.product_id.lot_valuated:
                values[lot.id] = lot.sudo().with_company(lot.company_id or self.env.company).total_value
            else:
                unit_cost = lot.chick_cost / lot.initial_bird_count if lot.initial_bird_count else 0.0
                values[lot.id] = lot.live_bird_count * unit_cost
        return values

    def _get_total_accumulated_batch_cost(self):
        """{lot id: chicks placed + feed, medication and vaccines capitalized into the broiler batch}."""
        movements = self._get_broiler_pool_movements()
        return {lot.id: lot.chick_cost + movements.get(lot.id, [0.0, 0.0])[0] for lot in self.filtered('id')}

    def _get_broiler_cost_figures(self):
        """{lot id: {invested, pool, live_value, remaining}} of broiler batches, in company currency.
        The batch value in the shed (remaining) is the live birds' stock value plus the batch's Broiler Cost Pool:
        a harvest releases exactly what the batch still carries, whatever happened to its birds before."""
        lots = self.filtered('id')
        movements = lots._get_broiler_pool_movements()
        releases = lots._get_broiler_pool_releases()
        live_values = lots._get_broiler_live_values()
        figures = {}
        for lot in lots:
            inputs, dead = movements.get(lot.id, [0.0, 0.0])
            pool = inputs + dead - releases.get(lot.id, 0.0)
            live_value = live_values.get(lot.id, 0.0)
            figures[lot.id] = {
                'invested': lot.chick_cost + inputs,
                'pool': pool,
                'live_value': live_value,
                'remaining': live_value + pool,
            }
        return figures

    # -------------------------------------------------------------------------
    # STAGE ACTIONS
    # -------------------------------------------------------------------------
    def _check_flock_stage_change(self, from_stages):
        """Manager-only change of the flock stage (never callable by an operator, whatever the context)."""
        self.ensure_one()
        if not self.env.su and not self.env.user.has_group('top_farm_core.group_farm_manager'):
            raise AccessError(_("Only Farm Managers can change the stage of a flock."))
        if not self.is_flock_batch:
            raise UserError(_("%s is not a flock lot.", self.display_name))
        if self.flock_stage not in from_stages:
            stages = dict(self._fields['flock_stage'].selection)
            raise UserError(_("This flock is not in the '%(stage)s' stage.",
                              stage=" / ".join(stages[stage] for stage in from_stages)))

    def _post_stage_note(self, body):
        self.message_post(body=body, subtype_xmlid='mail.mt_note')

    def action_move_to_rearing(self):
        """Manager button: brooding is over (normally done by the Brooding-to-Cage allocation wizard)."""
        self.ensure_one()
        self._check_flock_stage_change(['brooding'])
        self._advance_to_rearing()
        return True

    def _advance_to_rearing(self):
        self.ensure_one()
        if self.flock_stage != 'brooding':
            return
        self.write({'flock_stage': 'rearing', 'cage_allocation_date': fields.Date.context_today(self)})
        self._post_stage_note(_("Brooding is over: flock moved to Rearing / Pre-Laying at %(age)s weeks.",
                                age=f"{self.flock_age_weeks:.1f}"))

    def action_start_laying_phase(self):
        """Manager button: confirm the transition to the Laying Phase."""
        self.ensure_one()
        self._check_flock_stage_change(['rearing'])
        self._start_laying_phase()
        return True

    def _start_laying_phase(self, automatic=False, reason=None):
        """Move the flock to Laying and lock its pre-laying investment. Private so that the daily check can call
        it, while RPC callers always go through the manager check above."""
        self.ensure_one()
        if self.flock_stage != 'rearing':
            raise UserError(_("Only flocks in 'Rearing / Pre-Laying' stage can be transitioned to 'Laying'."))
        self.write({
            'flock_stage': 'laying',
            'laying_start_date': fields.Date.context_today(self),
            'laying_start_bird_count': self.live_bird_count,
        })
        self.activity_feedback([POINT_OF_LAY_ACTIVITY], feedback=_("Laying Phase started."))
        age = f"{self.flock_age_weeks:.1f}"
        if automatic:
            body = _("Laying Phase started automatically at %(age)s weeks.", age=age)
        else:
            body = _("Laying Phase started by %(user)s at %(age)s weeks.", user=self.env.user.name, age=age)
        if reason:
            body = f"{body} {reason}"
        self._post_stage_note(body + " " + _("The pre-laying flock investment is now locked."))

    def action_back_to_rearing(self):
        """Manager button: correct a flock that was moved to Laying by mistake."""
        self.ensure_one()
        self._check_flock_stage_change(['laying'])
        self.write({'flock_stage': 'rearing', 'laying_start_date': False, 'laying_start_bird_count': 0,
                    'laying_notification_sent': False})
        self._post_stage_note(_("Flock moved back to Rearing / Pre-Laying by %(user)s at %(age)s weeks.",
                                user=self.env.user.name, age=f"{self.flock_age_weeks:.1f}"))
        return True

    def action_mark_spent(self):
        """Manager button: the laying cycle is over; the flock becomes Spent Hen / Depleted."""
        self.ensure_one()
        self._check_flock_stage_change(['laying'])
        self.write({'flock_stage': 'spent', 'depletion_date': fields.Date.context_today(self)})
        self._post_stage_note(_("Flock marked as Spent / Depleted by %(user)s at %(age)s weeks.",
                                user=self.env.user.name, age=f"{self.flock_age_weeks:.1f}"))
        return True

    def action_close_broiler_batch(self):
        """Manager button: every bird of the broiler batch has left its shed (harvests, mortality)."""
        self.ensure_one()
        self._check_flock_stage_change(['growing'])
        if self.live_bird_count:
            raise UserError(_("Batch %(batch)s still has %(birds)s live birds: harvest them, or record their "
                              "mortality, before closing it.", batch=self.name, birds=self.live_bird_count))
        self._close_broiler_batch()
        return True

    def _close_broiler_batch(self, date=None):
        """Close the batch (Spent / Depleted) and expense what is left in its Broiler Cost Pool."""
        self.ensure_one()
        date = date or fields.Date.context_today(self)
        self.write({'flock_stage': 'spent', 'depletion_date': date})
        written_off = self._broiler_write_off_pool(date)
        body = _("Broiler batch closed at %(days)s days.", days=self.flock_age_days)
        if written_off:
            body += " " + _("%(amount)s of batch cost that no harvest released was expensed.",
                            amount=format_amount(self.env, written_off, self.currency_id))
        self._post_stage_note(body)

    def _broiler_write_off_pool(self, date):
        """Expense the cost left in the Broiler Cost Pool of a batch being closed (e.g. birds that died to the
        last one, or left the batch other than by a harvest). Returns the amount written off."""
        self.ensure_one()
        currency = self.currency_id
        pool = currency.round(self._get_broiler_cost_figures().get(self.id, {}).get('pool', 0.0))
        if currency.is_zero(pool):
            return 0.0
        company = self.company_id or self.env.company
        pool_account = company._get_farm_broiler_cost_location().valuation_account_id
        accounts = self.product_id.product_tmpl_id.with_company(company).get_product_accounts()
        # without an account on the pool location, the capitalized costs were never posted: nothing to reverse
        if pool_account and accounts['expense']:
            label = _("%s - batch cost written off at closing", self.name)
            entry = self.env['account.move'].sudo().with_company(company).create({
                'journal_id': (company.account_stock_journal_id or accounts['stock_journal']).id,
                'date': date,
                'ref': label,
                'move_type': 'entry',
                'line_ids': [
                    Command.create({'name': label, 'account_id': accounts['expense'].id, 'balance': pool}),
                    Command.create({'name': label, 'account_id': pool_account.id, 'balance': -pool}),
                ],
            })
            entry._post()
        self.broiler_written_off_cost += pool
        return pool

    def action_allocate_to_cages(self):
        """Shortcut from the flock: open the Brooding-to-Cage wizard on the nursery holding it."""
        self.ensure_one()
        brooding = self._get_brooding_locations()
        if not brooding:
            raise UserError(_("Flock %s has no birds in a brooding nursery.", self.display_name))
        action = brooding[0].action_allocate_birds()
        action['context'] = {**action['context'], 'default_lot_id': self.id}
        return action

    def action_view_live_birds(self):
        self.ensure_one()
        action = self.env['stock.quant']._get_quants_action()
        action['name'] = action['display_name'] = _("Live Birds of %s", self.display_name)
        action['domain'] = [('lot_id', '=', self.id), ('location_id.usage', '=', 'internal')]
        return action
