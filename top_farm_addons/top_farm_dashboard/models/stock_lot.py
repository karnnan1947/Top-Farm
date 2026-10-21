from markupsafe import Markup

from odoo import _, fields, models
from odoo.tools import format_amount, format_date, formatLang

from .farm_flock_investment_report import COMPONENTS


class StockLot(models.Model):
    _inherit = 'stock.lot'

    investment_total_cost = fields.Monetary(
        string='Pre-Laying Investment', compute='_compute_investment', currency_field='currency_id',
        help="Chicks, feed, medication and other direct costs of the flock until the Laying Phase starts.")
    investment_bird_count = fields.Integer(string='Birds (Cost Basis)', compute='_compute_investment')
    investment_cost_per_bird = fields.Monetary(
        string='Investment per Live Bird', compute='_compute_investment', currency_field='currency_id',
        help="Pre-laying investment carried by each surviving bird: live birds now, or at the start of the "
             "Laying Phase once locked.")
    investment_cost_per_placed_bird = fields.Monetary(
        string='Investment per Placed Bird', compute='_compute_investment', currency_field='currency_id',
        help="Pre-laying investment per chick placed in the brooding nursery, dead or alive (baseline input cost).")
    investment_remaining_per_bird = fields.Monetary(
        string='Remaining Budget per Bird', compute='_compute_investment', currency_field='currency_id',
        help="Target pre-laying cost per bird of the Dashboard Settings, less the investment per bird so far.")
    investment_summary = fields.Html(
        string='Pre-Laying Flock Investment Report', compute='_compute_investment', sanitize=False)

    def _compute_investment(self):
        flocks = self._origin.filtered('is_flock_batch')
        components = {}
        if flocks:
            # the report is a SQL view over stock moves and analytic lines: write pending changes first
            self.env.flush_all()
            for flock, component, cost, quantity in self.env['farm.flock.investment.report'].sudo()._read_group(
                    [('flock_lot_id', 'in', flocks.ids)], ['flock_lot_id', 'component'],
                    ['cost:sum', 'quantity:sum']):
                components.setdefault(flock.id, {})[component] = (cost, quantity)
        for lot in self:
            rows = components.get(lot._origin.id)
            if not lot.is_flock_batch:
                lot.update({'investment_total_cost': 0.0, 'investment_bird_count': 0, 'investment_cost_per_bird': 0.0,
                            'investment_cost_per_placed_bird': 0.0, 'investment_remaining_per_bird': 0.0,
                            'investment_summary': False})
                continue
            rows = rows or {}
            birds = lot.laying_start_bird_count if lot.laying_start_date else lot.live_bird_count
            placed = lot.initial_bird_count
            total = sum(cost for cost, __ in rows.values())
            per_bird = total / birds if birds else 0.0
            cfg = self.env['farm.dashboard.config']._get_config(lot.company_id or self.env.company)
            lot.investment_total_cost = total
            lot.investment_bird_count = birds
            lot.investment_cost_per_bird = per_bird
            lot.investment_cost_per_placed_bird = total / placed if placed else 0.0
            lot.investment_remaining_per_bird = cfg.pre_laying_target_cost - per_bird
            lot.investment_summary = lot._render_investment_summary(rows, birds, placed, total, per_bird, cfg)

    def _render_investment_summary(self, rows, birds, placed, total, per_bird, cfg):
        """The Pre-Laying Flock Investment Report of the flock, as a table."""
        self.ensure_one()
        currency = self.currency_id

        def money(amount):
            return format_amount(self.env, amount, currency)

        def number(value, digits=0):
            return formatLang(self.env, value, digits=digits)

        feed_uoms = self.env['farm.flock.investment.report'].sudo().search(
            [('flock_lot_id', '=', self.id), ('component', '=', 'feed')]).product_id.uom_id
        units = {
            'chick': _("birds"),
            'feed': feed_uoms.name if len(feed_uoms) == 1 else '',
            'medication': _("units"),
        }
        def per(cost, count):
            return money(cost / count if count else 0.0)

        body = Markup()
        for component, label in COMPONENTS:
            cost, quantity = rows.get(component, (0.0, 0.0))
            qty_text = f"{number(quantity)} {units[component]}" if component in units and quantity else "—"
            body += Markup(
                "<tr><td>%s</td><td class='text-end'>%s</td><td class='text-end'>%s</td>"
                "<td class='text-end'>%s</td><td class='text-end'>%s</td></tr>") % (
                label, qty_text, money(cost), per(cost, placed), per(cost, birds))
        body += Markup(
            "<tr class='fw-bold border-top'><td>%s</td><td></td><td class='text-end'>%s</td>"
            "<td class='text-end'>%s</td><td class='text-end'>%s</td></tr>") % (
            _("TOTAL ACCUMULATED INVESTMENT"), money(total), per(total, placed), money(per_bird))

        # the cost of the birds lost, carried by the survivors (none when no bird was lost)
        spread = Markup()
        if placed and 0 < birds < placed:
            spread = Markup("<p class='mb-0 text-muted'>%s</p>") % _(
                "Mortality spread: the %(lost)s birds lost add %(spread)s to the cost of each live bird.",
                lost=number(placed - birds), spread=money(per_bird - total / placed))

        if self.laying_start_date:
            status = _("Investment locked at the start of the Laying Phase on %(date)s, over %(birds)s birds.",
                       date=format_date(self.env, self.laying_start_date), birds=number(birds))
        else:
            status = _("Remaining Pre-Laying Budget: %(remaining)s / bird.",
                       remaining=money(cfg.pre_laying_target_cost - per_bird))
        header = _("Arrival Date: %(arrival)s · Age: %(age)s weeks · Placed: %(placed)s · Birds: %(birds)s",
                   arrival=format_date(self.env, self.farm_arrival_date) if self.farm_arrival_date else "—",
                   age=f"{self.flock_age_weeks:.1f}", placed=number(self.initial_bird_count), birds=number(birds))
        benchmark = _("Target Pre-Laying Investment Benchmark: %(low)s – %(high)s / bird",
                      low=money(cfg.pre_laying_target_cost), high=money(cfg.pre_laying_target_cost_max))
        return Markup(
            "<p class='mb-2 text-muted'>%(header)s</p>"
            "<table class='table table-sm o_farm_investment'><thead><tr>"
            "<th>%(c1)s</th><th class='text-end'>%(c2)s</th><th class='text-end'>%(c3)s</th>"
            "<th class='text-end'>%(c4)s</th><th class='text-end'>%(c5)s</th></tr></thead>"
            "<tbody>%(body)s</tbody></table>%(spread)s"
            "<p class='mb-0'>%(benchmark)s</p><p class='mb-0 fw-bold'>%(status)s</p>") % {
            'header': header, 'body': body, 'spread': spread, 'benchmark': benchmark, 'status': status,
            'c1': _("Cost Component"), 'c2': _("Quantity Consumed"), 'c3': _("Total Expenditure"),
            'c4': _("Cost / Placed Bird (%s)", number(placed)), 'c5': _("Cost / Live Bird (%s)", number(birds)),
        }

    def action_view_investment_report(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('top_farm_dashboard.action_farm_flock_investment_report')
        action['domain'] = [('flock_lot_id', '=', self.id)]
        action['context'] = {'search_default_group_component': 1}
        action['display_name'] = _("Pre-Laying Investment of %s", self.name)
        return action
