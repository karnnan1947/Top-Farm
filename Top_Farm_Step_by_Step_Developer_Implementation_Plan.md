# Top Farm: Step-by-Step Developer Implementation Plan

**Granular Technical Build Specifications for Odoo 19 Development**  
*Document Version:* 1.0 (Developer Blueprint)  
*Target System:* Odoo 19.0 (Enterprise / Community)  
*Total Effort Target:* 120–130 Hours (91–98 Dev Hours + 29–32 QA/UAT/Deployment)

---

## Development Sequence Overview

The modules must be developed strictly in sequential order to respect data dependencies:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Phase 1: Module 1 — top_farm_core (11–12 hrs)                              │
│  • Location Hierarchy (Farm/Batch/Cage) & Auto-Parent Detection             │
│  • Single stock.move._get_analytic_distribution() Hook                      │
│  • Live Bird Counter from stock.quant & Batch Lot Preservation              │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Phase 2: Module 2 — top_farm_operations (37–40 hrs)                        │
│  • Part A: Daily Feed & Medication Log + Direct Pre-Laying Expense (14–15h) │
│  • Part B: Daily Graded Egg Collection Form (12–13h)                        │
│  • Part C: Proportional MO Auto-Split Engine & Nightly Cron Fallback (25–27h)│
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Phase 3: Module 3 — top_farm_mortality (12–13 hrs)                         │
│  • Bird Mortality Logging with Live Stock Guards                            │
│  • Cumulative Daily Cage Threshold Check (> 2.0%)                            │
│  • Farm Manager Approval Workflow & Automated stock.scrap Hook              │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Phase 4: Module 4 — top_farm_dashboard (17–18 hrs)                         │
│  • Real-Time Biological KPIs (Hen-Day Snapshot %, kg/dozen FCR, Intake)    │
│  • Mortality Pivot Analysis by Batch, Cage & Cause of Death                 │
│  • Size-Weighted Revenue Distribution & Cage P&L Operating Margin           │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Phase 5: Master Configuration, Testing & Handover (29–32 hrs)              │
│  • Perpetual Valuation & Location Valuation Account Setup                   │
│  • Full End-to-End Cycle QA Testing & User Acceptance Testing (UAT)         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Phase 1: Module 1 — `top_farm_core`

* **Target Effort:** 11–12 Hours  
* **Dependencies:** `base`, `stock`, `stock_account`, `analytic`  
* **Folder Name:** `top_farm_core`

### 1.1 Directory Structure to Build
```text
top_farm_core/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── stock_location.py
│   └── stock_move.py
├── security/
│   ├── farm_security.xml
│   └── ir.model.access.csv
└── views/
    ├── stock_location_views.xml
    └── farm_menus.xml
```

### 1.2 Step-by-Step Implementation Steps

#### Step 1: Manifest & Security Groups
* In `security/farm_security.xml`, create:
  * Category: `module_category_farm_operations` ("Poultry Farm Management")
  * Group: `group_farm_user` ("Farm Operator / User", inherits `stock.group_stock_user`)
  * Group: `group_farm_manager` ("Farm Manager / Supervisor", inherits `group_farm_user`, `stock.group_stock_manager`)

#### Step 2: Model Extensions in `models/stock_location.py`
* Inherit `stock.location` and add:
  * `farm_hierarchy_level`: `fields.Selection([('farm', 'Farm Facility'), ('batch', 'Batch / Flock'), ('cage', 'Cage Sublocation')], string='Farm Hierarchy Level', index=True)`
  * `parent_batch_location_id`: `fields.Many2one('stock.location', string='Parent Batch Location', compute='_compute_parent_batch_location', store=True, domain="[('farm_hierarchy_level', '=', 'batch')]")`
  * `batch_stage`: `fields.Selection([('pre_laying', 'Pre-Laying (Weeks 1–18)'), ('laying', 'Laying Phase (Weeks 19–72)'), ('spent', 'Spent Hen / Depleted')], string='Flock Lifecycle Stage', default='pre_laying')`
  * `chick_arrival_date`: `fields.Date(string='Chick Arrival Date')`
  * `flock_age_weeks`: `fields.Float(string='Flock Age (Weeks)', compute='_compute_flock_age', digits=(16, 1))`
  * `farm_analytic_account_id`: `fields.Many2one('account.analytic.account', string='Analytic Account')`
  * `live_bird_count`: `fields.Integer(string='Live Birds', compute='_compute_live_bird_count')`
  * `sub_cage_count`: `fields.Integer(string='Cages Count', compute='_compute_sub_cage_count')`
