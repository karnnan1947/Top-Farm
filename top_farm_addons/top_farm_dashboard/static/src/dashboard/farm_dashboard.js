import { Component, onWillStart, proxy, signal, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useChart } from "@web/core/utils/chart_hook";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { _t } from "@web/core/l10n/translation";

const GRADE_COLORS = { jumbo: "#875a7b", large: "#00a09d", medium: "#f0ad4e", damage: "#d9534f" };
const GRADES = ["jumbo", "large", "medium", "damage"];

export class FarmDashboard extends Component {
    static template = "top_farm_dashboard.Dashboard";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        const today = new Date().toISOString().slice(0, 10);
        // t-model binds to signals in Owl 3
        this.from = signal(today);
        this.to = signal(today);
        this.batch = signal("");
        this.days = signal("7");
        this.state = proxy({ data: null });
        // Odoo's own Chart.js hook: loads the library, draws after mount and after every patch
        this.trend = useChart(() => this.trendConfig());
        this.mix = useChart(() => this.mixConfig());
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("farm.dashboard", "get_kpis", [], {
            date_from: this.from(),
            date_to: this.to(),
            batch_id: this.batch() ? parseInt(this.batch()) : false,
            trend_days: parseInt(this.days()),
        });
    }

    get textColor() {
        return getComputedStyle(document.body).color;
    }

    trendConfig() {
        const data = this.state.data;
        const text = this.textColor;
        const grid = "rgba(128,128,128,0.25)";
        const label = (g) => data.grade_mix.find((m) => m.grade === g).label;
        return {
            type: "bar",
            data: {
                labels: data.trend.map((t) => t.date.slice(5)),
                datasets: GRADES.map((g) => ({
                    label: label(g),
                    data: data.trend.map((t) => t[g]),
                    backgroundColor: GRADE_COLORS[g],
                })),
            },
            options: {
                maintainAspectRatio: false,
                animation: false,
                plugins: { legend: { labels: { color: text } } },
                scales: {
                    x: { stacked: true, ticks: { color: text }, grid: { color: grid } },
                    y: { stacked: true, ticks: { color: text }, grid: { color: grid }, beginAtZero: true },
                },
            },
        };
    }

    mixConfig() {
        const data = this.state.data;
        return {
            type: "doughnut",
            data: {
                labels: data.grade_mix.map((m) => `${m.label} (${m.pct}%)`),
                datasets: [
                    {
                        data: data.grade_mix.map((m) => m.qty),
                        backgroundColor: GRADES.map((g) => GRADE_COLORS[g]),
                        borderWidth: 0,
                    },
                ],
            },
            options: {
                maintainAspectRatio: false,
                animation: false,
                plugins: { legend: { position: "right", labels: { color: this.textColor } } },
            },
        };
    }

    async onFilterChange() {
        await this.load();
    }

    fmt(n) {
        return new Intl.NumberFormat().format(n);
    }

    statusClass(ok) {
        return ok === null || ok === undefined ? "" : ok ? "o_farm_ok" : "o_farm_bad";
    }

    get batchDomain() {
        return this.batch() ? [["batch_location_id", "=", parseInt(this.batch())]] : [];
    }

    openCollections() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Egg Collections"),
            res_model: "farm.egg.collection",
            views: [[false, "list"], [false, "form"]],
            domain: [
                ["state", "=", "done"],
                ["date", ">=", this.from()],
                ["date", "<=", this.to()],
                ...this.batchDomain,
            ],
        });
    }

    openMortality() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Mortality Records"),
            res_model: "farm.mortality.log",
            views: [[false, "list"], [false, "form"]],
            domain: [
                // the card counts scrapped logs only: the list must show exactly those
                ["state", "=", "done"],
                ["date", ">=", this.from()],
                ["date", "<=", this.to()],
                ...this.batchDomain,
            ],
        });
    }

    openPopulation() {
        // the live birds behind the card: bird stock in the cages, of the selected batch
        const domain = [
            ["product_id.is_farm_bird", "=", true],
            ["location_id.farm_hierarchy_level", "=", "cage"],
            ["quantity", ">", 0],
        ];
        if (this.batch()) {
            domain.push(["location_id.parent_batch_location_id", "=", parseInt(this.batch())]);
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Live Birds"),
            res_model: "stock.quant",
            views: [[false, "list"]],
            domain,
            context: { create: false, edit: false, delete: false, group_by: ["location_id"] },
        });
    }
}

registry.category("actions").add("top_farm_dashboard.main", FarmDashboard);
