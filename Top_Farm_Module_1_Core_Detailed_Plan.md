# Top Farm: Module 1 (`top_farm_core`) — Detailed Developer Implementation Plan

**Target System:** Odoo 19.0 (Enterprise / Community)  
**Effort Allocation:** 11–12 Developer Hours + 3–4 QA Hours (Total: 14–16 Hours)  
**Dependencies:** `base`, `stock`, `stock_account`, `analytic`  
**Module Name:** `top_farm_core`  
**License:** LGPL-3  

---

## 1. Module Overview & Architectural Purpose

`top_farm_core` is the foundational bedrock of the entire Top Farm Poultry ERP solution. It accomplishes three critical infrastructure objectives:

1. **Physical Poultry Facility Hierarchy:** Extends standard Odoo `stock.location` to structure locations into a 3-tier parent-child relationship: **Farm Facility $\rightarrow$ Batch / Flock $\rightarrow$ Cage Sublocation**, with automatic parent-batch resolution and flock lifecycle stage management (Pre-Laying, Laying, Depleted).
2. **Real-Time Live Bird Tracking:** Integrates with `stock.quant` to dynamically calculate live layer bird counts at Cage, Batch, and Farm levels without manual counters, preserving hatchery lot traceability (`LOT-2026-01`).
3. **The Single Odoo 19 Analytic Distribution Hook:** Overrides `stock.move._get_analytic_distribution()` in `stock_account`. In Odoo 19, `mrp.production` has no direct analytic distribution field; this single hook detects cage/batch locations across feed pickings, manufacturing orders, and mortality scraps, automatically populating dual-dimensional analytic tags (`Batch` and `Cage`) on `account.analytic.line` without requiring complex project setups or doubling journal items.

---

## 2. Directory & File Structure

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

---

## 3. Detailed Technical Specifications

### 3.1 `__manifest__.py`

```python
{
    'name': 'Top Farm Core - Poultry Hierarchy & Analytics',
    'version': '19.0.1.0.0',
    'category': 'Poultry Farm Operations',
    'summary': 'Physical farm hierarchy, live bird tracking, and analytic tagging for commercial poultry layers',
    'description': """
Top Farm Core Infrastructure
============================
- 3-Tier Farm / Batch / Cage location hierarchy with automated parent batch detection.
- Flock lifecycle stage management (Pre-Laying, Laying, Spent).
- Live bird stock tracking via stock.quant.
- Odoo 19 single stock.move analytic distribution hook for dual Batch/Cage P&L.
    """,
    'author': 'Top Farm ERP Team',
    'depends': [
        'base',
        'stock',
        'stock_account',
        'analytic',
    ],
    'data': [
        'security/farm_security.xml',
        'security/ir.model.access.csv',
        'views/stock_location_views.xml',
        'views/farm_menus.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
```

### 3.2 Security Definitions

#### File: `security/farm_security.xml`
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="module_category_top_farm" model="ir.module.category">
        <field name="name">Poultry Farm Management</field>
        <field name="description">Access rights for poultry farm operations, batches, and analytics.</field>
        <field name="sequence">50</field>
    </record>

    <!-- Farm Operator / User -->
    <record id="group_farm_user" model="res.groups">
        <field name="name">Farm Operator / User</field>
        <field name="category_id" ref="module_category_top_farm"/>
        <field name="implied_ids" eval="[(4, ref('stock.group_stock_user'))]"/>
    </record>

    <!-- Farm Manager / Supervisor -->
    <record id="group_farm_manager" model="res.groups">
        <field name="name">Farm Manager / Supervisor</field>
        <field name="category_id" ref="module_category_top_farm"/>
        <field name="implied_ids" eval="[(4, ref('group_farm_user')), (4, ref('stock.group_stock_manager'))]"/>
    </record>