* Implement logic:
  * `_compute_parent_batch_location`: Recursively traverse `location_id` until a location with `farm_hierarchy_level == 'batch'` is found.
  * `_compute_flock_age`: Compute `(today - chick_arrival_date).days / 7.0`.
  * `get_analytic_distribution_for_cage()`: Return `{str(self.farm_analytic_account_id.id): 100.0, str(self.parent_batch_location_id.farm_analytic_account_id.id): 100.0}`.
  * `get_live_bird_count()`: Query `stock.quant` for storable products where `location_id child_of self.id`.
  * `action_start_laying_phase()`: Button method restricted to `group_farm_manager` that updates `batch_stage = 'laying'`.
  * `@api.constrains('farm_hierarchy_level', 'parent_batch_location_id')`: Enforce that every cage has a parent batch location.

#### Step 3: Single Analytic Hook in `models/stock_move.py`
* Inherit `stock.move` and override `_get_analytic_distribution(self)`:
  1. Call `super()._get_analytic_distribution()`. If not empty, return it.
  2. Detect if `self.location_id` or `self.location_dest_id` is a cage location.
  3. If move is raw material for an MO (`self.raw_material_production_id.farm_collection_id`), get cage from `farm_collection_id.cage_location_id`.
  4. If cage identified, call `cage.get_analytic_distribution_for_cage()`.
  5. Return empty dict `{}` if no cage is involved.

#### Step 4: UI Views
* `stock_location_views.xml`:
  * Inherit `stock.view_location_form`: Add smart buttons for `Cages` and `Live Birds`. Add group "Poultry Farm Operations & Analytics" with hierarchy level, stage, age, and analytic account. Add button "Start Laying Phase" visible only when `batch_stage == 'pre_laying'`.
  * Dedicated List View: Show columns Name, Level, Parent Batch, Stage, Flock Age, Live Birds, and Analytic Account.
* `farm_menus.xml`:
  * Define Root menu **Top Farm** $\rightarrow$ **Farm Configuration** $\rightarrow$ **Farm, Batch & Cage Locations**.

### 1.3 Developer Acceptance Testing (Phase 1)
- [ ] Create `WH/Farm 1` (Level: Farm).
- [ ] Create `WH/Farm 1/Batch C-01` (Level: Batch, Arrival: 20 weeks ago). Confirm flock age computes as 20.0 weeks.
- [ ] Create `Cage A-01` under `Batch C-01` (Level: Cage). Confirm `Parent Batch` auto-populates as `Batch C-01`.
- [ ] Receive 20,000 chicks into `Batch C-01` with Lot `LOT-2026-01`. Transfer 1,000 birds to `Cage A-01`. Confirm `Cage A-01` shows **1,000 Live Birds**.
- [ ] Run test move from `Cage A-01` to `Virtual Locations/Scrapped`. Verify move calls `_get_analytic_distribution()` and creates `account.analytic.line` with Batch and Cage accounts.

---

# Phase 2: Module 2 — `top_farm_operations`

* **Target Effort:** 51–55 Hours Total  
  * Part A (Feed & Medication): 14–15 hrs  
  * Part B (Egg Harvest Screen): 12–13 hrs  
  * Part C (Proportional MO Engine & Nightly Cron): 25–27 hrs  
* **Dependencies:** `top_farm_core`, `mrp`, `mrp_account`, `mail`  
* **Folder Name:** `top_farm_operations`

