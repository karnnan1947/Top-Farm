from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError
from odoo.tools import SQL, formatLang

from odoo.addons.top_farm_core.models.stock_lot import BROILER_LIVE_STAGES, FLOCK_END_STAGES

GRADES = ('jumbo', 'large', 'medium', 'damage')
GRADE_LABELS = {'jumbo': 'Jumbo', 'large': 'Large', 'medium': 'Medium', 'damage': 'Damaged'}
# closed broiler batches are still offered in the broiler dashboard's batch filter this many days after closing
CLOSED_BATCH_DAYS = 120
# a user sees a dashboard when its group is enabled on the user (Farm Dashboards tab of the user form)
LAYER_GROUP = 'top_farm_dashboard.group_farm_layer_dashboard'
BROILER_GROUP = 'top_farm_dashboard.group_farm_broiler_dashboard'


class FarmDashboard(models.AbstractModel):
    _name = 'farm.dashboard'
    _description = 'Top Farm Executive Dashboard Data'

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------
    def _check_dashboard_access(self, group, dashboard):
        """A farm user with the dashboard enabled on the user (Flock / Layer Dashboard or Broiler Dashboard)."""
        user = self.env.user
        if not (user.has_group('top_farm_core.group_farm_user') and user.has_group(group)):
            raise AccessError(_("You do not have permission to view the %s.", dashboard))

    @api.model
    def _get_period(self, date_from, date_to):
        today = fields.Date.context_today(self)
        date_to = fields.Date.to_date(date_to) or today
        date_from = fields.Date.to_date(date_from) or date_to
        if date_from > date_to:
            date_from, date_to = date_to, date_from
        return date_from, date_to

    @api.model
    def _live_birds_by_day(self, lots, date_from, date_to):
        """{lot id: {date: birds of the lot present that day}} for every day of [date_from, date_to]: the larger of
        its birds in internal locations at the start and at the end of the day (the chicks placed that day count,
        and so do the birds harvested that day: they were fed before leaving), replayed from the done stock moves
        (placements, transfers out, harvests and cullings on their date; a mortality scrap, or its reversal, on the
        incident date of its log)."""
        lots = lots.filtered('id')
        if not lots or date_from > date_to:
            return {}
        self.env.flush_all()
        tz = self.env.context.get('tz') or self.env.user.tz or 'UTC'
        rows = self.env.execute_query(SQL("""
            SELECT x.lot_id, GREATEST(x.day, %(start)s::date) AS day,
                   SUM(CASE WHEN x.day >= %(start)s::date THEN x.qty ELSE 0 END) AS qty,
                   SUM(CASE WHEN x.day < %(start)s::date THEN x.qty ELSE 0 END) AS before
              FROM (
                SELECT sml.lot_id,
                       COALESCE(ml.date, (sm.date AT TIME ZONE 'UTC' AT TIME ZONE %(tz)s)::date) AS day,
                       CASE WHEN dst.usage = 'internal' THEN sml.quantity_product_uom
                            ELSE -sml.quantity_product_uom END AS qty
                  FROM stock_move_line sml
                  JOIN stock_move sm ON sm.id = sml.move_id
                  JOIN stock_location src ON src.id = sml.location_id
                  JOIN stock_location dst ON dst.id = sml.location_dest_id
                  LEFT JOIN farm_mortality_log ml ON ml.id = sm.farm_mortality_log_id
                 WHERE sm.state = 'done' AND sml.lot_id IN %(lots)s
                   AND (src.usage = 'internal') <> (dst.usage = 'internal')
              ) x
             WHERE x.day <= %(end)s::date
             GROUP BY 1, 2
        """, start=date_from, end=date_to, tz=tz, lots=tuple(lots.ids)))
        deltas = defaultdict(dict)
        opening = defaultdict(float)
        for lot_id, day, qty, before in rows:
            deltas[lot_id][day] = qty
            opening[lot_id] += before
        days = [date_from + timedelta(days=i) for i in range((date_to - date_from).days + 1)]
        result = {}
        for lot_id in lots.ids:
            running, series = opening[lot_id], {}
            for day in days:
                start = running
                running += deltas[lot_id].get(day, 0.0)
                series[day] = round(max(start, running))
            result[lot_id] = series
        return result

    def _hen_housed(self, collections):
        """(hen-housed %, hens housed) of produced egg collections: the eggs over the hens housed at point of lay
        (birds at the start of the Laying Phase; the chicks placed while the flock is still pre-laying), counted for
        the share of the flock's birds collected that day. Hen-day % divides by the hens alive that day instead:
        the gap between the two is the mortality and culling since the point of lay."""
        if not collections:
            return 0.0, 0
        flocks = collections.flock_lot_id
        housed = {flock.id: flock.laying_start_bird_count or flock.initial_bird_count for flock in flocks}
        dates = collections.mapped('date')
        live = self._live_birds_by_day(flocks, min(dates), max(dates))
        collected = defaultdict(int)
        for collection in collections:
            collected[collection.flock_lot_id.id, collection.date] += collection.confirmed_live_bird_count
        basis = 0.0
        for (flock_id, day), birds in collected.items():
            alive = max(live.get(flock_id, {}).get(day, 0), birds)
            if alive:
                basis += housed[flock_id] * birds / alive
        eggs = sum(collections.mapped('total_egg_qty'))
        return (round(eggs / basis * 100.0, 2) if basis else 0.0), sum(housed.values())

    # -------------------------------------------------------------------------
    # LAYER DASHBOARD
    # -------------------------------------------------------------------------
    @api.model
    def get_kpis(self, date_from=False, date_to=False, flock_id=False, trend_days=7):
        """Kept for the callers of the former mixed dashboard: the layer KPIs."""
        return self.get_layer_kpis(date_from, date_to, flock_id, trend_days)

    @api.model
    def get_layer_kpis(self, date_from=False, date_to=False, flock_id=False, trend_days=7):
        """Layer Performance Dashboard: live hens, hen-day and hen-housed production, laying feed per hen and per
        dozen eggs, mortality, grade mix and daily harvest trend of the layer flocks (broilers never lay)."""
        self._check_dashboard_access(LAYER_GROUP, _("Layer Performance Dashboard"))
        date_from, date_to = self._get_period(date_from, date_to)
        company_ids = self.env.companies.ids
        cfg = self.env['farm.dashboard.config']._get_config()
        flock_id = int(flock_id) if flock_id else False

        env = self.sudo().env
        # Live population: the hens of the active layer flocks, in brooding nurseries and cages
        flocks = env['stock.lot'].search([
            ('is_flock_batch', '=', True), ('flock_type', '=', 'layer'), ('flock_stage', 'not in', FLOCK_END_STAGES),
            ('company_id', 'in', company_ids + [False])], order='farm_arrival_date desc, name')
        counted = flocks.filtered(lambda f: f.id == flock_id) if flock_id else flocks
        counts = counted._get_live_bird_counts()
        live = int(sum(counts.values()))
        by_stage = {stage: 0 for stage in ('brooding', 'rearing', 'laying')}
        for flock in counted:
            by_stage[flock.flock_stage] = by_stage.get(flock.flock_stage, 0) + counts.get(flock.id, 0)

        # Eggs, hen-day, hen-housed, feed per hen and FCR from the produced (done) collections of the period
        col_domain = [('state', '=', 'done'), ('company_id', 'in', company_ids),
                      ('flock_lot_id.flock_type', '=', 'layer'), ('date', '>=', date_from), ('date', '<=', date_to)]
        if flock_id:
            col_domain.append(('flock_lot_id', '=', flock_id))
        Collection = env['farm.egg.collection']
        totals = Collection._read_group(
            col_domain, [], ['qty_jumbo:sum', 'qty_large:sum', 'qty_medium:sum', 'qty_damage:sum',
                             'total_egg_qty:sum', 'confirmed_live_bird_count:sum'])[0]
        by_grade = dict(zip(GRADES, totals[:4]))
        eggs, bird_days = totals[4] or 0, totals[5] or 0
        hen_day = round(eggs / bird_days * 100.0, 2) if bird_days else 0.0
        # laying feed is staged per cage: feed per hen and per dozen over the collections that consumed feed
        feed, fed_birds, fed_eggs = Collection._read_group(
            col_domain + [('feed_consumed_qty', '>', 0)], [],
            ['feed_consumed_qty:sum', 'confirmed_live_bird_count:sum', 'total_egg_qty:sum'])[0]
        feed, fed_birds, fed_eggs = feed or 0.0, fed_birds or 0, fed_eggs or 0
        fcr = round(feed / (fed_eggs / 12.0), 3) if fed_eggs else 0.0
        feed_per_hen = round(feed * 1000.0 / fed_birds, 1) if fed_birds else 0.0
        hen_housed, housed_birds = self._hen_housed(Collection.search(col_domain))

        # Mortality of the period (only logs that really scrapped birds). Same basis as Mortality BI and as the
        # approval threshold: dead birds over the opening population of each flock-day, so a period of several
        # days gives the average daily rate and is compared with the daily threshold like for like.
        log_domain = [('company_id', 'in', company_ids), ('date', '>=', date_from), ('date', '<=', date_to),
                      ('lot_id.flock_type', '=', 'layer')]
        bi_domain = [('company_id', 'in', company_ids), ('date', '>=', date_from), ('date', '<=', date_to),
                     ('flock_lot_id.flock_type', '=', 'layer')]
        if flock_id:
            log_domain.append(('lot_id', '=', flock_id))
            bi_domain.append(('flock_lot_id', '=', flock_id))
        dead, base = env['farm.mortality.bi']._read_group(
            bi_domain, [], ['dead_bird_count:sum', 'population_base:sum'])[0]
        dead, base = dead or 0, base or 0
        pending = env['farm.mortality.log'].search_count(log_domain + [('state', '=', 'waiting_approval')])
        mortality = round(dead / base * 100.0, 3) if base else 0.0
        alert = cfg.mortality_alert_pct or env['farm.mortality.config']._get_config().daily_mortality_threshold_pct
        # cumulative mortality of the flocks shown, from their placement to the end of the period
        cum_flocks = env['stock.lot'].browse(flock_id) if flock_id else flocks
        cum_dead = env['farm.mortality.log']._read_group(
            [('lot_id', 'in', cum_flocks.ids), ('state', '=', 'done'), ('date', '<=', date_to)],
            [], ['dead_bird_count:sum'])[0][0] or 0
        placed = sum(cum_flocks.mapped('initial_bird_count'))
        cumulative_mortality = round(cum_dead / placed * 100.0, 2) if placed else 0.0

        # Daily harvest trend, with the hen-day % of each day
        days = max(int(trend_days or 7), 1)
        t_from = date_to - timedelta(days=days - 1)
        t_domain = [('state', '=', 'done'), ('company_id', 'in', company_ids), ('flock_lot_id.flock_type', '=', 'layer'),
                    ('date', '>=', t_from), ('date', '<=', date_to)]
        if flock_id:
            t_domain.append(('flock_lot_id', '=', flock_id))
        rows = Collection._read_group(
            t_domain, ['date:day'], ['qty_jumbo:sum', 'qty_large:sum', 'qty_medium:sum', 'qty_damage:sum',
                                     'total_egg_qty:sum', 'confirmed_live_bird_count:sum'])
        per_day = {day: vals for day, *vals in rows}
        trend = []
        for i in range(days):
            day = t_from + timedelta(days=i)
            vals = [v or 0 for v in per_day.get(day, [0] * 6)]
            trend.append({
                'date': fields.Date.to_string(day), **dict(zip(GRADES, vals[:4])),
                'hen_day': round(vals[4] / vals[5] * 100.0, 2) if vals[5] else None,
            })

        grade_mix = [{'grade': g, 'label': GRADE_LABELS[g], 'qty': by_grade[g] or 0,
                      'pct': round((by_grade[g] or 0) / eggs * 100.0, 1) if eggs else 0.0} for g in GRADES]
        stages = dict(env['stock.lot']._fields['flock_stage'].selection)
        detail = " · ".join(f"{formatLang(self.env, birds, digits=0)} {stages[stage].lower()}"
                            for stage, birds in by_stage.items() if birds)
        return {
            'date_from': fields.Date.to_string(date_from), 'date_to': fields.Date.to_string(date_to),
            'live_population': live,
            'population_detail': detail or _("hens of the active layer flocks now"),
            'eggs': eggs, 'bird_days': bird_days,
            'hen_day': hen_day, 'hen_day_ok': (hen_day >= cfg.target_hen_day_pct) if eggs else None,
            'target_hen_day': cfg.target_hen_day_pct,
            'hen_housed': hen_housed, 'housed_birds': housed_birds,
            'fcr': fcr, 'fcr_ok': (fcr <= cfg.target_fcr) if fed_eggs else None, 'target_fcr': cfg.target_fcr,
            'feed_kg': feed, 'feed_per_hen_g': feed_per_hen, 'fed_bird_days': fed_birds,
            'dead': dead, 'mortality_base': base, 'multi_day': date_from != date_to,
            'mortality': mortality, 'mortality_ok': mortality <= alert,
            'mortality_alert': alert, 'pending_approval': pending,
            'cumulative_mortality': cumulative_mortality, 'cumulative_dead': cum_dead, 'placed': placed,
            'grade_mix': grade_mix, 'trend': trend,
            'flocks': [{'id': f.id, 'name': f"{f.name} ({stages.get(f.flock_stage, '')})"} for f in flocks],
        }

    # -------------------------------------------------------------------------
    # BROILER DASHBOARD
    # -------------------------------------------------------------------------
    @api.model
    def get_broiler_kpis(self, date_from=False, date_to=False, flock_id=False):
        """Broiler Performance Dashboard: live broilers, live biomass (live birds x the batch's estimated average
        weight), batch FCR (feed kg / live weight kg), cumulative mortality over the batch, the daily feed intake
        (booster, starter, finisher) and a summary of the broiler batches. Batch figures cover each batch from its
        placement; the period (From / To) drives the daily feed intake."""
        self._check_dashboard_access(BROILER_GROUP, _("Broiler Performance Dashboard"))
        date_from, date_to = self._get_period(date_from, date_to)
        today = fields.Date.context_today(self)
        company_ids = self.env.companies.ids
        cfg = self.env['farm.dashboard.config']._get_config()
        flock_id = int(flock_id) if flock_id else False

        env = self.sudo().env
        Lot = env['stock.lot']
        stages = dict(Lot._fields['flock_stage'].selection)
        base_domain = [('is_flock_batch', '=', True), ('flock_type', '=', 'broiler'),
                       ('company_id', 'in', company_ids + [False])]
        batches = Lot.search(base_domain + [
            '|', ('flock_stage', 'in', BROILER_LIVE_STAGES),
            '&', ('flock_stage', '=', 'closed'), ('depletion_date', '>=', today - timedelta(days=CLOSED_BATCH_DAYS)),
        ], order='farm_arrival_date desc, name')
        if flock_id:
            selected = Lot.search(base_domain + [('id', '=', flock_id)])
            batches |= selected
        else:
            selected = batches.filtered(lambda b: b.flock_stage in BROILER_LIVE_STAGES)

        counts = selected._get_live_bird_counts()
        dead_by_batch = {lot.id: dead for lot, dead in env['farm.mortality.log']._read_group(
            [('lot_id', 'in', selected.ids), ('state', '=', 'done')], ['lot_id'], ['dead_bird_count:sum'])}

        rows = []
        for batch in selected:
            live = counts.get(batch.id, 0)
            alive_stage = batch.flock_stage in BROILER_LIVE_STAGES
            abw = batch.broiler_avg_weight
            biomass = live * abw if alive_stage else 0.0
            produced = batch.broiler_harvested_weight + biomass
            if batch.flock_stage == 'closed' and batch.depletion_date and batch.farm_arrival_date:
                age = (batch.depletion_date - batch.farm_arrival_date).days
            else:
                age = batch.flock_age_days
            dead = dead_by_batch.get(batch.id, 0)
            rows.append({
                'id': batch.id, 'name': batch.name, 'stage': stages.get(batch.flock_stage, ''),
                'alive_stage': alive_stage, 'age': age, 'placed': batch.initial_bird_count, 'live': live,
                'dead': dead, 'mortality': round(dead / batch.initial_bird_count * 100.0, 2)
                if batch.initial_bird_count else 0.0,
                'harvested_birds': batch.broiler_harvested_birds,
                'harvested_kg': round(batch.broiler_harvested_weight, 2),
                'abw': round(abw, 3), 'biomass': round(biomass, 2), 'feed_kg': round(batch.broiler_feed_qty, 2),
                'fcr': round(batch.broiler_feed_qty / produced, 3) if produced else 0.0,
            })

        # Batch totals of the cards
        live_total = sum(r['live'] for r in rows)
        placed_total = sum(r['placed'] for r in rows)
        dead_total = sum(r['dead'] for r in rows)
        biomass_total = sum(r['biomass'] for r in rows)
        harvested_kg = sum(r['harvested_kg'] for r in rows)
        harvested_birds = sum(r['harvested_birds'] for r in rows)
        feed_total = sum(r['feed_kg'] for r in rows)
        produced_total = harvested_kg + biomass_total
        fcr = round(feed_total / produced_total, 3) if produced_total else 0.0
        abw = round(biomass_total / live_total, 3) if live_total else 0.0
        mortality = round(dead_total / placed_total * 100.0, 2) if placed_total else 0.0

        # Daily feed intake of the period (feed lines of the batches' confirmed feed logs), by feed product
        lines = env['farm.feed.log.line'].search([
            ('log_id.flock_lot_id', 'in', selected.ids), ('log_id.state', '=', 'reconciled'),
            ('log_id.date', '>=', date_from), ('log_id.date', '<=', date_to), ('is_medication', '=', False)])
        kg = env.ref('uom.product_uom_kgm')
        feed_by_day = defaultdict(lambda: defaultdict(float))
        fed_batches = defaultdict(set)
        first_use = {}
        for line in lines:
            day = line.log_id.date
            feed_by_day[day][line.product_id.id] += line._get_qty_in(kg)
            fed_batches[day].add(line.log_id.flock_lot_id.id)
            first_use[line.product_id] = min(first_use.get(line.product_id, day), day)
        products = sorted(first_use, key=lambda p: (first_use[p], p.display_name))
        live_by_day = self._live_birds_by_day(selected, date_from, date_to) if lines else {}
        feed_days, period_feed, period_bird_days = [], 0.0, 0
        for i in range((date_to - date_from).days + 1):
            day = date_from + timedelta(days=i)
            day_feed = feed_by_day.get(day, {})
            total = sum(day_feed.values())
            birds = sum(live_by_day.get(batch_id, {}).get(day, 0) for batch_id in fed_batches.get(day, ()))
            if total and birds:
                period_feed += total
                period_bird_days += birds
            feed_days.append({
                'date': fields.Date.to_string(day),
                'kg': {str(p.id): round(day_feed.get(p.id, 0.0), 2) for p in products},
                'total': round(total, 2), 'birds': birds,
                'intake_g': round(total * 1000.0 / birds, 1) if total and birds else None,
            })
        intake = round(period_feed * 1000.0 / period_bird_days, 1) if period_bird_days else 0.0

        return {
            'date_from': fields.Date.to_string(date_from), 'date_to': fields.Date.to_string(date_to),
            'single': bool(flock_id), 'batch_count': len(selected),
            'live': live_total, 'placed': placed_total, 'dead': dead_total,
            'biomass': round(biomass_total, 2), 'abw': abw,
            'harvested_birds': harvested_birds, 'harvested_kg': round(harvested_kg, 2),
            'feed_kg': round(feed_total, 2), 'fcr': fcr, 'target_fcr': cfg.target_broiler_fcr,
            'fcr_ok': (fcr <= cfg.target_broiler_fcr) if fcr else None,
            'mortality': mortality, 'mortality_alert': cfg.broiler_mortality_alert_pct,
            'mortality_ok': mortality <= cfg.broiler_mortality_alert_pct if placed_total else None,
            'intake_g': intake, 'period_feed_kg': round(period_feed, 2),
            'feed_products': [{'id': str(p.id), 'name': p.display_name} for p in products],
            'feed_days': feed_days,
            'rows': rows,
            'batches': [{'id': b.id, 'name': f"{b.name} ({stages.get(b.flock_stage, '')})"} for b in batches],
        }
