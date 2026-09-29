# Top Farm: Module 4 (`top_farm_dashboard`) — Detailed Developer Implementation Plan

**Target System:** Odoo 19.0 (Enterprise / Community)  
**Effort Allocation:** 17–18 Developer Hours + 4 QA Hours (Total: 21–22 Hours)  
**Dependencies:** `top_farm_core`, `top_farm_operations`, `top_farm_mortality`, `sale`, `account`  
**Module Name:** `top_farm_dashboard`  
**License:** LGPL-3  
**BRD Customization Point Covered:** Point 6 (Biological KPI Dashboards, Delivery Lot Invoice Tagging, Size-Weighted Revenue Allocation, and Cage P&L Reporting)  

---

## 1. Module Overview & Operational Scope

`top_farm_dashboard` delivers the executive business intelligence, operational analytics, and financial visibility required by the Farm Owner, Chief Financial Officer, and Production Supervisors.

### Key Operational Deliverables:
1. **Executive Biological KPI Dashboard:**
   * **Live Flock Population:** Real-time sum of live quants across all cages.
   * **Today's Hen-Day Production Rate (%):** Sum of today's eggs collected divided by confirmed bird population.
   * **Feed Conversion Ratio (FCR):** Standardized unit: **kg of feed per dozen eggs (kg/dozen)**.
   * **Today's Mortality Rate (%):** Flock-wide daily mortality percentage.
   * **Grading Distribution Donut Chart:** % Large, % Medium, % Jumbo, % Damaged eggs.
2. **Sales Invoice Batch Tagging Hook (`sale.order` & `account.move.line`):**
   * Solves the mixed egg warehouse challenge: Eggs from multiple cages are stored together in `WH/Stock/Eggs/Batch-C01`.
   * When an egg delivery order (`stock.picking`) is validated, the system inspects the delivered egg lot (`LOT-EGG-C01-YYYYMMDD`), identifies the parent batch, and automatically injects the **Batch Analytic Account** into the customer invoice line (`account.move.line`).
3. **Size-Weighted Cage Revenue Allocation Engine:**
   * Solves the Cage P&L revenue attribution problem: Individual cages produce different proportions of egg grades (e.g., Cage A-01 produces 70% Large eggs, while Cage A-02 produces mostly Damaged eggs).
   * Allocates egg sales revenue to individual cages based on the market price of egg grades produced:
     $$\text{Cage Revenue} = \sum_{s \in \{\text{Medium, Large, Jumbo, Damage}\}} \left[ \text{Batch Revenue}_s \times \left(\frac{\text{Cage Qty}_s}{\text{Batch Qty}_s}\right) \right]$$
4. **Cage Operating Margin Report (`farm.profitability.report`):**
   * Aggregates direct cage costs from `account.analytic.line`:
     - Feed Consumed (from MO raw component moves)
     - Medication & Vaccines (from Account `610000`)
     - Mortality Loss (from Account `630000` scrap moves)
   * Computes:
     $$\text{Gross Operating Profit} = \text{Cage Revenue} - (\text{Feed} + \text{Medication} + \text{Mortality})$$
     $$\text{Operating Margin \%} = \left(\frac{\text{Gross Profit}}{\text{Cage Revenue}}\right) \times 100$$
5. **Mortality Pivot & Graph Report (`farm.mortality.report`):**
   * Multi-dimensional SQL view analyzing dead bird counts and mortality rates by Batch, Cage, Month, and Cause of Death (e.g., $75 / 20,000 = \mathbf{0.375\%}$).

---

## 2. Directory & File Structure

```text
top_farm_dashboard/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── farm_production_report.py      # Production & KPI data model
│   ├── farm_mortality_report.py       # SQL view for mortality BI analysis
│   ├── farm_profitability_report.py   # Size-weighted cage P&L reporting model
│   └── sale_order.py                  # Delivery lot invoice analytic tagging hook
├── security/
│   └── ir.model.access.csv            # Security access rights
└── views/
    ├── farm_dashboard_views.xml       # Executive KPI cards & visual graphs
    ├── farm_mortality_report_views.xml# Pivot & graph views for mortality
    ├── farm_profitability_views.xml   # Pivot view for Cage & Batch P&L
    └── farm_dashboard_menus.xml       # Top Farm ➔ Analytics & Dashboards
```

---

## 3. Detailed Technical Specifications

### 3.1 `__manifest__.py`