### 2.1 Directory Structure to Build
```text
top_farm_operations/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── farm_feed_log.py
│   ├── farm_egg_collection.py
│   └── mrp_production.py
├── data/
│   ├── ir_sequence_data.xml
│   └── ir_cron_data.xml
├── security/
│   └── ir.model.access.csv
└── views/
    ├── farm_feed_log_views.xml
    ├── farm_egg_collection_views.xml
    └── farm_operations_menus.xml
```

### 2.2 Step-by-Step Implementation Steps

#### Step 1: Model `farm.feed.log` and `farm.feed.log.line`
* Model `farm.feed.log`:
  * `name`: Sequence `FEED/YYYY/XXXXX`
  * `date`: Date (Default: today)
  * `batch_location_id`: Many2one `stock.location` (domain `[('farm_hierarchy_level', '=', 'batch')]`)
  * `cage_location_id`: Many2one `stock.location` (domain `[('farm_hierarchy_level', '=', 'cage'), ('parent_batch_location_id', '=', batch_location_id)]`)
  * `feeding_phase`: Selection (`pre_laying`, `laying`), compute/default from `batch_location_id.batch_stage`
  * `feed_line_ids`: One2many `farm.feed.log.line`
  * `total_feed_qty`: Float, sum of line quantities
  * `state`: Selection (`draft`, `confirmed`, `reconciled`, `cancelled`)
  * `picking_id`: Many2one `stock.picking` (for pre-laying direct expense)
* Model `farm.feed.log.line`:
  * `product_id`: Feed or Medication/Vaccine product
  * `product_type`: Related to product category (`feed` vs `medication`)
  * `quantity`: Float
  * `uom_id`: Related UoM
  * `source_location_id`: Silo or Medicine cabinet location
* Business Logic:
  * `action_confirm()`:
    * If `feeding_phase == 'pre_laying'` OR line is `medication`:
      * Create and immediately validate a `stock.picking` from `source_location_id` to `Virtual Locations/Feed Consumption` (or `Medication Consumption`).
      * Odoo 19's `stock.move._get_analytic_distribution()` hook automatically creates the analytic lines!
    * If `feeding_phase == 'laying'` AND line is `feed`:
      * Mark state as `confirmed` (staged for Egg Collection MO consumption). **Do not move stock yet** to avoid double deduction.

#### Step 2: Model `farm.egg.collection`
* Fields:
  * `name`: Sequence `EGG/YYYY/XXXXX`
  * `date`: Date (Default: today)
  * `batch_location_id`: Batch location
  * `cage_location_id`: Cage sublocation
  * `destination_location_id`: Many2one `stock.location` (default: `WH/Stock/Eggs/Batch-C01`)
  * 4 Egg Product Fields: `product_medium_id`, `product_large_id`, `product_jumbo_id`, `product_damage_id`
  * 4 Quantity Fields: `qty_medium`, `qty_large`, `qty_jumbo`, `qty_damage`
  * `total_egg_qty`: Computed sum of 4 quantities
  * `confirmed_live_bird_count`: Stored Integer snapshot of live birds at collection time
  * `hen_day_rate`: Computed Float `(total_egg_qty / confirmed_live_bird_count) * 100`
  * `fcr`: Computed Float `(total_feed_qty / (total_egg_qty / 12.0))` (kg/dozen)
  * `feed_line_ids`: One2many `farm.egg.collection.feed`
  * `total_feed_qty`: Computed Float
  * `production_ids`: One2many `mrp.production`, 'farm_collection_id'
  * `state`: Selection (`draft`, `done`, `cancelled`)