</odoo>
```

#### File: `security/ir.model.access.csv`
```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_stock_location_farm_user,stock.location.farm.user,stock.model_stock_location,group_farm_user,1,1,0,0
access_stock_location_farm_manager,stock.location.farm.manager,stock.model_stock_location,group_farm_manager,1,1,1,1
```

---

### 3.3 Models Implementation

#### File: `models/stock_location.py`
Extends `stock.location` with farm classification, batch relationships, bird counts, and analytic resolution.

```python
from datetime import date
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class StockLocation(models.Model):
    _inherit = 'stock.location'

    farm_hierarchy_level = fields.Selection([
        ('farm', 'Farm Facility'),
        ('batch', 'Batch / Flock'),
        ('cage', 'Cage Sublocation'),
    ], string='Farm Hierarchy Level', index=True,
       help="Categorizes location into Farm, Batch (Flock house), or Cage level.")

    parent_batch_location_id = fields.Many2one(
        'stock.location',
        string='Parent Batch Location',
        compute='_compute_parent_batch_location',
        store=True,
        index=True,
        domain="[('farm_hierarchy_level', '=', 'batch')]",
        help="Automatically resolved parent batch location for cage sublocations."
    )

    batch_stage = fields.Selection([
        ('pre_laying', 'Pre-Laying (Weeks 1–18)'),
        ('laying', 'Laying Phase (Weeks 19–72)'),
        ('spent', 'Spent Hen / Depleted'),
    ], string='Flock Lifecycle Stage', default='pre_laying', tracking=True,
       help="Current physiological stage of the flock.")

    chick_arrival_date = fields.Date(
        string='Chick Arrival Date',
        help="Date when day-old chicks or pullets arrived at the facility."
    )

    flock_age_weeks = fields.Float(
        string='Flock Age (Weeks)',
        compute='_compute_flock_age',
        digits=(16, 1),
        help="Calculated age of the flock in weeks based on arrival date."
    )

    farm_analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Farm / Batch / Cage Analytic Account',
        copy=False,
        help="Analytic account mapped directly to this Batch or Cage for P&L tracking."
    )

    live_bird_count = fields.Integer(
        string='Live Birds',
        compute='_compute_live_bird_count',
        help="Current count of live birds on hand at this location (from stock.quant)."
    )

    sub_cage_count = fields.Integer(
        string='Cages Count',
        compute='_compute_sub_cage_count',
        help="Number of active cage sublocations under this batch or farm."
    )

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------
    @api.depends('farm_hierarchy_level', 'location_id', 'location_id.farm_hierarchy_level', 'location_id.parent_batch_location_id')
    def _compute_parent_batch_location(self):
        """Recursively resolve the parent batch location for cage sublocations."""
        for loc in self:
            if loc.farm_hierarchy_level == 'cage':
                curr = loc.location_id
                batch_loc = False
                while curr:
                    if curr.farm_hierarchy_level == 'batch':
                        batch_loc = curr
                        break
                    curr = curr.location_id
                loc.parent_batch_location_id = batch_loc
            elif loc.farm_hierarchy_level == 'batch':
                loc.parent_batch_location_id = loc
            else:
                loc.parent_batch_location_id = False

    @api.depends('chick_arrival_date')
    def _compute_flock_age(self):
        """Compute age of flock in weeks."""
        today = fields.Date.today()
        for loc in self:
            if loc.chick_arrival_date:
                delta_days = (today - loc.chick_arrival_date).days
                loc.flock_age_weeks = max(0.0, round(delta_days / 7.0, 1))
            elif loc.parent_batch_location_id and loc.parent_batch_location_id != loc and loc.parent_batch_location_id.chick_arrival_date:
                delta_days = (today - loc.parent_batch_location_id.chick_arrival_date).days
                loc.flock_age_weeks = max(0.0, round(delta_days / 7.0, 1))
            else:
                loc.flock_age_weeks = 0.0

    def _compute_live_bird_count(self):
        """Compute live bird quantity directly from stock.quant."""
        for loc in self:
            loc.live_bird_count = loc.get_live_bird_count()

    def _compute_sub_cage_count(self):
        """Count child cages."""
        for loc in self:
            if loc.farm_hierarchy_level in ('farm', 'batch'):
                loc.sub_cage_count = self.search_count([
                    ('id', 'child_of', loc.id),
                    ('farm_hierarchy_level', '=', 'cage')
                ])
            else:
                loc.sub_cage_count = 0

    # -------------------------------------------------------------------------
    # CONSTRAINTS & VALIDATIONS
    # -------------------------------------------------------------------------
    @api.constrains('farm_hierarchy_level', 'parent_batch_location_id')
    def _check_cage_parent_batch(self):
        for loc in self:
            if loc.farm_hierarchy_level == 'cage' and not loc.parent_batch_location_id:
                raise ValidationError(_(
                    "Cage location '%s' must be located under a parent location classified as 'Batch / Flock'.",
                    loc.display_name
                ))

    # -------------------------------------------------------------------------
    # PUBLIC HELPER METHODS
    # -------------------------------------------------------------------------
    def get_live_bird_count(self):
        """Query live bird count on hand for this location or its children."""
        self.ensure_one()
        quants = self.env['stock.quant'].search([
            ('location_id', 'child_of', self.id),
            ('product_id.type', '=', 'consu'),
            ('product_id.is_storable', '=', True),
            ('product_id.categ_id.name', 'ilike', 'Bird')
        ])
        return int(sum(quants.mapped('quantity')))

    def get_analytic_distribution_for_cage(self):
        """
        Returns the dual-dimensional analytic distribution dict:
        {str(cage_analytic_id): 100.0, str(batch_analytic_id): 100.0}
        """
        self.ensure_one()
        distribution = {}
        if self.farm_analytic_account_id:
            distribution[str(self.farm_analytic_account_id.id)] = 100.0
        
        parent_batch = self.parent_batch_location_id
        if parent_batch and parent_batch.farm_analytic_account_id:
            batch_analytic_id = str(parent_batch.farm_analytic_account_id.id)
            distribution[batch_analytic_id] = 100.0
            
        return distribution

    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------
    def action_start_laying_phase(self):
        """Transition batch from Pre-Laying to Laying phase."""
        self.ensure_one()
        if not self.env.user.has_group('top_farm_core.group_farm_manager'):
            raise ValidationError(_("Only Farm Managers can start the Laying Phase."))
        if self.batch_stage != 'pre_laying':
            raise ValidationError(_("Only flocks in 'Pre-Laying' stage can be transitioned to 'Laying'."))
        self.batch_stage = 'laying'
        cages = self.search([('id', 'child_of', self.id), ('farm_hierarchy_level', '=', 'cage')])
        cages.write({'batch_stage': 'laying'})
        return True

    def action_view_cages(self):
        """Action for smart button to view child cages."""
        self.ensure_one()
        action = self.env.ref('stock.action_location_form').read()[0]
        action['domain'] = [('id', 'child_of', self.id), ('farm_hierarchy_level', '=', 'cage')]
        action['context'] = {'default_location_id': self.id, 'default_farm_hierarchy_level': 'cage'}
        return action

    def action_view_live_birds(self):
        """Action for smart button to view quants of live birds."""
        self.ensure_one()
        action = self.env.ref('stock.quantsact').read()[0]
        action['domain'] = [('location_id', 'child_of', self.id), ('product_id.categ_id.name', 'ilike', 'Bird')]
        return action