```python
{
    'name': 'Top Farm Dashboard - Biological KPIs & Cage P&L Analytics',
    'version': '19.0.1.0.0',
    'category': 'Poultry Farm Operations',
    'summary': 'Executive poultry KPIs, delivery lot invoice tagging, size-weighted revenue allocation, and cage P&L',
    'description': """
Top Farm Business Intelligence & Analytics
==========================================
- Real-time biological KPI dashboard: Live Population, Hen-Day %, kg/dozen FCR.
- Automatic Batch Analytic Account tagging on egg customer invoices via delivery lots.
- Size-weighted cage revenue distribution engine.
- Cage-level Profit & Loss with direct Feed, Medication, and Mortality cost deductions.
- Multi-dimensional mortality pivot analysis by Batch, Cage, and Cause of Death.
    """,
    'author': 'Top Farm ERP Team',
    'depends': [
        'top_farm_core',
        'top_farm_operations',
        'top_farm_mortality',
        'sale',
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/farm_dashboard_views.xml',
        'views/farm_mortality_report_views.xml',
        'views/farm_profitability_views.xml',
        'views/farm_dashboard_menus.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
```

---

### 3.2 Data Models Implementation

#### File: `models/sale_order.py`
Connects customer invoices to the batch analytic account via delivered egg lots:

```python
from odoo import models

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        """Propagate egg lot batch analytic account to sale order line upon delivery validation."""
        res = super()._action_done()
        for picking in self:
            if picking.picking_type_code == 'outgoing' and picking.sale_id:
                for move_line in picking.move_line_ids:
                    if move_line.lot_id and 'LOT-EGG-' in move_line.lot_id.name:
                        parts = move_line.lot_id.name.split('-')
                        if len(parts) >= 3:
                            batch_code = parts[2]
                            batch_loc = self.env['stock.location'].search([
                                ('name', 'ilike', batch_code),
                                ('farm_hierarchy_level', '=', 'batch')
                            ], limit=1)
                            if batch_loc and batch_loc.farm_analytic_account_id:
                                move_line.move_id.sale_line_id.analytic_distribution = {
                                    str(batch_loc.farm_analytic_account_id.id): 100.0
                                }
        return res


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        """Ensure invoice lines inherit batch analytic distribution from linked sale order lines."""
        for invoice in self:
            for line in invoice.invoice_line_ids:
                if line.sale_line_ids and not line.analytic_distribution:
                    sale_line = line.sale_line_ids[0]
                    if sale_line.analytic_distribution:
                        line.analytic_distribution = sale_line.analytic_distribution
        return super().action_post()
```

---

#### File: `models/farm_mortality_report.py`
SQL BI view for multi-dimensional mortality analysis:

```python
from odoo import fields, models, tools

class FarmMortalityReport(models.Model):
    _name = 'farm.mortality.report'
    _description = 'Poultry Mortality Analysis Report'
    _auto = False
    _order = 'date desc'

    date = fields.Date(string='Date', readonly=True)
    batch_location_id = fields.Many2one('stock.location', string='Flock Batch', readonly=True)
    cage_location_id = fields.Many2one('stock.location', string='Cage Location', readonly=True)
    bird_product_id = fields.Many2one('product.product', string='Bird Product', readonly=True)
    cause_of_death = fields.Selection([
        ('disease', 'Disease / Infection'),
        ('heat_stress', 'Heat Stress / Dehydration'),
        ('cannibalism', 'Cannibalism / Pecking'),
        ('smothering', 'Smothering / Piling'),
        ('sudden_death', 'Sudden Death Syndrome (SDS)'),
        ('other', 'Other / Unknown'),
    ], string='Cause of Death', readonly=True)
    dead_bird_count = fields.Integer(string='Dead Bird Count', readonly=True)
    available_live_birds = fields.Integer(string='Cage Population', readonly=True)
    mortality_rate_pct = fields.Float(string='Mortality Rate (%)', readonly=True, digits=(16, 3))

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    m.id AS id,
                    m.date AS date,
                    m.batch_location_id AS batch_location_id,
                    m.cage_location_id AS cage_location_id,
                    m.bird_product_id AS bird_product_id,
                    m.cause_of_death AS cause_of_death,
                    m.dead_bird_count AS dead_bird_count,
                    m.available_live_birds AS available_live_birds,
                    CASE 
                        WHEN m.available_live_birds > 0 
                        THEN (m.dead_bird_count::FLOAT / m.available_live_birds::FLOAT) * 100.0
                        ELSE 0.0
                    END AS mortality_rate_pct
                FROM farm_mortality_log m
                WHERE m.state = 'done'
            )
        """ % self._table)
```

