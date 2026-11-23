import { Component, onWillStart, proxy, signal, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useChart } from "@web/core/utils/chart_hook";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { _t } from "@web/core/l10n/translation";

const GRADE_COLORS = { jumbo: "#875a7b", large: "#00a09d", medium: "#f0ad4e", damage: "#d9534f" };
const GRADES = ["jumbo", "large", "medium", "damage"];
// feed products in their order of first use: booster, starter, finisher, ...
const FEED_COLORS = ["#e9b949", "#e07b39", "#3a9d8f", "#5b6abf", "#9b59b6", "#7f8c8d"];
const GRID = "rgba(128,128,128,0.25)";
const STANDARD = "rgba(128,128,128,0.9)";

function isoDate(date) {
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 10);
}

/** Shared behaviour of the layer and broiler dashboards: period and flock filters, card helpers. */
class FarmDashboardBase extends Component {
    props = useProps(standardActionServiceProps);
    defaultDays = 1;

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        const today = new Date();
        const from = new Date(today.getTime() - (this.defaultDays - 1) * 86400000);
        // t-model binds to signals in Owl 3
        this.from = signal(isoDate(from));
        this.to = signal(isoDate(today));
        this.flock = signal("");
        this.state = proxy({ data: null });
        onWillStart(() => this.load());
    }

    get flockId() {
        return this.flock() ? parseInt(this.flock()) : false;
    }

    async onFilterChange() {
        await this.load();
    }

    get textColor() {
        return getComputedStyle(document.body).color;
    }

    fmt(n, digits = 0) {
        return new Intl.NumberFormat(undefined, {
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
        }).format(n || 0);
    }

    statusClass(ok) {
        return ok === null || ok === undefined ? "" : ok ? "o_farm_ok" : "o_farm_bad";
    }

    get periodDomain() {
        return [
            ["date", ">=", this.from()],
            ["date", "<=", this.to()],
        ];
    }

    openList(name, resModel, domain, context = {}, views = [[false, "list"], [false, "form"]]) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: resModel,
            views,
            domain,
            context,
        });
    }
}

/** Layer Performance Dashboard: hen-day and hen-housed production, egg grade mix, laying feed per hen. */
export class LayerDashboard extends FarmDashboardBase {
    static template = "top_farm_dashboard.LayerDashboard";

    setup() {
        super.setup();
        this.days = signal("7");
        // Odoo's own Chart.js hook: loads the library, draws after mount and after every patch
        this.trend = useChart(() => this.trendConfig());
        this.mix = useChart(() => this.mixConfig());
    }

    async load() {
        this.state.data = await this.orm.call("farm.dashboard", "get_layer_kpis", [], {
            date_from: this.from(),
            date_to: this.to(),
            flock_id: this.flockId,
            trend_days: parseInt(this.days()),
        });
    }

