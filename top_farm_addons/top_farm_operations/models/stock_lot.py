# -*- coding: utf-8 -*-
from datetime import timedelta

from markupsafe import Markup

from odoo import api, fields, models, _

from odoo.addons.top_farm_core.models.stock_lot import POINT_OF_LAY_ACTIVITY


class StockLot(models.Model):
    _inherit = 'stock.lot'

    farm_flock_lot_id = fields.Many2one(
        'stock.lot', string='Parent Flock', index='btree_not_null', copy=False, readonly=True,
        help="Flock that laid the eggs of this lot. Set when the egg collection creates the lot; "
             "never parsed from the lot name.")
    farm_production_date = fields.Date(
        string='Egg Production Date', index='btree_not_null', copy=False, readonly=True)
    rolling_hen_day_pct = fields.Float(
        string='Rolling Hen-Day (%)', compute='_compute_rolling_hen_day', digits=(16, 1),
        help="Eggs over live bird days of the flock's cages on the rolling window of the Top Farm settings, "
             "up to today. The Laying Phase benchmark is checked against it.")

    def _compute_rolling_hen_day(self):
        for lot in self:
            lot.rolling_hen_day_pct = lot._origin._get_rolling_hen_day()[0] if lot.is_flock_batch else 0.0

    def _get_rolling_hen_day(self, end_date=None):
        """(hen-day %, eggs, live bird days) of the flock over the rolling window ending on `end_date`.
        Each cage holding the flock counts its birds once per day: the collection's snapshot when the cage was
        collected, else the flock's birds in it now with no eggs, so a day without a harvest pulls the rate down."""
        self.ensure_one()
        if not self.id:
            return 0.0, 0, 0
        company = self.company_id or self.env.company
        end = end_date or fields.Date.context_today(self)
        start = end - timedelta(days=company.laying_rolling_days - 1)
        if self.cage_allocation_date:
            start = max(start, self.cage_allocation_date)
        if start > end:
            return 0.0, 0, 0
        collections = self.env['farm.egg.collection'].sudo().search([
            ('flock_lot_id', '=', self.id), ('state', '=', 'done'), ('date', '>=', start), ('date', '<=', end)])
        eggs = sum(collections.mapped('total_egg_qty'))
        collected = {(c.cage_location_id.id, c.date): c.confirmed_live_bird_count for c in collections}
        bird_days = sum(collected.values())
        cages = self.flock_location_ids.filtered(lambda l: l.farm_hierarchy_level == 'cage')
        birds_now = cages._get_live_bird_counts(self)
        for offset in range((end - start).days + 1):
            day = start + timedelta(days=offset)
            bird_days += sum(birds for cage_id, birds in birds_now.items() if (cage_id, day) not in collected)
        rate = round(eggs / bird_days * 100.0, 2) if bird_days else 0.0
        return rate, eggs, bird_days

    # -------------------------------------------------------------------------
    # LAYING TRANSITION ENGINE (50 % hen-day benchmark)
    # -------------------------------------------------------------------------
    def _farm_check_laying_transition(self, end_date=None):
        """Rearing flocks that are old enough and sustain the hen-day benchmark: alert the Farm Managers once,
        or start the Laying Phase in automatic mode. The calendar never forces the transition."""
        for flock in self.filtered(lambda l: l.is_flock_batch and l.flock_stage == 'rearing'):
            company = flock.company_id or self.env.company
            if not flock.farm_arrival_date or flock.flock_age_weeks < company.laying_min_age_weeks:
                continue
            rate, eggs, bird_days = flock._get_rolling_hen_day(end_date)
            if rate < company.laying_hen_day_threshold_pct:
                continue
            if company.laying_transition_mode == 'automatic':
                flock._start_laying_phase(automatic=True, reason=_(
                    "The %(days)s-day rolling hen-day rate reached %(rate)s%% (%(eggs)s eggs over %(bird_days)s "
                    "live bird days; benchmark %(threshold)s%%).",
                    days=company.laying_rolling_days, rate=f"{rate:.1f}", eggs=eggs, bird_days=bird_days,
                    threshold=f"{company.laying_hen_day_threshold_pct:g}"))
            elif not flock.laying_notification_sent:
                flock._send_laying_ready_alert(rate)

    def _send_laying_ready_alert(self, rate):
        """Post the point-of-lay alert and give each Farm Manager a To-Do on the flock."""
        self.ensure_one()
        company = self.company_id or self.env.company
        note = Markup("<p>%s</p><p>%s</p>") % (
            _("Flock %(flock)s has reached %(rate)s%% laying production (%(days)s-day rolling hen-day, "
              "benchmark %(threshold)s%%) at %(age)s weeks. Ready to transition to Laying Phase.",
              flock=self.name, rate=f"{rate:.1f}", days=company.laying_rolling_days,
              threshold=f"{company.laying_hen_day_threshold_pct:g}", age=f"{self.flock_age_weeks:.1f}"),
            _("A Farm Manager confirms it with Start Laying Phase: the pre-laying investment is then locked "
              "and the daily feed becomes a component of the eggs."),
        )
        managers = self.env.ref('top_farm_core.group_farm_manager').all_user_ids.filtered(
            lambda u: u.active and not u.share and company in u.company_ids)
        for manager in managers:
            self.activity_schedule(POINT_OF_LAY_ACTIVITY, note=note, user_id=manager.id)
        self.message_post(body=note, subtype_xmlid='mail.mt_note', partner_ids=managers.partner_id.ids)
        self.laying_notification_sent = True

    @api.model
    def _cron_check_laying_transition(self):
        """Daily check of the rearing flocks on complete days only (up to yesterday): today's harvests may
        not be entered yet."""
        yesterday = fields.Date.context_today(self) - timedelta(days=1)
        flocks = self.search([('is_flock_batch', '=', True), ('flock_stage', '=', 'rearing')])
        flocks._farm_check_laying_transition(yesterday)

    def action_view_egg_collections(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('top_farm_operations.action_farm_egg_collection')
        action['domain'] = [('flock_lot_id', '=', self.id)]
        action['context'] = {'default_flock_lot_id': self.id}
        return action

    def action_view_feed_logs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('top_farm_operations.action_farm_feed_log')
        action['domain'] = [('flock_lot_id', '=', self.id)]
        action['context'] = {'default_flock_lot_id': self.id}
        return action