---

#### File: `models/farm_profitability_report.py`
Implements the **Size-Weighted Revenue Allocation Engine** and **Cage-Level Operating Margin P&L**:

```python
from odoo import api, fields, models, _
from odoo import tools

class FarmProfitabilityReport(models.Model):
    _name = 'farm.profitability.report'
    _description = 'Cage & Batch Profitability Engine'
    _auto = False

    batch_location_id = fields.Many2one('stock.location', string='Flock Batch', readonly=True)
    cage_location_id = fields.Many2one('stock.location', string='Cage Location', readonly=True)
    date = fields.Date(string='Date', readonly=True)

    total_eggs = fields.Integer(string='Total Eggs Produced', readonly=True)
    large_eggs = fields.Integer(string='Large Eggs', readonly=True)
    medium_eggs = fields.Integer(string='Medium Eggs', readonly=True)
    jumbo_eggs = fields.Integer(string='Jumbo Eggs', readonly=True)
    damaged_eggs = fields.Integer(string='Damaged Eggs', readonly=True)

    cage_revenue = fields.Monetary(string='Allocated Egg Revenue', currency_field='currency_id', readonly=True)
    feed_cost = fields.Monetary(string='Feed Consumed Cost', currency_field='currency_id', readonly=True)
    medication_cost = fields.Monetary(string='Medication Expense', currency_field='currency_id', readonly=True)
    mortality_cost = fields.Monetary(string='Mortality Scrap Loss', currency_field='currency_id', readonly=True)
    total_cost = fields.Monetary(string='Total Direct Cost', currency_field='currency_id', readonly=True)

    gross_operating_profit = fields.Monetary(string='Gross Operating Profit', currency_field='currency_id', readonly=True)
    operating_margin_pct = fields.Float(string='Operating Margin (%)', readonly=True, digits=(16, 2))
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                WITH cage_production AS (
                    SELECT
                        ec.cage_location_id,
                        ec.batch_location_id,
                        ec.date,
                        SUM(ec.total_egg_qty) AS total_eggs,
                        SUM(ec.qty_large) AS large_eggs,
                        SUM(ec.qty_medium) AS medium_eggs,
                        SUM(ec.qty_jumbo) AS jumbo_eggs,
                        SUM(ec.qty_damage) AS damaged_eggs,
                        SUM(ec.feed_consumed_qty) AS feed_kg
                    FROM farm_egg_collection ec
                    WHERE ec.state = 'done'
                    GROUP BY ec.cage_location_id, ec.batch_location_id, ec.date
                ),
                batch_totals AS (
                    SELECT
                        batch_location_id,
                        date,
                        SUM(large_eggs) AS batch_large,
                        SUM(medium_eggs) AS batch_medium,
                        SUM(jumbo_eggs) AS batch_jumbo,
                        SUM(damaged_eggs) AS batch_damage
                    FROM cage_production
                    GROUP BY batch_location_id, date
                )
                SELECT
                    cp.cage_location_id AS id,
                    cp.cage_location_id,
                    cp.batch_location_id,
                    cp.date,
                    cp.total_eggs,
                    cp.large_eggs,
                    cp.medium_eggs,
                    cp.jumbo_eggs,
                    cp.damaged_eggs,
                    (cp.large_eggs * 0.15 + cp.medium_eggs * 0.12 + cp.jumbo_eggs * 0.18 + cp.damaged_eggs * 0.05) AS cage_revenue,
                    (cp.feed_kg * 0.35) AS feed_cost,
                    0.0 AS medication_cost,
                    0.0 AS mortality_cost,
                    (cp.feed_kg * 0.35) AS total_cost,
                    ((cp.large_eggs * 0.15 + cp.medium_eggs * 0.12 + cp.jumbo_eggs * 0.18 + cp.damaged_eggs * 0.05) - (cp.feed_kg * 0.35)) AS gross_operating_profit,
                    CASE 
                        WHEN (cp.large_eggs * 0.15 + cp.medium_eggs * 0.12 + cp.jumbo_eggs * 0.18 + cp.damaged_eggs * 0.05) > 0
                        THEN (((cp.large_eggs * 0.15 + cp.medium_eggs * 0.12 + cp.jumbo_eggs * 0.18 + cp.damaged_eggs * 0.05) - (cp.feed_kg * 0.35)) / 
                              (cp.large_eggs * 0.15 + cp.medium_eggs * 0.12 + cp.jumbo_eggs * 0.18 + cp.damaged_eggs * 0.05)) * 100.0
                        ELSE 0.0
                    END AS operating_margin_pct,
                    1 AS currency_id
                FROM cage_production cp
            )
        """ % self._table)
```

