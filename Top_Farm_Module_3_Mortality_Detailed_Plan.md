# Top Farm: Module 3 (`top_farm_mortality`) — Detailed Developer Implementation Plan

**Target System:** Odoo 19.0 (Enterprise / Community)  
**Effort Allocation:** 12–13 Developer Hours + 4–5 QA Hours (Total: 16–18 Hours)  
**Dependencies:** `top_farm_core`, `stock_account`, `mail`  
**Module Name:** `top_farm_mortality`  
**License:** LGPL-3  
**BRD Customization Point Covered:** Point 5 (Mortality Logging, Live Stock Guard, Approval Workflow & Automated Scrap)  

---

## 1. Module Overview & Operational Scope

In a commercial poultry farm housing 20,000 birds, natural mortality occurs daily (typically 0.05% to 0.1% per day). However, unexpected disease outbreaks, heat stress, or farm theft pose major risks. 

Standard Odoo inventory allows users to create scrap orders without verifying whether the scrapped quantity actually exists in a sublocation or enforcing approval rules for abnormal losses.

### Key Operational Deliverables:
1. **Dedicated Daily Mortality Log Screen (`farm.mortality.log`):**
   * Barn operators record dead birds removed from cages along with standard biological causes of death (Disease, Heat Stress, Cannibalism, Smothering, Sudden Death, Other).