#### Step 3: Proportional MO Auto-Split Engine
* Method `action_generate_split_manufacturing_orders()` on `farm.egg.collection`:
  1. Validate `total_egg_qty > 0`.
  2. Snapshot `confirmed_live_bird_count = cage_location_id.get_live_bird_count()`.
  3. Identify non-zero grades and sort descending by quantity.
  4. For each feed line consumed:
     * For each grade $i$: calculate allocated feed $= \text{round}(\text{total\_feed} \times (\text{qty}_i / \text{total\_eggs}), 4)$.
     * Reconcile rounding difference on largest grade so $\sum \text{Allocated Feed} \equiv \text{Total Feed Consumed}$ (zero residual).
  5. For each grade with $\text{qty} > 0$:
     * Generate `stock.lot` prefixed with batch code: `LOT-EGG-{batch_name}-{YYYYMMDD}`.
     * Create `mrp.production`:
       * `product_id`: egg grade product
       * `product_qty`: grade quantity
       * `lot_producing_id`: generated egg lot
       * `location_src_id`: feed silo location
       * `location_dest_id`: `destination_location_id`
       * `farm_collection_id`: `self.id`
       * `move_raw_ids`: raw stock moves with proportional feed quantities
     * Confirm and auto-produce the MO.
  6. Transition `state = 'done'`.
  7. Mark linked `farm.feed.log` state as `reconciled`.

#### Step 4: Nightly Cron for Unharvested Laying Feed
* In `data/ir_cron_data.xml`, schedule `cron_reconcile_unharvested_feed` to run daily at 23:59:
  * Find all `farm.feed.log` records in state `confirmed` where `date == today` and `feeding_phase == 'laying'`.
  * For any log with no linked egg collection (or collection with 0 eggs):
    * Create a direct consumption picking to `Virtual Locations/Feed Consumption` tagged as *Flock Maintenance / Zero-Egg Feed*.
    * Mark state as `reconciled`.

### 2.3 Developer Acceptance Testing (Phase 2)
- [ ] Log 50 kg feed for `Cage A-01` in pre-laying. Confirm picking moves stock from Silo to Feed Consumption and books GL 600000 with Batch & Cage analytic lines.
- [ ] Log 100 kg feed for `Cage A-01` in laying phase. Verify stock is NOT deducted yet.
- [ ] Open Egg Collection for `Cage A-01`: Enter 500 Large, 300 Medium, 100 Jumbo, 100 Damage. Pull feed (100 kg).
- [ ] Click "Generate Split MOs". Verify 4 MOs are created:
  - Large: 500 eggs, 50.0 kg feed.
  - Medium: 300 eggs, 30.0 kg feed.
  - Jumbo: 100 eggs, 10.0 kg feed.
  - Damage: 100 eggs, 10.0 kg feed.
- [ ] Verify sum of feed in all 4 MOs is exactly 100.00 kg.
- [ ] Verify egg lot `LOT-EGG-C01-YYYYMMDD` is generated and assigned.
- [ ] Test cron: Leave a laying feed log with no egg collection; run cron manually; verify feed is expensed to 600000.

---

# Phase 3: Module 3 — `top_farm_mortality`

* **Target Effort:** 12–13 Hours  
* **Dependencies:** `top_farm_core`, `stock_account`, `mail`  
* **Folder Name:** `top_farm_mortality`

### 3.1 Directory Structure to Build
```text
top_farm_mortality/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── farm_mortality_log.py
│   └── res_config_settings.py
├── data/
│   └── ir_sequence_data.xml
├── security/
│   └── ir.model.access.csv
└── views/
    ├── farm_mortality_log_views.xml
    └── res_config_settings_views.xml
```

### 3.2 Step-by-Step Implementation Steps

#### Step 1: Config Parameter in `models/res_config_settings.py`
* Add `daily_mortality_threshold_pct` to `res.company` / `res.config.settings` (Default: `2.0%`).

#### Step 2: Model `farm.mortality.log`
* Fields:
  * `name`: Sequence `MORT/YYYY/XXXXX`
  * `date`: Date (Default: today)
  * `batch_location_id`: Batch location
  * `cage_location_id`: Cage sublocation
  * `bird_product_id`: Storable layer bird product
  * `batch_lot_id`: Retained Hatchery Lot number
  * `available_live_birds`: Computed integer from `top_farm_core`
  * `dead_bird_count`: Integer (Required)
  * `cage_today_mortality_pct`: Computed Float
  * `cause_of_death`: Selection (`disease`, `heat_stress`, `cannibalism`, `smothering`, `sudden_death`, `other`)
  * `state`: Selection (`draft`, `waiting_approval`, `done`, `rejected`)
  * `scrap_id`: Many2one `stock.scrap`
  * `rejection_reason`: Text