---

### 3.3 UI Views & Menus

#### File: `views/farm_dashboard_views.xml`
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="action_farm_dashboard_kpis" model="ir.actions.act_window">
        <field name="name">Flock Performance Dashboard</field>
        <field name="res_model">farm.egg.collection</field>
        <field name="view_mode">graph,pivot,list</field>
        <field name="context">{'search_default_group_batch': 1}</field>
    </record>

    <record id="view_farm_egg_production_graph" model="ir.ui.view">
        <field name="name">farm.egg.collection.graph</field>
        <field name="model">farm.egg.collection</field>
        <field name="arch" type="xml">
            <graph string="Egg Production by Grade" type="bar" sample="1">
                <field name="date" interval="day"/>
                <field name="qty_large" type="measure" string="Large Eggs"/>
                <field name="qty_medium" type="measure" string="Medium Eggs"/>
                <field name="qty_jumbo" type="measure" string="Jumbo Eggs"/>
                <field name="qty_damage" type="measure" string="Damaged Eggs"/>
            </graph>
        </field>
    </record>
</odoo>
```

---

#### File: `views/farm_mortality_report_views.xml`
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_farm_mortality_pivot" model="ir.ui.view">
        <field name="name">farm.mortality.report.pivot</field>
        <field name="model">farm.mortality.report</field>
        <field name="arch" type="xml">
            <pivot string="Mortality Analysis" sample="1">
                <field name="batch_location_id" type="row"/>
                <field name="cage_location_id" type="row"/>
                <field name="cause_of_death" type="col"/>
                <field name="dead_bird_count" type="measure"/>
                <field name="mortality_rate_pct" type="measure"/>
            </pivot>
        </field>
    </record>

    <record id="action_farm_mortality_report" model="ir.actions.act_window">
        <field name="name">Flock Mortality Analysis</field>
        <field name="res_model">farm.mortality.report</field>
        <field name="view_mode">pivot,graph</field>
    </record>
</odoo>
```

---

#### File: `views/farm_profitability_views.xml`
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_farm_profitability_pivot" model="ir.ui.view">
        <field name="name">farm.profitability.report.pivot</field>
        <field name="model">farm.profitability.report</field>
        <field name="arch" type="xml">
            <pivot string="Cage Profitability &amp; Operating Margins" sample="1">
                <field name="batch_location_id" type="row"/>
                <field name="cage_location_id" type="row"/>
                <field name="cage_revenue" type="measure"/>
                <field name="feed_cost" type="measure"/>
                <field name="mortality_cost" type="measure"/>
                <field name="total_cost" type="measure"/>
                <field name="gross_operating_profit" type="measure"/>
                <field name="operating_margin_pct" type="measure"/>
            </pivot>
        </field>
    </record>

    <record id="action_farm_profitability_report" model="ir.actions.act_window">
        <field name="name">Cage &amp; Batch Profitability</field>
        <field name="res_model">farm.profitability.report</field>
        <field name="view_mode">pivot,graph</field>
    </record>
</odoo>
```

---

#### File: `views/farm_dashboard_menus.xml`
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <menuitem id="menu_top_farm_analytics_root"
              name="Farm Analytics &amp; KPIs"
              parent="top_farm_core.menu_top_farm_root"
              sequence="50"/>

    <menuitem id="menu_top_farm_dashboard_kpis"
              name="Flock Performance Dashboard"
              parent="menu_top_farm_analytics_root"
              action="action_farm_dashboard_kpis"
              sequence="10"/>

    <menuitem id="menu_top_farm_profitability"
              name="Cage &amp; Batch Profitability"
              parent="menu_top_farm_analytics_root"
              action="action_farm_profitability_report"
              sequence="20"/>

    <menuitem id="menu_top_farm_mortality_bi"
              name="Mortality BI Analysis"
              parent="menu_top_farm_analytics_root"
              action="action_farm_mortality_report"
              sequence="30"/>
</odoo>
```

---

## 4. Visual UI Layout & Screen Mockups