```

---

#### File: `models/stock_move.py`
Overrides `stock.move` to provide the **single analytic distribution hook** in Odoo 19.

```python
from odoo import models

class StockMove(models.Model):
    _inherit = 'stock.move'

    def _get_analytic_distribution(self):
        """
        Single Analytic Hook in Odoo 19:
        Captures cage and batch analytic distribution for:
        1. Pre-laying feed & medication pickings to virtual consumption locations.
        2. Raw material feed consumption in egg harvest Manufacturing Orders (mrp.production).
        3. Bird mortality scrap moves (stock.scrap).
        """
        distribution = super()._get_analytic_distribution()
        if distribution:
            return distribution

        cage = False
        if self.location_id and self.location_id.farm_hierarchy_level == 'cage':
            cage = self.location_id
        elif self.location_dest_id and self.location_dest_id.farm_hierarchy_level == 'cage':
            cage = self.location_dest_id
        elif self.raw_material_production_id and hasattr(self.raw_material_production_id, 'farm_collection_id'):
            collection = self.raw_material_production_id.farm_collection_id
            if collection and collection.cage_location_id:
                cage = collection.cage_location_id

        if cage:
            return cage.get_analytic_distribution_for_cage()

        return {}
```

---

### 3.4 Views & User Interface

#### File: `views/stock_location_views.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_location_form_top_farm" model="ir.ui.view">
        <field name="name">stock.location.form.top_farm</field>
        <field name="model">stock.location</field>
        <field name="inherit_id" ref="stock.view_location_form"/>
        <field name="arch" type="xml">
            <xpath expr="//sheet" position="before">
                <header>
                    <button name="action_start_laying_phase"
                            string="Start Laying Phase (Week 19)"
                            type="object"
                            class="oe_highlight"
                            invisible="farm_hierarchy_level != 'batch' or batch_stage != 'pre_laying'"
                            groups="top_farm_core.group_farm_manager"/>
                    <field name="batch_stage" widget="statusbar"
                           statusbar_visible="pre_laying,laying,spent"
                           invisible="farm_hierarchy_level not in ('batch', 'cage')"/>
                </header>
            </xpath>

            <xpath expr="//div[@name='button_box']" position="inside">
                <button name="action_view_cages"
                        type="object"
                        class="oe_stat_button"
                        icon="fa-th-large"
                        invisible="farm_hierarchy_level not in ('farm', 'batch')">
                    <field name="sub_cage_count" widget="statinfo" string="Cages"/>
                </button>
                <button name="action_view_live_birds"
                        type="object"
                        class="oe_stat_button"
                        icon="fa-twitter"
                        invisible="farm_hierarchy_level not in ('batch', 'cage')">
                    <field name="live_bird_count" widget="statinfo" string="Live Birds"/>
                </button>
            </xpath>

            <xpath expr="//group[@name='additional_info']" position="before">
                <group name="top_farm_group" string="Poultry Farm Operations &amp; Analytics">
                    <group>
                        <field name="farm_hierarchy_level"/>
                        <field name="parent_batch_location_id"
                               invisible="farm_hierarchy_level != 'cage'"
                               readonly="1"/>
                        <field name="farm_analytic_account_id"/>
                    </group>
                    <group invisible="farm_hierarchy_level not in ('batch', 'cage')">
                        <field name="chick_arrival_date"
                               readonly="farm_hierarchy_level == 'cage'"/>
                        <field name="flock_age_weeks"/>
                    </group>
                </group>
            </xpath>
        </field>
    </record>

    <record id="view_location_tree_top_farm" model="ir.ui.view">
        <field name="name">stock.location.list.top_farm</field>
        <field name="model">stock.location</field>
        <field name="arch" type="xml">
            <list string="Poultry Farm Hierarchy">
                <field name="display_name" string="Location Name"/>
                <field name="farm_hierarchy_level" widget="badge"
                       decoration-info="farm_hierarchy_level == 'farm'"
                       decoration-warning="farm_hierarchy_level == 'batch'"
                       decoration-success="farm_hierarchy_level == 'cage'"/>
                <field name="parent_batch_location_id"/>
                <field name="batch_stage" widget="badge"
                       decoration-muted="batch_stage == 'spent'"
                       decoration-primary="batch_stage == 'pre_laying'"
                       decoration-success="batch_stage == 'laying'"/>
                <field name="flock_age_weeks"/>
                <field name="live_bird_count" sum="Total Live Birds"/>
                <field name="farm_analytic_account_id"/>
            </list>
        </field>
    </record>

    <record id="view_location_search_top_farm" model="ir.ui.view">
        <field name="name">stock.location.search.top_farm</field>
        <field name="model">stock.location</field>
        <field name="inherit_id" ref="stock.view_location_search"/>
        <field name="arch" type="xml">
            <xpath expr="//filter[@name='inactive']" position="after">
                <separator/>
                <filter string="Farms" name="filter_farm" domain="[('farm_hierarchy_level', '=', 'farm')]"/>
                <filter string="Flock Batches" name="filter_batch" domain="[('farm_hierarchy_level', '=', 'batch')]"/>
                <filter string="Cages" name="filter_cage" domain="[('farm_hierarchy_level', '=', 'cage')]"/>
                <separator/>
                <filter string="Pre-Laying Flocks" name="filter_pre_laying" domain="[('batch_stage', '=', 'pre_laying')]"/>
                <filter string="Active Laying Flocks" name="filter_laying" domain="[('batch_stage', '=', 'laying')]"/>
                <group expand="0" string="Group By">
                    <filter string="Hierarchy Level" name="group_level" context="{'group_by': 'farm_hierarchy_level'}"/>
                    <filter string="Parent Batch" name="group_batch" context="{'group_by': 'parent_batch_location_id'}"/>
                    <filter string="Flock Stage" name="group_stage" context="{'group_by': 'batch_stage'}"/>
                </group>
            </xpath>
        </field>
    </record>

    <record id="action_top_farm_locations" model="ir.actions.act_window">
        <field name="name">Farm, Batch &amp; Cage Locations</field>
        <field name="res_model">stock.location</field>
        <field name="view_mode">list,form</field>
        <field name="view_id" ref="view_location_tree_top_farm"/>
        <field name="search_view_id" ref="view_location_search_top_farm"/>
        <field name="domain">[('farm_hierarchy_level', 'in', ('farm', 'batch', 'cage'))]</field>
        <field name="context">{'search_default_group_batch': 1}</field>
    </record>