* Business Methods:
  * `action_submit()`:
    1. Validate `dead_bird_count <= available_live_birds`. If greater, raise `ValidationError`.
    2. Compute **Cumulative Daily Cage Total**:
       $$\text{Total Dead Today} = \sum (\text{previous confirmed dead today in this cage}) + \text{dead\_bird\_count}$$
       $$\text{Daily Mortality \%} = (\text{Total Dead Today} / \text{available\_live\_birds}) \times 100$$
    3. If `Daily Mortality % > daily_mortality_threshold_pct`:
       * Set `state = 'waiting_approval'`.
       * Post chatter alert tagging `group_farm_manager`.
    4. Else ($\le 2\%$):
       * Execute `_create_and_validate_scrap()`.
       * Set `state = 'done'`.
  * `action_manager_approve()`:
    1. Check user has `top_farm_core.group_farm_manager`.
    2. Re-validate: ensure `dead_bird_count <= cage_location_id.get_live_bird_count()`.
    3. Execute `_create_and_validate_scrap()`.
    4. Set `state = 'done'`.
  * `action_reject()`:
    1. Require `rejection_reason`.
    2. Set `state = 'rejected'`. Return entry to draft for correction.
  * `_create_and_validate_scrap()`:
    * Create `stock.scrap`: product = `bird_product_id`, qty = `dead_bird_count`, location = `cage_location_id`, lot = `batch_lot_id`.
    * Validate scrap. The Odoo 19 `stock.move._get_analytic_distribution()` hook automatically attaches Batch and Cage analytic lines!

### 3.3 Developer Acceptance Testing (Phase 3)
- [ ] Cage A-01 has 1,000 birds. Enter 15 dead birds (1.5%). Click Submit. Verify it validates immediately and live count drops to 985.
- [ ] Anti-Bypass Test: Same day, enter another 10 dead birds (total = 25 / 1,000 = 2.5%). Click Submit. Verify system blocks direct execution and sets status to **Waiting Manager Approval**.
- [ ] Log in as Farm Manager. Click Approve. Verify stock scrap executes, GL 630000 is debited, and live birds drop to 975.
- [ ] Attempt to enter 2,000 dead birds in Cage A-01 (more than on hand). Verify system throws a strict `ValidationError`.

---

# Phase 4: Module 4 — `top_farm_dashboard`

* **Target Effort:** 17–18 Hours  
* **Dependencies:** `top_farm_core`, `top_farm_operations`, `top_farm_mortality`, `sale`, `account`  
* **Folder Name:** `top_farm_dashboard`

### 4.1 Directory Structure to Build
```text
top_farm_dashboard/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── farm_production_report.py
│   ├── farm_mortality_report.py
│   └── sale_order.py
└── views/
    ├── farm_dashboard_views.xml
    ├── farm_mortality_report_views.xml
    └── farm_profitability_views.xml
```

### 4.2 Step-by-Step Implementation Steps

#### Step 1: Sale Order Invoice Tagging in `models/sale_order.py`
* When an egg delivery order (`stock.picking`) is validated, retrieve the egg batch lot (e.g. `LOT-EGG-C01-YYYYMMDD`).
* Resolve parent batch analytic account from the lot.
* Automatically assign the Batch Analytic Account to the linked Customer Invoice line (`account.move.line`).

#### Step 2: Mortality Report in `models/farm_mortality_report.py`
* SQL view model `farm.mortality.report`:
  * Columns: Date, Batch, Cage, Cause of Death, Dead Count, Cage Population, Mortality Rate %.
  * Define Pivot and Graph views grouping by Batch, Cage, Cause, and Month.
  * Verify calculation: 75 dead birds / 20,000 flock birds = **0.375%**.