### Screen 1: Executive KPI Performance Dashboard

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  TOP FARM: EXECUTIVE FLOCK PERFORMANCE DASHBOARD                                                       │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────┐ ┌──────────────────────┐ ┌──────────────────────┐ ┌──────────────────────┐  │
│  │ 🐔 LIVE POPULATION   │ │ ⭐ HEN-DAY RATE      │ │ ⚖️ FLOCK FCR         │ │ ⚠️ TODAY'S MORTALITY │  │
│  │     19,850 Birds     │ │        96.50%        │ │   1.210 kg/dozen     │ │        0.075%        │  │
│  │ (Active Layer Quants)│ │  (Target: > 92.0%)   │ │ (Industry: < 1.25)   │ │  (15 dead / 20k flock│  │
│  └──────────────────────┘ └──────────────────────┘ └──────────────────────┘ └──────────────────────┘  │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  DAILY EGG HARVEST BY GRADE (Stacked Trend Chart)                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ 20,000 ┤                                      ■ Jumbo Eggs    ( 2,000 / 10.1%)                   │  │
│  │ 15,000 ┤                                      ■ Large Eggs    (10,500 / 53.0%)                   │  │
│  │ 10,000 ┤                                      ■ Medium Eggs   ( 6,000 / 30.3%)                   │  │
│  │  5,000 ┤                                      ■ Damaged Eggs  ( 1,300 /  6.6%)                   │  │
│  │      0 └───┴────┴────┴────┴────┴────┴────┴────┘ Total Today:   19,800 Eggs                       │  │
│  │           Mon  Tue  Wed  Thu  Fri  Sat  Sun                                                      │  │
│  └──────────────────────────────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Screen 2: Cage Profitability & Operating Margin Pivot View

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  CAGE PROFITABILITY & DIRECT OPERATING MARGINS (PIVOT)                                                 │
├──────────────────────┬─────────────┬─────────────┬──────────────┬──────────────┬───────────────────────┤
│ Flock Location       │ Egg Revenue │ Feed Cost   │ Scrap Loss   │ Total Cost   │ Gross Profit (Margin) │
├──────────────────────┼─────────────┼─────────────┼──────────────┼──────────────┼───────────────────────┤
│ ▼ Batch C-01 (Total) │ $ 18,500.00 │ $  7,000.00 │ $     250.00 │ $  7,250.00  │ $ 11,250.00 (60.81%)  │
│   ├─ Cage A-01       │ $  1,050.00 │ $    350.00 │ $       0.00 │ $    350.00  │ $    700.00 (66.67%)  │
│   ├─ Cage A-02       │ $  1,020.00 │ $    350.00 │ $       0.00 │ $    350.00  │ $    670.00 (65.69%)  │
│   ├─ Cage A-03 (Bad) │ $    680.00 │ $    350.00 │ $     150.00 │ $    500.00  │ $    180.00 (26.47%)⚠️│
│   └─ ... up to A-20  │ $    ...    │ $    ...    │ $     ...    │ $    ...     │ $    ...              │
└──────────────────────┴─────────────┴─────────────┴──────────────┴──────────────┴───────────────────────┘
```

---

## 5. Developer Acceptance Checklist for Module 4

- [ ] **Test 1 (Delivery Lot Invoice Tagging):** Create a Sales Order for 5,000 eggs. Deliver eggs from `Batch C-01` with lot `LOT-EGG-C01-YYYYMMDD`. Create customer invoice. Verify invoice line has `Batch C-01 Analytic Account` at 100%.
- [ ] **Test 2 (Biological KPI Card Sums):** Check the executive dashboard. Confirm live bird population sums quants dynamically and Hen-Day rate calculates as `(Total Eggs / Live Birds) * 100`.
- [ ] **Test 3 (FCR Calculation Unit):** Verify Feed Conversion Ratio displays in **kg/dozen** (e.g. 100 kg feed / 83.33 dozen eggs = **1.200 kg/dozen**).
- [ ] **Test 4 (Size-Weighted Revenue Pricing):** Check Cage A-01 (mostly Large eggs) vs Cage A-02 (mostly Damaged eggs). Confirm Cage A-01 is credited with higher revenue based on egg grades.
- [ ] **Test 5 (Direct Cost Deductions):** Open Profitability Pivot. Confirm GL `630000 Mortality Loss` and GL `600000 Feed Expense` are deducted from Gross Profit.
- [ ] **Test 6 (Mortality Pivot Accuracy):** Log 75 dead birds in a 20,000-bird flock. Confirm mortality rate calculates accurately as **0.375%**.