    trendConfig() {
        const data = this.state.data;
        const text = this.textColor;
        const label = (g) => data.grade_mix.find((m) => m.grade === g).label;
        return {
            type: "bar",
            data: {
                labels: data.trend.map((t) => t.date.slice(5)),
                datasets: [
                    {
                        type: "line",
                        label: _t("Hen-Day %"),
                        data: data.trend.map((t) => t.hen_day),
                        borderColor: text,
                        backgroundColor: text,
                        yAxisID: "y1",
                        spanGaps: true,
                        pointRadius: 3,
                        order: 0,
                    },
                    {
                        type: "line",
                        label: _t("Hen-Day target"),
                        data: data.trend.map(() => data.target_hen_day),
                        borderColor: STANDARD,
                        borderDash: [6, 4],
                        pointRadius: 0,
                        yAxisID: "y1",
                        order: 1,
                    },
                    ...GRADES.map((g) => ({
                        label: label(g),
                        data: data.trend.map((t) => t[g]),
                        backgroundColor: GRADE_COLORS[g],
                        stack: "eggs",
                        order: 2,
                    })),
                ],
            },
            options: {
                maintainAspectRatio: false,
                animation: false,
                plugins: { legend: { labels: { color: text } } },
                scales: {
                    x: { stacked: true, ticks: { color: text }, grid: { color: GRID } },
                    y: {
                        stacked: true,
                        beginAtZero: true,
                        ticks: { color: text },
                        grid: { color: GRID },
                        title: { display: true, text: _t("Eggs"), color: text },
                    },
                    y1: {
                        position: "right",
                        beginAtZero: true,
                        suggestedMax: 100,
                        ticks: { color: text },
                        grid: { drawOnChartArea: false },
                        title: { display: true, text: _t("Hen-Day %"), color: text },
                    },
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

    get flockDomain() {
        return this.flockId ? [["flock_lot_id", "=", this.flockId]] : [];
    }

    openCollections() {
        this.openList(_t("Egg Collections"), "farm.egg.collection", [
            ["state", "=", "done"],
            ["flock_lot_id.flock_type", "=", "layer"],
            ...this.periodDomain,
            ...this.flockDomain,
        ]);
    }

    openDailyReport() {
        this.openList(
            _t("Daily Egg Production & Hen-Day %"),
            "farm.egg.daily.report",
            [...this.periodDomain, ...this.flockDomain],
            { search_default_group_day: 1, search_default_group_flock: 1 },
            [[false, "list"], [false, "pivot"], [false, "graph"]]
        );
    }

    openMortality() {
        this.openList(_t("Mortality Records"), "farm.mortality.log", [
            // the card counts scrapped logs only: the list must show exactly those
            ["state", "=", "done"],
            ["lot_id.flock_type", "=", "layer"],
            ...this.periodDomain,
            ...(this.flockId ? [["lot_id", "=", this.flockId]] : []),
        ]);
    }

    openPopulation() {
        // the live hens behind the card: the active layer flocks in their brooding nurseries and cages
        const domain = [
            ["product_id.is_farm_bird", "=", true],
            ["location_id.usage", "=", "internal"],
            ["lot_id.is_flock_batch", "=", true],
            ["lot_id.flock_type", "=", "layer"],
            ["lot_id.flock_stage", "not in", ["spent", "closed"]],
            ["quantity", ">", 0],
        ];
        if (this.flockId) {
            domain.push(["lot_id", "=", this.flockId]);
        }
        this.openList(
            _t("Live Hens"),
            "stock.quant",
            domain,
            { create: false, edit: false, delete: false, group_by: ["lot_id", "location_id"] },
            [[false, "list"]]
        );
    }
}

/** Broiler Performance Dashboard: batch FCR, live biomass, cumulative mortality, daily feed intake curve. */
export class BroilerDashboard extends FarmDashboardBase {
    static template = "top_farm_dashboard.BroilerDashboard";
    // a broiler batch lives 35 to 42 days: show its whole cycle by default
    defaultDays = 42;

    setup() {
        super.setup();
        this.feed = useChart(() => this.feedConfig());
    }

    async load() {
        this.state.data = await this.orm.call("farm.dashboard", "get_broiler_kpis", [], {
            date_from: this.from(),
            date_to: this.to(),
            flock_id: this.flockId,
        });
    }

    get batchIds() {
        return this.state.data.rows.map((r) => r.id);
    }

    feedConfig() {
        const data = this.state.data;
        const text = this.textColor;
        const days = data.feed_days;
        const datasets = [
            {
                type: "line",
                label: _t("Intake (g/bird/day)"),
                data: days.map((d) => d.intake_g),
                borderColor: text,
                backgroundColor: text,
                yAxisID: "y1",
                spanGaps: true,
                pointRadius: 2,
                order: 0,
            },
        ];
        datasets.push(
            ...data.feed_products.map((p, i) => ({
                label: p.name,
                data: days.map((d) => d.kg[p.id] || 0),
                backgroundColor: FEED_COLORS[i % FEED_COLORS.length],
                stack: "feed",
                order: 2,
            }))
        );
        return {
            type: "bar",
            data: { labels: days.map((d) => d.date.slice(5)), datasets },
            options: {
                maintainAspectRatio: false,
                animation: false,
                plugins: { legend: { labels: { color: text } } },
                scales: {
                    x: { stacked: true, ticks: { color: text }, grid: { color: GRID } },
                    y: {
                        stacked: true,
                        beginAtZero: true,
                        ticks: { color: text },
                        grid: { color: GRID },
                        title: { display: true, text: _t("Feed (kg)"), color: text },
                    },
                    y1: {
                        position: "right",
                        beginAtZero: true,
                        ticks: { color: text },
                        grid: { drawOnChartArea: false },
                        title: { display: true, text: _t("g / bird / day"), color: text },
                    },
                },
            },
        };
    }

    openLiveBirds() {
        this.openList(
            _t("Live Broilers"),
            "stock.quant",
            [
                ["location_id.usage", "=", "internal"],
                ["lot_id", "in", this.batchIds],
                ["quantity", ">", 0],
            ],
            { create: false, edit: false, delete: false, group_by: ["lot_id", "location_id"] },
            [[false, "list"]]
        );
    }

    openBatches() {
        this.openList(_t("Broiler Batches"), "stock.lot", [["id", "in", this.batchIds]]);
    }

    openBatch(batchId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "stock.lot",
            res_id: batchId,
            views: [[false, "form"]],
        });
    }

    openFeedLogs() {
        this.openList(_t("Broiler Feed Logs"), "farm.feed.log", [
            ["flock_lot_id", "in", this.batchIds],
            ["state", "=", "reconciled"],
            ...this.periodDomain,
        ]);
    }

    openMortality() {
        this.openList(_t("Broiler Mortality"), "farm.mortality.log", [
            ["state", "=", "done"],
            ["lot_id", "in", this.batchIds],
        ]);
    }
}

registry.category("actions").add("top_farm_dashboard.layer_dashboard", LayerDashboard);
registry.category("actions").add("top_farm_dashboard.broiler_dashboard", BroilerDashboard);
// the former mixed dashboard (bookmarks, home actions): the layer dashboard
registry.category("actions").add("top_farm_dashboard.main", LayerDashboard);