#### Step 3: Size-Weighted Profitability Engine & Report
* SQL/Python BI model `farm.profitability.report`:
  * Fetch Batch egg revenue grouped by size ($s \in \{\text{Medium, Large, Jumbo, Damage}\}$).
  * Compute Size-Weighted Cage Revenue:
    $$\text{Cage Revenue} = \sum_{s} \left[ \text{Batch Revenue}_s \times \left(\frac{\text{Cage Qty}_s}{\text{Batch Qty}_s}\right) \right]$$
  * Fetch Cage Direct Costs:
    * Feed Consumed (from MO component moves)
    * Medication Expense (from `610000` analytic lines)
    * Mortality Loss (from `630000` scrap analytic lines)
  * Compute **Gross Operating Profit** = $\text{Cage Revenue} - (\text{Feed} + \text{Medication} + \text{Mortality Loss})$.
  * Compute **Operating Margin %** = $(\text{Gross Profit} / \text{Cage Revenue}) \times 100$.

#### Step 4: KPI Dashboard Cards
* Action and Client Action/View with KPI metric cards:
  * **Current Live Flock Population** (Real-time sum of live quants across all cages)
  * **Today's Hen-Day Rate (%)** (Sum of today's eggs / Sum of confirmed snapshot birds)
  * **Flock Feed Conversion Ratio (FCR)** (kg of feed per dozen eggs)
  * **Today's Mortality Rate (%)**

### 4.3 Developer Acceptance Testing (Phase 4)
- [ ] Deliver eggs from `Batch C-01`. Confirm invoice line automatically gets `Batch C-01 Analytic Account`.
- [ ] Open Mortality Pivot: Verify mortality rates calculate accurately by cage (e.g., 44 dead / 1,000 = 4.40%).
- [ ] Open Profitability Pivot: Confirm `630000 Mortality Loss` is deducted from operating margin.
- [ ] Verify Cage A-01 (mostly Large/Jumbo) shows higher gross revenue than Cage A-02 (mostly Damage).

---

# Phase 5: Master Setup & System Pre-requisites Checklist

Before executing end-to-end tests or handing over to users, the following configurations must be made in Odoo 19:

1. **Product Categories (Set to Perpetual Valuation):**
   * Go to **Inventory $\rightarrow$ Configuration $\rightarrow$ Product Categories**.
   * Open `Poultry Feed` $\rightarrow$ Set Inventory Valuation = **Automated (real_time)**.
   * Open `Medication & Vaccines` $\rightarrow$ Set Inventory Valuation = **Automated (real_time)**.
   * Open `Live Birds / Layers` $\rightarrow$ Set Inventory Valuation = **Automated (real_time)**.
   * Open `Graded Table Eggs` $\rightarrow$ Set Inventory Valuation = **Automated (real_time)**.

2. **Virtual Location Valuation Accounts:**
   * Go to **Inventory $\rightarrow$ Configuration $\rightarrow$ Locations**.
   * Create `Virtual Locations/Feed Consumption` $\rightarrow$ Set Valuation Account = `600000 Feed Expense`.
   * Create `Virtual Locations/Medication Consumption` $\rightarrow$ Set Valuation Account = `610000 Vet & Medication Expense`.
   * Open `Virtual Locations/Scrapped` $\rightarrow$ Set Valuation Account = `630000 Mortality Loss`.

3. **Multi-Analytic Plans:**
   * Go to **Accounting $\rightarrow$ Configuration $\rightarrow$ Analytic Plans**.
   * Create Plan 1: **Flock Batch Plan**.
   * Create Plan 2: **Cage Row Plan**.
   * Set both plans as independent dimensions.

4. **Chief Accountant Policy Sign-Off:**
   * Confirm Pre-Laying Feed policy: **Option A (Direct Expense to 600000)** vs **Option B (Capitalization to 141000 Biological Asset)**.