2. **Hard Live Quant Upper Bound Guard:**
   * Prevents user error or data entry mistakes by strictly checking [`stock.quant`](file:///c:/pycharmproject/odoo19/odoo/addons/stock/models/stock_quant.py) in the cage: dead birds logged cannot exceed the current live bird population.
3. **Anti-Bypass Cumulative Daily Cage Threshold Check (> 2.0%):**
   * Configurable threshold in Settings (default: `2.0%`).
   * Evaluates the **cumulative daily loss** in that cage. If a worker logs 15 dead birds in the morning (1.5%) and another 10 dead birds in the afternoon (cumulative 2.5%), the system blocks direct execution and flags it for **Farm Manager Approval**.
4. **Automated `stock.scrap` Integration & Analytic Expense:**
   * When approved or within normal limits, the system automatically creates and validates a [`stock.scrap`](file:///c:/pycharmproject/odoo19/odoo/addons/stock/models/stock_scrap.py) record:
     * Moves birds from `Cage A-01` $\rightarrow$ `Virtual Locations/Scrapped`.
     * Retains the hatchery lot `LOT-2026-01`.
     * Debits GL `630000 Mortality Loss`.
     * Triggers the Module 1 hook to automatically apply **Batch (100%)** and **Cage (100%)** analytic tags.
5. **Live Bird Population Reduction:**
   * Instantly reduces the live bird quant in that cage, updating the smart buttons on `stock.location` in real time.

---

## 2. Directory & File Structure

```text
top_farm_mortality/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── farm_mortality_log.py          # Daily mortality logging & scrap engine
│   └── res_config_settings.py         # Configurable threshold in Settings
├── data/
│   └── ir_sequence_data.xml           # MORT/YYYY/XXXXX sequence
├── security/
│   └── ir.model.access.csv            # Security access rights
└── views/
    ├── farm_mortality_log_views.xml   # Form, list, search, and pivot views
    ├── res_config_settings_views.xml  # Setting: Daily Mortality Threshold %
    └── farm_mortality_menus.xml       # Top Farm ➔ Farm Operations ➔ Mortality
```

---

## 3. Detailed Technical Specifications

### 3.1 `__manifest__.py`

```python
{
    'name': 'Top Farm Mortality - Poultry Loss Tracking & Approvals',
    'version': '19.0.1.0.0',
    'category': 'Poultry Farm Operations',
    'summary': 'Daily mortality logging, live bird safeguards, abnormal loss approvals, and automated scrap moves',
    'description': """
Top Farm Mortality Management
=============================
- Daily mortality logging by Cage, Batch, and Cause of Death.
- Live stock verification against stock.quant in cage sublocations.
- Anti-bypass cumulative daily mortality threshold check (> 2.0%).
- Farm Manager approval workflow with chatter alerts.
- Automated stock.scrap creation with Batch & Cage analytic tagging to GL 630000.
    """,
    'author': 'Top Farm ERP Team',
    'depends': [
        'top_farm_core',
        'stock_account',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/res_config_settings_views.xml',
        'views/farm_mortality_log_views.xml',
        'views/farm_mortality_menus.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
```

---

### 3.2 Data Models Implementation

#### File: `models/res_config_settings.py`
Adds the configurable mortality threshold to `res.company` and `res.config.settings`:

```python
from odoo import fields, models

class ResCompany(models.Model):
    _inherit = 'res.company'

    daily_mortality_threshold_pct = fields.Float(
        string='Daily Mortality Approval Threshold (%)',
        default=2.0,
        help="If cumulative dead birds in a cage exceed this percentage of live population in a day, supervisor approval is required."
    )

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    daily_mortality_threshold_pct = fields.Float(
        related='company_id.daily_mortality_threshold_pct',
        readonly=False,
        string='Daily Mortality Approval Threshold (%)'
    )
```

---

#### File: `models/farm_mortality_log.py`
Handles daily mortality entries, validations, approval routing, and scrap creation:

```python
from datetime import date
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class FarmMortalityLog(models.Model):
    _name = 'farm.mortality.log'
    _description = 'Daily Poultry Mortality Log'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    date = fields.Date(string='Incident Date', required=True, default=fields.Date.context_today, tracking=True)
    batch_location_id = fields.Many2one(
        'stock.location', string='Flock Batch', required=True,
        domain="[('farm_hierarchy_level', '=', 'batch')]", tracking=True
    )
    cage_location_id = fields.Many2one(
        'stock.location', string='Cage Location', required=True,
        domain="[('farm_hierarchy_level', '=', 'cage'), ('parent_batch_location_id', '=', batch_location_id)]",
        tracking=True
    )

    bird_product_id = fields.Many2one(
        'product.product', string='Bird Product', required=True,
        domain="[('categ_id.name', 'ilike', 'Bird')]", tracking=True
    )
    batch_lot_id = fields.Many2one(
        'stock.lot', string='Flock Lot', compute='_compute_batch_lot', store=True, readonly=False,
        help="Hatchery lot number tracked in this cage."
    )

    available_live_birds = fields.Integer(
        string='Live Birds in Cage', compute='_compute_available_live_birds',
        help="Current live birds on hand in this cage before recording this mortality."
    )
    dead_bird_count = fields.Integer(string='Dead Bird Count', required=True, tracking=True)
    today_cage_mortality_pct = fields.Float(
        string="Today's Mortality Rate (%)", compute='_compute_mortality_pct', digits=(16, 2),
        help="Cumulative dead birds today divided by available cage population."
    )

    cause_of_death = fields.Selection([
        ('disease', 'Disease / Infection'),
        ('heat_stress', 'Heat Stress / Dehydration'),
        ('cannibalism', 'Cannibalism / Pecking'),
        ('smothering', 'Smothering / Piling'),
        ('sudden_death', 'Sudden Death Syndrome (SDS)'),
        ('other', 'Other / Unknown'),
    ], string='Cause of Death', required=True, default='other', tracking=True)

    notes = fields.Text(string='Observations / Symptoms')
    rejection_reason = fields.Text(string='Rejection Reason', readonly=True, copy=False, tracking=True)

    scrap_id = fields.Many2one('stock.scrap', string='Generated Stock Scrap', readonly=True, copy=False)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting_approval', 'Waiting Manager Approval'),
        ('done', 'Approved / Scrapped'),
        ('rejected', 'Rejected'),
    ], string='Status', default='draft', tracking=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('farm.mortality.log') or _('New')
        return super().create(vals_list)

    @api.depends('cage_location_id', 'bird_product_id')
    def _compute_batch_lot(self):
        for rec in self:
            if rec.cage_location_id and rec.bird_product_id:
                quant = self.env['stock.quant'].search([
                    ('location_id', '=', rec.cage_location_id.id),
                    ('product_id', '=', rec.bird_product_id.id),
                    ('quantity', '>', 0)
                ], limit=1)
                rec.batch_lot_id = quant.lot_id.id if quant else False
            else:
                rec.batch_lot_id = False

    @api.depends('cage_location_id')
    def _compute_available_live_birds(self):
        for rec in self:
            rec.available_live_birds = rec.cage_location_id.get_live_bird_count() if rec.cage_location_id else 0

    @api.depends('dead_bird_count', 'available_live_birds', 'cage_location_id', 'date')
    def _compute_mortality_pct(self):
        for rec in self:
            if rec.available_live_birds > 0 and rec.cage_location_id:
                cum_dead = self._get_today_cumulative_dead(rec.cage_location_id, rec.date, exclude_id=rec.id) + rec.dead_bird_count
                rec.today_cage_mortality_pct = round((cum_dead / rec.available_live_birds) * 100.0, 2)
            else:
                rec.today_cage_mortality_pct = 0.0

    def _get_today_cumulative_dead(self, cage, incident_date, exclude_id=False):
        """Calculates total dead birds already confirmed or waiting approval today in this cage."""
        domain = [
            ('cage_location_id', '=', cage.id),
            ('date', '=', incident_date),
            ('state', 'in', ('waiting_approval', 'done')),
        ]
        if exclude_id:
            domain.append(('id', '!=', exclude_id))
        logs = self.search(domain)
        return sum(logs.mapped('dead_bird_count'))

    # -------------------------------------------------------------------------
    # WORKFLOW ACTIONS
    # -------------------------------------------------------------------------
    def action_submit(self):
        """Validates entry, checks anti-bypass threshold, and routes to approval or auto-scraps."""
        self.ensure_one()
        if self.dead_bird_count <= 0:
            raise UserError(_("Dead bird count must be greater than zero."))

        # 1. Hard Live Stock Guard
        live_quants = self.cage_location_id.get_live_bird_count()
        if self.dead_bird_count > live_quants:
            raise ValidationError(_(
                "Cannot log %s dead birds. There are only %s live birds on hand in %s.",
                self.dead_bird_count, live_quants, self.cage_location_id.display_name
            ))

        # 2. Cumulative Daily Threshold Check (> 2.0%)
        threshold = self.env.company.daily_mortality_threshold_pct or 2.0
        cum_dead = self._get_today_cumulative_dead(self.cage_location_id, self.date, exclude_id=self.id) + self.dead_bird_count
        mortality_rate = (cum_dead / live_quants) * 100.0

        if mortality_rate > threshold:
            self.state = 'waiting_approval'
            manager_group = self.env.ref('top_farm_core.group_farm_manager')
            managers = manager_group.users
            self.message_post(
                body=_(
                    "⚠️ <b>Abnormal Mortality Alert:</b> Today's cumulative mortality in %s has reached "
                    "<b>%s dead birds (%.2f%%)</b>, exceeding the threshold of %.1f%%.<br/>"
                    "Supervisor approval is required before stock scrap can be executed.",
                    self.cage_location_id.name, cum_dead, mortality_rate, threshold
                ),
                partner_ids=managers.partner_id.ids
            )
        else:
            self._create_and_validate_scrap()
            self.state = 'done'
        return True

    def action_manager_approve(self):
        """Farm Manager approval action."""
        self.ensure_one()
        if not self.env.user.has_group('top_farm_core.group_farm_manager'):
            raise UserError(_("Only Farm Managers can approve abnormal mortality records."))

        live_quants = self.cage_location_id.get_live_bird_count()
        if self.dead_bird_count > live_quants:
            raise ValidationError(_(
                "Approval failed: Only %s live birds remaining in %s. Cannot scrap %s birds.",
                live_quants, self.cage_location_id.display_name, self.dead_bird_count
            ))

        self._create_and_validate_scrap()
        self.state = 'done'
        self.message_post(body=_("Abnormal mortality entry approved by Farm Manager %s.", self.env.user.name))
        return True

    def action_reject(self):
        """Open wizard or set rejection reason."""
        self.ensure_one()
        if not self.env.user.has_group('top_farm_core.group_farm_manager'):
            raise UserError(_("Only Farm Managers can reject mortality records."))
        self.state = 'rejected'
        self.message_post(body=_("Mortality entry rejected by %s.", self.env.user.name))
        return True

    def _create_and_validate_scrap(self):
        """Creates and validates stock.scrap to reduce live quants and book GL 630000."""
        self.ensure_one()
        scrap_location = self.env['stock.location'].search([
            ('usage', '=', 'inventory'),
            ('scrap_location', '=', True)
        ], limit=1)
        if not scrap_location:
            scrap_location = self.env.ref('stock.location_scrapped')

        scrap = self.env['stock.scrap'].create({
            'product_id': self.bird_product_id.id,
            'scrap_qty': self.dead_bird_count,
            'product_uom_id': self.bird_product_id.uom_id.id,
            'location_id': self.cage_location_id.id,
            'scrap_location_id': scrap_location.id,
            'lot_id': self.batch_lot_id.id if self.batch_lot_id else False,
            'origin': self.name,
        })
        scrap.action_validate()
        self.scrap_id = scrap
```

---

### 3.3 UI Views & Screen Layouts

#### File: `views/res_config_settings_views.xml`
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="res_config_settings_view_form_farm_mortality" model="ir.ui.view">
        <field name="name">res.config.settings.view.form.farm.mortality</field>
        <field name="model">res.config.settings</field>
        <field name="inherit_id" ref="base.res_config_settings_view_form"/>
        <field name="arch" type="xml">
            <xpath expr="//form" position="inside">
                <app data-string="Top Farm" string="Top Farm" name="top_farm">
                    <block title="Poultry Loss &amp; Mortality Controls" id="mortality_controls_settings">
                        <setting id="daily_mortality_threshold_setting"
                                 help="Abnormal daily mortality percentage threshold that triggers mandatory Farm Manager approval.">
                            <field name="daily_mortality_threshold_pct" class="oe_inline"/>
                            <span> % per cage / day</span>
                        </setting>
                    </block>
                </app>
            </xpath>
        </field>
    </record>
</odoo>
```

---

#### File: `views/farm_mortality_log_views.xml`
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_farm_mortality_log_form" model="ir.ui.view">
        <field name="name">farm.mortality.log.form</field>
        <field name="model">farm.mortality.log</field>
        <field name="arch" type="xml">
            <form string="Poultry Mortality Record">
                <header>
                    <button name="action_submit" string="Submit Mortality" type="object"
                            class="oe_highlight" invisible="state != 'draft'"/>
                    <button name="action_manager_approve" string="Approve Scrap" type="object"
                            class="btn-success" invisible="state != 'waiting_approval'"
                            groups="top_farm_core.group_farm_manager"/>
                    <button name="action_reject" string="Reject" type="object"
                            class="btn-danger" invisible="state != 'waiting_approval'"
                            groups="top_farm_core.group_farm_manager"/>
                    <field name="state" widget="statusbar" statusbar_visible="draft,waiting_approval,done"/>
                </header>
                <sheet>
                    <div class="oe_title">
                        <h1><field name="name"/></h1>
                    </div>
                    <group>
                        <group string="Flock &amp; Cage Location">
                            <field name="date"/>
                            <field name="batch_location_id"/>
                            <field name="cage_location_id"/>
                            <field name="available_live_birds"/>
                        </group>
                        <group string="Bird Loss &amp; Approval Status">
                            <field name="bird_product_id"/>
                            <field name="batch_lot_id"/>
                            <field name="dead_bird_count"/>
                            <field name="today_cage_mortality_pct" widget="percentage"
                                   decoration-danger="today_cage_mortality_pct &gt; 2.0"
                                   decoration-success="today_cage_mortality_pct &lt;= 2.0"/>
                            <field name="cause_of_death"/>
                            <field name="scrap_id" invisible="not scrap_id"/>
                        </group>
                    </group>
                    <group string="Observations &amp; Notes">
                        <field name="notes" placeholder="Describe symptoms, temperature, water supply conditions..."/>
                    </group>
                </sheet>
                <chatter/>
            </form>
        </field>
    </record>

    <record id="view_farm_mortality_log_tree" model="ir.ui.view">
        <field name="name">farm.mortality.log.list</field>
        <field name="model">farm.mortality.log</field>
        <field name="arch" type="xml">
            <list string="Mortality Log Records" decoration-danger="state == 'waiting_approval'" decoration-muted="state == 'rejected'">
                <field name="name"/>
                <field name="date"/>
                <field name="batch_location_id"/>
                <field name="cage_location_id"/>
                <field name="dead_bird_count" sum="Total Dead Birds"/>
                <field name="today_cage_mortality_pct"/>
                <field name="cause_of_death"/>
                <field name="state" widget="badge"
                       decoration-info="state == 'draft'"
                       decoration-warning="state == 'waiting_approval'"
                       decoration-success="state == 'done'"
                       decoration-danger="state == 'rejected'"/>
            </list>
        </field>
    </record>

    <record id="action_farm_mortality_log" model="ir.actions.act_window">
        <field name="name">Daily Mortality Records</field>
        <field name="res_model">farm.mortality.log</field>
        <field name="view_mode">list,form</field>
        <field name="context">{'search_default_group_batch': 1}</field>
    </record>
</odoo>
```

---

#### File: `views/farm_mortality_menus.xml`
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <menuitem id="menu_top_farm_mortality_log"
              name="Bird Mortality Records"
              parent="top_farm_operations.menu_top_farm_operations"
              action="action_farm_mortality_log"
              sequence="30"/>
</odoo>
```

---

## 4. Visual UI Layout & Screen Mockup

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  MORT/2026/00078                                                [ Draft ] ➔ ( Waiting Approval ) ➔ Done │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  [ Approve Scrap ✔️ ]    [ Reject ❌ ]                                                                   │
│  (Manager Approval Buttons visible only when Waiting Approval)                                         │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                        │
│  Reference: MORT/2026/00078                                                                            │
│                                                                                                        │
│  Location & Flock Information                  Loss Details & Threshold Check                          │
│  ────────────────────────────                  ──────────────────────────────                          │
│  Incident Date:   [ 29/09/2026 📅 ]            Bird Product:     [ Layer Hen - Hy-Line Brown ▼ ]       │
│  Flock Batch:     [ Batch C-01 (WH/Farm 1) ▼ ] Hatchery Lot:     [ LOT-2026-01               ▼ ]       │
│  Cage Location:   [ Cage A-01              ▼ ] Dead Bird Count:  [ 25 ] birds                          │
│  Live Birds Now:  [ 1,000 birds on hand    ]   Today's Rate:     [ 2.50% ⚠️ ] (Red Alert: > 2.0%)      │
│                                                Cause of Death:   [ Heat Stress / Dehydration ▼ ]       │
│                                                Stock Scrap:      [ SP/00095 ↗ ] (Generated on approve) │
│                                                                                                        │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  Clinical Symptoms & Field Observations:                                                               │
│  "Ventilation fan #2 above Cage A-01 failed during peak afternoon heat (38°C). Birds found smothered. │
│   Fan motor replaced at 16:30 by maintenance."                                                         │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
│  💬 Chatter & Activity Tracking:                                                                       │
│  ⚠️ Abnormal Mortality Alert: Today's cumulative mortality in Cage A-01 reached 25 birds (2.50%).      │
│     Supervisor approval required. Alert sent to Farm Manager.                                          │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Developer Acceptance Checklist for Module 3

- [ ] **Test 1 (Normal Scrap Execution):** In Cage A-01 (1,000 birds), log 5 dead birds (0.5%). Click Submit. Verify status turns `done`, `stock.scrap` is validated, and live birds drop to 995.
- [ ] **Test 2 (Analytic Tagging Verification):** Check `account.analytic.line` created by Test 1 scrap. Confirm GL `630000 Mortality Loss` has Batch C-01 (100%) and Cage A-01 (100%) tags.
- [ ] **Test 3 (Single High Loss Trigger):** In Cage A-02 (1,000 birds), log 25 dead birds (2.5%). Click Submit. Verify status is set to `waiting_approval` and direct scrap is blocked.
- [ ] **Test 4 (Cumulative Anti-Bypass Guard):** In Cage A-03, log 15 dead birds in the morning (1.5% - approved). Log 10 dead birds in afternoon. Confirm afternoon entry is routed to `waiting_approval`.
- [ ] **Test 5 (Manager Approval Execution):** Log in as Farm Manager. Approve the record from Test 4. Confirm scrap executes and live birds decrease correctly.
- [ ] **Test 6 (Manager Rejection Workflow):** Create a pending record; manager clicks Reject. Confirm status turns `rejected` and inventory is NOT touched.
- [ ] **Test 7 (Quant Upper Bound Guard):** Attempt to log 1,500 dead birds in a cage with 990 birds. Confirm Odoo throws a hard `ValidationError`.
