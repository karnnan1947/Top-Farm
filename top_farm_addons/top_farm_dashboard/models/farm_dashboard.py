from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError
from odoo.tools import formatLang

GRADES = ('jumbo', 'large', 'medium', 'damage')
GRADE_LABELS = {'jumbo': 'Jumbo', 'large': 'Large', 'medium': 'Medium', 'damage': 'Damaged'}


class FarmDashboard(models.AbstractModel):
    _name = 'farm.dashboard'
    _description = 'Top Farm Executive Dashboard Data'

    @api.model
    def get_kpis(self, date_from=False, date_to=False, flock_id=False, trend_days=7):
        if not self.env.user.has_group('top_farm_core.group_farm_user'):
            raise AccessError(_("You do not have access to the farm dashboard."))
        today = fields.Date.context_today(self)
        date_to = fields.Date.to_date(date_to) or today
        date_from = fields.Date.to_date(date_from) or date_to
        if date_from > date_to:
            date_from, date_to = date_to, date_from
        company_ids = self.env.companies.ids
        cfg = self.env['farm.dashboard.config']._get_config()
        flock_id = flock_id or False

        env = self.sudo().env
        # Live population: the birds of the active flocks, in brooding nurseries and cages
        flock_domain = [('is_flock_batch', '=', True), ('flock_stage', '!=', 'spent'),
                        ('company_id', 'in', company_ids + [False])]
        flocks = env['stock.lot'].search(flock_domain, order='farm_arrival_date desc, name')
        counted = flocks.filtered(lambda f: f.id == flock_id) if flock_id else flocks
        counts = counted._get_live_bird_counts()
        live = int(sum(counts.values()))
        by_stage = {stage: 0 for stage in ('brooding', 'rearing', 'laying')}
        for flock in counted:
            by_stage[flock.flock_stage] = by_stage.get(flock.flock_stage, 0) + counts.get(flock.id, 0)

        # Eggs, hen-day and FCR from the produced (done) collections of the period
        col_domain = [('state', '=', 'done'), ('company_id', 'in', company_ids),
                      ('date', '>=', date_from), ('date', '<=', date_to)]
        if flock_id:
            col_domain.append(('flock_lot_id', '=', flock_id))
        Collection = env['farm.egg.collection']
        totals = Collection._read_group(
            col_domain, [], ['qty_jumbo:sum', 'qty_large:sum', 'qty_medium:sum', 'qty_damage:sum',
                             'total_egg_qty:sum', 'confirmed_live_bird_count:sum', 'feed_consumed_qty:sum'])[0]
        by_grade = dict(zip(GRADES, totals[:4]))
        eggs, bird_days, feed = totals[4] or 0, totals[5] or 0, totals[6] or 0.0
        hen_day = round(eggs / bird_days * 100.0, 2) if bird_days else 0.0
        fcr = round(feed / (eggs / 12.0), 3) if eggs else 0.0

        # Mortality of the period (only logs that really scrapped birds). Same basis as Mortality BI and as the
        # approval threshold: dead birds over the opening population of each flock-day, so a period of several
        # days gives the average daily rate and is compared with the daily threshold like for like.
        log_domain = [('company_id', 'in', company_ids), ('date', '>=', date_from), ('date', '<=', date_to)]
        bi_domain = list(log_domain)
        if flock_id:
            log_domain.append(('lot_id', '=', flock_id))
            bi_domain.append(('flock_lot_id', '=', flock_id))
        dead, base = env['farm.mortality.bi']._read_group(
            bi_domain, [], ['dead_bird_count:sum', 'population_base:sum'])[0]
        dead, base = dead or 0, base or 0
        pending = env['farm.mortality.log'].search_count(log_domain + [('state', '=', 'waiting_approval')])
        mortality = round(dead / base * 100.0, 3) if base else 0.0
        alert = cfg.mortality_alert_pct or env['farm.mortality.config']._get_config().daily_mortality_threshold_pct

        # Daily harvest trend
        days = max(int(trend_days or 7), 1)
        t_from = date_to - timedelta(days=days - 1)
        t_domain = [('state', '=', 'done'), ('company_id', 'in', company_ids), ('date', '>=', t_from),
                    ('date', '<=', date_to)]
        if flock_id:
            t_domain.append(('flock_lot_id', '=', flock_id))
        rows = Collection._read_group(
            t_domain, ['date:day'], ['qty_jumbo:sum', 'qty_large:sum', 'qty_medium:sum', 'qty_damage:sum'])
        per_day = {day: vals for day, *vals in rows}
        trend = []
        for i in range(days):
            day = t_from + timedelta(days=i)
            vals = per_day.get(day, [0, 0, 0, 0])
            trend.append({'date': fields.Date.to_string(day), **dict(zip(GRADES, [v or 0 for v in vals]))})

        grade_mix = [{'grade': g, 'label': GRADE_LABELS[g], 'qty': by_grade[g] or 0,
                      'pct': round((by_grade[g] or 0) / eggs * 100.0, 1) if eggs else 0.0} for g in GRADES]
        stages = dict(env['stock.lot']._fields['flock_stage'].selection)
        detail = " · ".join(f"{formatLang(self.env, birds, digits=0)} {stages[stage].lower()}"
                            for stage, birds in by_stage.items() if birds)
        return {
            'date_from': fields.Date.to_string(date_from), 'date_to': fields.Date.to_string(date_to),
            'live_population': live,
            'population_detail': detail or _("birds of the active flocks now"),
            'eggs': eggs,
            'hen_day': hen_day, 'hen_day_ok': (hen_day >= cfg.target_hen_day_pct) if eggs else None,
            'target_hen_day': cfg.target_hen_day_pct,
            'fcr': fcr, 'fcr_ok': (fcr <= cfg.target_fcr) if eggs else None, 'target_fcr': cfg.target_fcr,
            'feed_kg': feed,
            'dead': dead, 'mortality_base': base, 'multi_day': date_from != date_to,
            'mortality': mortality, 'mortality_ok': mortality <= alert,
            'mortality_alert': alert, 'pending_approval': pending,
            'grade_mix': grade_mix, 'trend': trend,
            'flocks': [{'id': f.id, 'name': f"{f.name} ({stages.get(f.flock_stage, '')})"} for f in flocks],
        }
