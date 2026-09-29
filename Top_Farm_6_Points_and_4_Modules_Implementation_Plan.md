# Top Farm: 6 Customization Points & Individual Module Implementation Plans

**Target System:** Odoo 19.0 (Enterprise / Community)  
**Total Project Boundary:** 120–130 Hours (91–98 Dev Hours + 29–32 QA/UAT/Deployment)  
**Architecture:** 4 Modular Addons mapping directly to the 6 Core BRD Customization Points  

---

## Part 1: Mapping the 6 Customization Points to the 4 Modules

The Business Requirements Document (BRD) defines **6 critical customization points** needed to operate a commercial poultry layer farm in Odoo. In our clean, modular architecture, these 6 points are grouped into **4 custom modules** to respect single-responsibility and dependency boundaries:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        6 BRD CUSTOMIZATION POINTS MAPPING                              │
├──────────────────────────────────────────────────────┬─────────────────────────────────┤
│ BRD Customization Point                              │ Implementing Odoo 19 Module     │
├──────────────────────────────────────────────────────┼─────────────────────────────────┤
│ Point 1: 3-Tier Farm/Batch/Cage Location Hierarchy   │ Module 1: top_farm_core         │
│          & Single Analytic Hook                      │                                 │
├──────────────────────────────────────────────────────┼─────────────────────────────────┤
│ Point 2: Daily Feed & Medication Logging Screen       │ Module 2: top_farm_operations   │
│          (Pre-Laying direct expense vs Laying stage) │                                 │
├──────────────────────────────────────────────────────┼─────────────────────────────────┤
│ Point 3: Daily Graded Egg Collection Screen          │ Module 2: top_farm_operations   │
│          (Medium, Large, Jumbo, Damage + Snapshot)   │                                 │
├──────────────────────────────────────────────────────┼─────────────────────────────────┤
│ Point 4: Proportional MO Auto-Split Engine           │ Module 2: top_farm_operations   │
│          (Feed allocation formula + zero rounding)   │                                 │
├──────────────────────────────────────────────────────┼─────────────────────────────────┤
│ Point 5: Mortality Logging with Cumulative > 2%      │ Module 3: top_farm_mortality    │
│          Guard, Manager Approval & stock.scrap Hook  │                                 │
├──────────────────────────────────────────────────────┼─────────────────────────────────┤
│ Point 6: Biological KPI Dashboards (Hen-Day, FCR)    │ Module 4: top_farm_dashboard    │
│          & Size-Weighted Cage Revenue P&L            │                                 │
└──────────────────────────────────────────────────────┴─────────────────────────────────┘
```

---

## Part 2: Individual Implementation Plan — Module 1 (`top_farm_core`)

* **Implements:** **Point 1 (Farm Hierarchy & Analytic Hook)**
* **Target Effort:** 11–12 Dev Hours (Total with QA: 14–16 hrs)
* **Dependencies:** `base`, `stock`, `stock_account`, `analytic`

### 1.1 Directory Structure
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

### 1.2 Model & Business Logic Specifications
1. **`stock.location` Extensions (`models/stock_location.py`):**
   * `farm_hierarchy_level`: Selection `[('farm', 'Farm Facility'), ('batch', 'Batch / Flock'), ('cage', 'Cage Sublocation')]`.
   * `parent_batch_location_id`: Many2one `stock.location`, computed recursively up `location_id` until a location with `farm_hierarchy_level == 'batch'` is resolved.
   * `batch_stage`: Selection `[('pre_laying', 'Pre-Laying (Weeks 1–18)'), ('laying', 'Laying Phase (Weeks 19–72)'), ('spent', 'Spent Hen / Depleted')]`.
   * `chick_arrival_date`: Date; computes `flock_age_weeks = (today - chick_arrival_date).days / 7.0`.
   * `farm_analytic_account_id`: Many2one `account.analytic.account`.
   * `get_analytic_distribution_for_cage()`: Returns `{str(cage_analytic.id): 100.0, str(batch_analytic.id): 100.0}`.
   * `get_live_bird_count()`: Reads `stock.quant` for storable poultry layer products in `child_of self.id`.
   * `action_start_laying_phase()`: Restrict to `group_farm_manager`. Promotes `batch_stage` from `pre_laying` to `laying`.
2. **The Single Odoo 19 Analytic Hook (`models/stock_move.py`):**
   * In Odoo 19, `mrp.production` has no direct `analytic_distribution` field.
   * Override `stock.move._get_analytic_distribution()`:
     1. Call `super()._get_analytic_distribution()`.
     2. Identify if `location_id`, `location_dest_id`, or `raw_material_production_id.farm_collection_id` points to a cage.
     3. If cage found, return `cage.get_analytic_distribution_for_cage()`.
     4. This automatically populates `account.analytic.line` for feed consumption, manufacturing orders, and mortality scrap moves without creating duplicate journal items.

### 1.3 UI & Security
* **Form View:** Statusbar with stage, button "Start Laying Phase (Week 19)", smart buttons for "Cages" and "Live Birds", and poultry configuration group.
* **List View:** Tree showing Name, Level, Parent Batch, Stage, Flock Age, Live Birds, Analytic Account.
* **Menus:** Root menu **Top Farm** $\rightarrow$ **Farm Configuration** $\rightarrow$ **Farm, Batch & Cage Hierarchy**.

### 1.4 Acceptance Criteria
- [ ] Create `Farm 1` $\rightarrow$ `Batch C-01` $\rightarrow$ `Cage A-01`. Confirm `parent_batch_location_id` auto-resolves.
- [ ] Receive 20,000 birds into Batch C-01; transfer 1,000 birds to Cage A-01. Confirm live count reads 1,000.
- [ ] Perform a test scrap from Cage A-01. Confirm `account.analytic.line` is generated with Batch (100%) and Cage (100%).

---

## Part 3: Individual Implementation Plan — Module 2 (`top_farm_operations`)

* **Implements:** **Point 2 (Daily Feed/Med Log)**, **Point 3 (Egg Collection)**, **Point 4 (Proportional MO Auto-Split Engine)**
* **Target Effort:** 51–55 Dev Hours (Total with QA: 65–70 hrs)
* **Dependencies:** `top_farm_core`, `mrp`, `mrp_account`, `mail`

### 2.1 Directory Structure
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

### 2.2 Model & Business Logic Specifications
1. **Daily Feed & Medication Log (`farm.feed.log` & `farm.feed.log.line`):**
   * Captures Date, Batch, Cage, Feeding Phase (`pre_laying` vs `laying`), Feed lines (Product, Silo Source Location, Quantity, UoM).
   * **Pre-Laying & Medication Execution:** When confirmed in `pre_laying` (or if line is medication), creates and immediately validates a `stock.picking` from Silo to `Virtual Locations/Feed Consumption` (or `Medication Consumption`). The Module 1 hook immediately tags the GL expense to Batch & Cage.
   * **Laying Feed Staging:** When confirmed in `laying`, marks status `confirmed` without moving inventory (staging it for the egg collection MO).
2. **Graded Egg Collection Form (`farm.egg.collection`):**
   * Inputs 4 egg size quantities: `qty_medium`, `qty_large`, `qty_jumbo`, `qty_damage`.
   * Captures `confirmed_live_bird_count = cage.get_live_bird_count()` as a permanent stored snapshot.
   * Computes Hen-Day Rate % and FCR (kg of feed per dozen eggs).
3. **Proportional Manufacturing Order Splitting Engine:**
   * Method `action_generate_split_manufacturing_orders()`:
     1. Allocates total feed consumed across active egg grades:
        $$\text{Feed}_i = \text{round}\left(\text{Total Feed Consumed} \times \frac{\text{Egg Qty}_i}{\text{Total Egg Qty}}, \; 4\right)$$
     2. **Zero-Rounding Reconciliation:** Calculates $\Delta = \text{Total Feed} - \sum \text{Feed}_i$ and adds $\Delta$ to the largest egg grade.
     3. Auto-generates egg traceability lot: `LOT-EGG-{batch}-{YYYYMMDD}`.
     4. Generates, validates, and marks `done` up to 4 separate `mrp.production` records.
     5. Reconciles and closes the linked `farm.feed.log`.
4. **Nightly Cron Fallback (`cron_reconcile_unharvested_feed`):**
   * Runs daily at 23:59. Identifies any confirmed laying feed logs with no egg collections recorded and expenses the staged feed to `600000 Feed Expense` as maintenance feed.

### 2.3 Acceptance Criteria
- [ ] Pre-laying feed (50 kg) creates picking and debits `600000 Feed Expense` with Cage & Batch analytic lines.
- [ ] Laying feed (100 kg) does NOT move stock upon feed confirmation.
- [ ] Collection of 500 Large, 300 Medium, 100 Jumbo, 100 Damage produces 4 MOs consuming exactly 50 kg, 30 kg, 10 kg, and 10 kg of feed.
- [ ] Graded eggs land in `WH/Stock/Eggs/Batch-C01` with lot `LOT-EGG-C01-YYYYMMDD`.

---

## Part 4: Individual Implementation Plan — Module 3 (`top_farm_mortality`)

* **Implements:** **Point 5 (Mortality Logging, Approval & stock.scrap)**
* **Target Effort:** 12–13 Dev Hours (Total with QA: 16–18 hrs)
* **Dependencies:** `top_farm_core`, `stock_account`, `mail`

### 3.1 Directory Structure
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

### 3.2 Model & Business Logic Specifications
1. **Configurable Tolerance (`models/res_config_settings.py`):**
   * Adds `daily_mortality_threshold_pct` to `res.company` / `res.config.settings` (Default: `2.0%`).
2. **Mortality Entry Model (`models/farm_mortality_log.py`):**
   * Fields: `date`, `batch_location_id`, `cage_location_id`, `bird_product_id`, `batch_lot_id`, `dead_bird_count`, `available_live_birds`, `cause_of_death` (Disease, Heat stress, Cannibalism, Smothering, Sudden death, Other), `state` (`draft`, `waiting_approval`, `done`, `rejected`).
3. **Anti-Bypass Approval & Scrap Engine:**
   * On `action_submit()`:
     - **Hard Guard:** Ensures `dead_bird_count <= available_live_birds`.
     - **Cumulative Daily Check:**
       $$\text{Cumulative Dead Today} = \sum (\text{Confirmed Dead Today in this Cage}) + \text{Current Dead Count}$$
       $$\text{Daily Mortality \%} = \left(\frac{\text{Cumulative Dead Today}}{\text{Available Live Birds}}\right) \times 100$$
     - If $\text{Daily Mortality \%} > 2.0\%$: Sets `state = 'waiting_approval'` and notifies `group_farm_manager` in chatter.
     - If $\le 2.0\%$: Automatically calls `_create_and_validate_scrap()`.
4. **Approval & Rejection Methods:**
   * `action_manager_approve()`: Re-checks live quants, calls `_create_and_validate_scrap()`, transitions to `done`.
   * `action_reject()`: Requires mandatory rejection reason and resets state to `draft` for correction.
5. **Scrap Execution (`_create_and_validate_scrap`):**
   * Creates and validates `stock.scrap`: Location = `cage_location_id`, Scrap Location = `Virtual Locations/Scrapped`, Lot = `batch_lot_id`.
   * Triggers Module 1 analytic hook $\rightarrow$ Debits `630000 Mortality Loss` with Batch & Cage analytic lines.

### 3.3 Acceptance Criteria
- [ ] Log 15 dead birds out of 1,000 (1.5%). Validates immediately; live bird count drops to 985.
- [ ] Same day: Log another 10 dead birds (25 / 1,000 = 2.5%). System blocks direct scrap and sets `waiting_approval`.
- [ ] Farm Manager clicks Approve. System creates `stock.scrap`, debits `630000 Mortality Loss`, and drops live birds to 975.
- [ ] Attempting to log 2,000 dead birds throws a strict `ValidationError`.

---

## Part 5: Individual Implementation Plan — Module 4 (`top_farm_dashboard`)

* **Implements:** **Point 6 (KPI Dashboards, Size-Weighted Revenue & Cage P&L)**
* **Target Effort:** 17–18 Dev Hours (Total with QA: 21–22 hrs)
* **Dependencies:** `top_farm_core`, `top_farm_operations`, `top_farm_mortality`, `sale`, `account`

### 4.1 Directory Structure
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

### 4.2 Model & Business Logic Specifications
1. **Sales Delivery Invoice Tagging (`models/sale_order.py`):**
   * When an egg delivery picking is validated, resolves the parent batch from the egg lot (`LOT-EGG-C01-YYYYMMDD`).
   * Automatically populates the Batch Analytic Account on the customer invoice line (`account.move.line`).
2. **Mortality Analysis Pivot (`models/farm_mortality_report.py`):**
   * SQL view calculating:
     $$\text{Mortality \%} = \left(\frac{\text{Dead Birds}}{\text{Total Flock Population}}\right) \times 100$$
   * (e.g., $75 / 20,000 = \mathbf{0.375\%}$). Groupable by Batch, Cage, Month, and Cause of Death.
3. **Size-Weighted Cage Revenue Allocation Engine:**
   * Resolves mixed egg warehouse sales by calculating cage revenue based on the market price of egg grades produced:
     $$\text{Cage Revenue} = \sum_{s \in \{\text{Medium, Large, Jumbo, Damage}\}} \left[ \text{Batch Revenue}_s \times \left(\frac{\text{Cage Qty}_s}{\text{Batch Qty}_s}\right) \right]$$
4. **Cage Operating Margin Report (`farm.profitability.report`):**
   * Pulls Direct Cage Costs from GL analytic lines:
     - Feed Consumed (from MO raw moves)
     - Medication Expense (Account `610000`)
     - Mortality Loss (Account `630000`)
   * Calculates:
     $$\text{Gross Operating Profit} = \text{Cage Revenue} - (\text{Feed} + \text{Medication} + \text{Mortality})$$
     $$\text{Operating Margin \%} = \left(\frac{\text{Gross Profit}}{\text{Cage Revenue}}\right) \times 100$$
5. **Real-Time KPI Cards:**
   * Live Population (real-time quant sum), Hen-Day Rate %, Feed Conversion Ratio (kg/dozen), and Today's Mortality %.

### 4.3 Acceptance Criteria
- [ ] Deliver egg lot `LOT-EGG-C01-20260929`. Verify linked customer invoice line inherits Batch C-01 Analytic Account.
- [ ] Open Profitability Pivot: Confirm `630000 Mortality Loss` is deducted from Cage Gross Margin.
- [ ] Confirm Cage A-01 (mostly Large/Jumbo) shows higher gross revenue than Cage A-02 (mostly Damage).
- [ ] Confirm Hen-Day % and FCR (kg/dozen) calculate accurately on dashboard cards.

---

## Part 6: Total Effort & Project Hours Summary

| Module | Implemented BRD Customization Points | Developer Hours | QA & Deployment | Total Hours |
| :--- | :--- | :---: | :---: | :---: |
| **`top_farm_core`** | **Point 1** (Hierarchy, Bird Quants, Analytic Hook) | 11–12 hrs | 3–4 hrs | 14–16 hrs |
| **`top_farm_operations`** | **Point 2, 3, 4** (Feed Log, Egg Screen, MO Engine) | 51–55 hrs | 14–15 hrs | 65–70 hrs |
| **`top_farm_mortality`** | **Point 5** (Mortality Log, Cumulative Guard, Scrap) | 12–13 hrs | 4–5 hrs | 16–18 hrs |
| **`top_farm_dashboard`** | **Point 6** (KPIs, Size-Weighted Revenue, Cage P&L) | 17–18 hrs | 4–4 hrs | 21–22 hrs |
| **System Prerequisites** | Automated Valuation (`real_time`) & Account Setup | — | 4–4 hrs | 4–4 hrs |
| **Total Project** | **All 6 Customization Points Completed** | **91–98 hrs** | **29–32 hrs** | **120–130 hrs** |
