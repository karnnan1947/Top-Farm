from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError

GRADES = ('jumbo', 'large', 'medium', 'damage')
GRADE_LABELS = {'jumbo': 'Jumbo', 'large': 'Large', 'medium': 'Medium', 'damage': 'Damaged'}


class FarmDashboard(models.AbstractModel):
    _name = 'farm.dashboard'
    _description = 'Top Farm Executive Dashboard Data'

    @api.model
    def get_kpis(self, date_from=False, date_to=False, batch_id=False, trend_days=7):
        if not self.env.user.has_group('top_farm_core.group_farm_user'):
            raise AccessError(_("You do not have access to the farm dashboard."))
        today = fields.Date.context_today(self)
        date_to = fields.Date.to_date(date_to) or today
        date_from = fields.Date.to_date(date_from) or date_to
        if date_from > date_to:
            date_from, date_to = date_to, date_from
        company_ids = self.env.companies.ids
        cfg = self.env['farm.dashboard.config']._get_config()
        batch_id = batch_id or False

        env = self.sudo().env
        # Live population: cage locations only, so a batch is never counted on top of its cages
        cage_domain = [('farm_hierarchy_level', '=', 'cage'), ('company_id', 'in', company_ids + [False])]
        if batch_id:
            cage_domain.append(('parent_batch_location_id', '=', batch_id))
        cages = env['stock.location'].search(cage_domain)
        live = int(sum(cages._get_live_bird_counts().values()))

        # Eggs, hen-day and FCR from the produced (done) collections of the period
        col_domain = [('state', '=', 'done'), ('company_id', 'in', company_ids),
                      ('date', '>=', date_from), ('date', '<=', date_to)]
        if batch_id:
            col_domain.append(('batch_location_id', '=', batch_id))
        Collection = env['farm.egg.collection']
        totals = Collection._read_group(
            col_domain, [], ['qty_jumbo:sum', 'qty_large:sum', 'qty_medium:sum', 'qty_damage:sum',
                             'total_egg_qty:sum', 'confirmed_live_bird_count:sum', 'feed_consumed_qty:sum'])[0]
        by_grade = dict(zip(GRADES, totals[:4]))
        eggs, bird_days, feed = totals[4] or 0, totals[5] or 0, totals[6] or 0.0
        hen_day = round(eggs / bird_days * 100.0, 2) if bird_days else 0.0
        fcr = round(feed / (eggs / 12.0), 3) if eggs else 0.0

        # Mortality of the period (only logs that really scrapped birds)
        log_domain = [('company_id', 'in', company_ids), ('date', '>=', date_from), ('date', '<=', date_to)]
        if batch_id:
            log_domain.append(('batch_location_id', '=', batch_id))
        Log = env['farm.mortality.log']
        dead = Log._read_group(log_domain + [('state', '=', 'done')], [], ['dead_bird_count:sum'])[0][0] or 0
        pending = Log.search_count(log_domain + [('state', '=', 'waiting_approval')])
        flock = live + dead
        mortality = round(dead / flock * 100.0, 3) if flock else 0.0
        alert = cfg.mortality_alert_pct or env['farm.mortality.config']._get_config().daily_mortality_threshold_pct

        # Daily harvest trend
        days = max(int(trend_days or 7), 1)
        t_from = date_to - timedelta(days=days - 1)
        t_domain = [('state', '=', 'done'), ('company_id', 'in', company_ids), ('date', '>=', t_from),
                    ('date', '<=', date_to)]
        if batch_id:
            t_domain.append(('batch_location_id', '=', batch_id))
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
        return {
            'date_from': fields.Date.to_string(date_from), 'date_to': fields.Date.to_string(date_to),
            'live_population': live, 'eggs': eggs,
            'hen_day': hen_day, 'hen_day_ok': (hen_day >= cfg.target_hen_day_pct) if eggs else None,
            'target_hen_day': cfg.target_hen_day_pct,
            'fcr': fcr, 'fcr_ok': (fcr <= cfg.target_fcr) if eggs else None, 'target_fcr': cfg.target_fcr,
            'feed_kg': feed,
            'dead': dead, 'mortality': mortality, 'mortality_ok': mortality <= alert,
            'mortality_alert': alert, 'pending_approval': pending,
            'grade_mix': grade_mix, 'trend': trend,
            'batches': [{'id': b.id, 'name': b.display_name} for b in env['stock.location'].search(
                [('farm_hierarchy_level', '=', 'batch'), ('company_id', 'in', company_ids + [False])])],
        }