</odoo>
```

---

#### File: `views/farm_menus.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <menuitem id="menu_top_farm_root"
              name="Top Farm"
              web_icon="top_farm_core,static/description/icon.png"
              sequence="25"/>

    <menuitem id="menu_top_farm_config"
              name="Farm Configuration"
              parent="menu_top_farm_root"
              sequence="100"/>

    <menuitem id="menu_top_farm_locations"
              name="Farm, Batch &amp; Cage Hierarchy"
              parent="menu_top_farm_config"
              action="action_top_farm_locations"
              sequence="10"/>
</odoo>
```

---

## 4. Developer Acceptance Testing & Verification Checklist

| # | Test Case Scenario | Input / Action | Expected Result | Verified (Pass/Fail) |
| :---: | :--- | :--- | :--- | :---: |
| **1** | Hierarchy Creation | Create `Farm 1` (Farm) $\rightarrow$ `Batch C-01` (Batch) $\rightarrow$ `Cage A-01` (Cage). | `Cage A-01` auto-resolves `parent_batch_location_id == Batch C-01`. | [ ] |
| **2** | Orphan Cage Guard | Try creating a Cage directly under a location that is NOT a Batch. | System raises a `ValidationError` blocking creation. | [ ] |
| **3** | Flock Age Calculation | Set `chick_arrival_date` = 140 days prior to today on `Batch C-01`. | `flock_age_weeks` displays **20.0**. | [ ] |
| **4** | Lifecycle State Transition | Farm Manager clicks **Start Laying Phase** on `Batch C-01`. | `batch_stage` changes from `pre_laying` to `laying` and propagates to sub-cages. Non-managers are blocked. | [ ] |
| **5** | Live Bird Count Precision | Move 1,000 layer birds (storable) to `Cage A-01` with Lot `LOT-001`. | `Cage A-01.live_bird_count` displays **1,000**. | [ ] |
| **6** | Analytic Distribution Hook | Validate a stock move with source `Cage A-01`. | Move triggers `_get_analytic_distribution()` and creates 2 analytic lines: Cage (100%) and Batch (100%). | [ ] |
| **7** | Security Access Rights | Log in as `group_farm_user`. Attempt to delete a Batch location. | System prevents deletion (read/write only, unlink restricted to Manager). | [ ] |
