# Top Farm: Module 2 (`top_farm_operations`) — Detailed Developer Implementation Plan

**Target System:** Odoo 19.0 (Enterprise / Community)  
**Effort Allocation:** 51–55 Developer Hours + 14–15 QA Hours (Total: 65–70 Hours)  
**Dependencies:** `top_farm_core`, `mrp`, `mrp_account`, `mail`  
**Module Name:** `top_farm_operations`  
**License:** LGPL-3  
**BRD Customization Points Covered:** Point 2 (Feed/Medication Log), Point 3 (Graded Egg Collection), Point 4 (Proportional Split MO Engine)  

---

## 1. Module Overview & Operational Scope

`top_farm_operations` is the operational engine of Top Farm. It bridges the gap between daily physical poultry activities inside the sheds and standard Odoo inventory, manufacturing, and cost accounting.

### Key Operational Deliverables:
1. **Daily Feed & Medication Logging (`farm.feed.log`):**
   * Records morning feeding and medication/vaccine administration by Batch and Cage.
   * **Pre-Laying Phase:** Automatically generates a stock picking to `Virtual Locations/Feed Consumption`, booking direct expense to GL `600000`.
   * **Laying Phase:** Stages feed in `confirmed` status without moving inventory to prevent double-deduction before egg harvesting.
   * **Medication:** Expensed directly to `Virtual Locations/Medication Consumption` (GL `610000`).
2. **Daily Graded Egg Collection (`farm.egg.collection`):**
   * Fast, touch-friendly tablet entry for 4 standard egg grades: **Medium, Large, Jumbo, and Damaged/Cracked**.
   * Permanent snapshot of `confirmed_live_bird_count` to ensure historical Hen-Day rate integrity even after future flock mortality.
   * Real-time calculation of **Hen-Day Egg Production %** and **FCR (kg of feed per dozen eggs)**.
3. **Proportional Manufacturing Order Splitting Engine:**
   * One single click creates and auto-produces up to 4 separate `mrp.production` records (one per active egg grade).
   * Allocates feed component consumption proportionally based on egg grade quantity.
   * **Zero-Loss Rounding Reconciler:** Residual grams from rounding are reconciled on the largest egg grade so that total feed consumed exactly matches the silo deduction.
   * Generates finished egg batch lot `LOT-EGG-{batch}-{YYYYMMDD}` and places eggs in `WH/Stock/Eggs/Batch-C01`.
4. **Nightly Unharvested Feed Fallback Cron (`cron_reconcile_unharvested_feed`):**
   * Scheduled daily at 23:59. Identifies any laying feed logs with no egg harvest and flushes them to GL `600000` as maintenance feed.

---

## 2. Directory & File Structure

```text
top_farm_operations/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── farm_feed_log.py              # Feed & medication logging models
│   ├── farm_egg_collection.py        # Graded egg collection & split MO engine
│   └── mrp_production.py             # Extension linking MO back to egg collection
├── data/
│   ├── ir_sequence_data.xml          # FEED/YYYY/XXXXX and EGG/YYYY/XXXXX sequences
│   └── ir_cron_data.xml              # Nightly 23:59 unharvested feed reconciler
├── security/
│   └── ir.model.access.csv           # Permissions for operator and manager
└── views/
    ├── farm_feed_log_views.xml       # Feed log form, tree, search
    ├── farm_egg_collection_views.xml # Graded egg collection form, tree, search
    └── farm_operations_menus.xml     # Operations menus under Top Farm
```

---

## 3. Detailed Technical Specifications

### 3.1 `__manifest__.py`

```python
{
    'name': 'Top Farm Operations - Feed, Eggs & Proportional MO Engine',
    'version': '19.0.1.0.0',
    'category': 'Poultry Farm Operations',
    'summary': 'Daily feed and medication logging, graded egg collections, and proportional MO splitting',
    'description': """
Top Farm Daily Operations
=========================
- Daily Feed & Medication entry with automated Pre-Laying consumption.
- Daily Graded Egg Collection (Medium, Large, Jumbo, Damage).
- Proportional MO Auto-Split Engine converting feed into graded table eggs.
- Zero-loss mathematical rounding reconciliation.
- Nightly cron fallback for unharvested laying feed.
    """,
    'author': 'Top Farm ERP Team',
    'depends': [
        'top_farm_core',
        'mrp',
        'mrp_account',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        'views/farm_feed_log_views.xml',
        'views/farm_egg_collection_views.xml',
        'views/farm_operations_menus.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
```

---

### 3.2 Sequence & Cron Data

#### File: `data/ir_sequence_data.xml`
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="seq_farm_feed_log" model="ir.sequence">
        <field name="name">Daily Feed Log Sequence</field>
        <field name="code">farm.feed.log</field>
        <field name="prefix">FEED/%(year)s/</field>
        <field name="padding">5</field>
        <field name="company_id" eval="False"/>
    </record>

    <record id="seq_farm_egg_collection" model="ir.sequence">
        <field name="name">Daily Egg Collection Sequence</field>
        <field name="code">farm.egg.collection</field>
        <field name="prefix">EGG/%(year)s/</field>
        <field name="padding">5</field>
        <field name="company_id" eval="False"/>
    </record>
</odoo>
```

#### File: `data/ir_cron_data.xml`
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="cron_reconcile_unharvested_feed" model="ir.cron">
        <field name="name">Top Farm: Reconcile Unharvested Laying Feed</field>
        <field name="model_id" ref="model_farm_feed_log"/>
        <field name="state">code</field>
        <field name="code">model._cron_reconcile_unharvested_feed()</field>
        <field name="interval_number">1</field>
        <field name="interval_type">days</field>
        <field name="nextcall" eval="(DateTime.now().replace(hour=23, minute=59, second=0)).strftime('%Y-%m-%d %H:%M:%S')"/>
        <field name="active" eval="True"/>
    </record>
</odoo>
```

---

### 3.3 Data Models Implementation

#### File: `models/farm_feed_log.py`
Handles daily feeding and medication administration:

```python
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class FarmFeedLog(models.Model):
    _name = 'farm.feed.log'
    _description = 'Daily Feed & Medication Log'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Log Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    date = fields.Date(string='Feeding Date', required=True, default=fields.Date.context_today, tracking=True)
    batch_location_id = fields.Many2one(
        'stock.location', string='Flock Batch', required=True,
        domain="[('farm_hierarchy_level', '=', 'batch')]", tracking=True
    )
    cage_location_id = fields.Many2one(
        'stock.location', string='Cage Location', required=True,
        domain="[('farm_hierarchy_level', '=', 'cage'), ('parent_batch_location_id', '=', batch_location_id)]",
        tracking=True
    )
    feeding_phase = fields.Selection([
        ('pre_laying', 'Pre-Laying (Direct Expense)'),
        ('laying', 'Laying Phase (Staged for Egg Harvest)'),
    ], string='Feeding Phase', compute='_compute_feeding_phase', store=True, readonly=False, tracking=True)

    line_ids = fields.One2many('farm.feed.log.line', 'log_id', string='Feed & Medication Lines')
    total_feed_qty = fields.Float(string='Total Feed (kg)', compute='_compute_totals', store=True, digits='Product Unit of Measure')
    total_med_qty = fields.Float(string='Total Medication', compute='_compute_totals', store=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed (Staged)'),
        ('reconciled', 'Reconciled / Produced'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False)

    picking_id = fields.Many2one('stock.picking', string='Consumption Picking', readonly=True, copy=False)
    egg_collection_id = fields.Many2one('farm.egg.collection', string='Linked Egg Collection', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('farm.feed.log') or _('New')
        return super().create(vals_list)

    @api.depends('batch_location_id', 'batch_location_id.batch_stage')
    def _compute_feeding_phase(self):
        for rec in self:
            if rec.batch_location_id and rec.batch_location_id.batch_stage:
                rec.feeding_phase = 'laying' if rec.batch_location_id.batch_stage == 'laying' else 'pre_laying'
            else:
                rec.feeding_phase = 'pre_laying'

    @api.depends('line_ids.quantity', 'line_ids.is_medication')
    def _compute_totals(self):
        for rec in self:
            feed_lines = rec.line_ids.filtered(lambda l: not l.is_medication)
            med_lines = rec.line_ids.filtered(lambda l: l.is_medication)
            rec.total_feed_qty = sum(feed_lines.mapped('quantity'))
            rec.total_med_qty = sum(med_lines.mapped('quantity'))

    def action_confirm(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Please add at least one feed or medication line before confirming."))

        med_lines = self.line_ids.filtered(lambda l: l.is_medication)
        feed_lines = self.line_ids.filtered(lambda l: not l.is_medication)

        if med_lines:
            self._create_direct_consumption_picking(med_lines, 'medication')

        if self.feeding_phase == 'pre_laying':
            if feed_lines:
                self._create_direct_consumption_picking(feed_lines, 'feed')
            self.state = 'reconciled'
        else:
            self.state = 'confirmed'
        return True

    def _create_direct_consumption_picking(self, lines, line_type):
        self.ensure_one()
        dest_loc = self.env['stock.location'].search([
            ('usage', '=', 'inventory'),
            ('name', 'ilike', 'Feed Consumption' if line_type == 'feed' else 'Medication Consumption')
        ], limit=1)
        if not dest_loc:
            dest_loc = self.env.ref('stock.location_inventory')

        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', self.batch_location_id.warehouse_id.id or 1)
        ], limit=1)

        move_vals = []
        for line in lines:
            move_vals.append((0, 0, {
                'name': f"{line.product_id.name} Consumption ({self.cage_location_id.name})",
                'product_id': line.product_id.id,
                'product_uom': line.uom_id.id,
                'product_uom_qty': line.quantity,
                'location_id': line.source_location_id.id,
                'location_dest_id': dest_loc.id,
            }))

        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': lines[0].source_location_id.id,
            'location_dest_id': dest_loc.id,
            'origin': self.name,
            'move_ids_without_package': move_vals,
        })
        picking.action_confirm()
        picking.action_assign()
        for move in picking.move_ids_without_package:
            move.quantity = move.product_uom_qty
        picking.button_validate()
        self.picking_id = picking

    @api.model
    def _cron_reconcile_unharvested_feed(self):
        today = fields.Date.today()
        unharvested_logs = self.search([
            ('state', '=', 'confirmed'),
            ('feeding_phase', '=', 'laying'),
            ('date', '<=', today),
        ])
        for log in unharvested_logs:
            feed_lines = log.line_ids.filtered(lambda l: not l.is_medication)
            if feed_lines:
                log._create_direct_consumption_picking(feed_lines, 'feed')
            log.message_post(body=_(
                "No egg harvest was recorded for this cage today. Staged feed (%s kg) has been "
                "automatically expensed as flock maintenance feed.", log.total_feed_qty
            ))
            log.state = 'reconciled'


class FarmFeedLogLine(models.Model):
    _name = 'farm.feed.log.line'
    _description = 'Feed & Medication Line'

    log_id = fields.Many2one('farm.feed.log', string='Feed Log Reference', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    is_medication = fields.Boolean(string='Is Medication', compute='_compute_is_medication', store=True)
    source_location_id = fields.Many2one('stock.location', string='Source Silo / Store', required=True)
    quantity = fields.Float(string='Quantity', required=True, digits='Product Unit of Measure')
    uom_id = fields.Many2one('uom.uom', string='UoM', related='product_id.uom_id', readonly=True)

    @api.depends('product_id', 'product_id.categ_id')
    def _compute_is_medication(self):
        for line in self:
            if line.product_id and line.product_id.categ_id:
                line.is_medication = 'Medication' in line.product_id.categ_id.name or 'Vaccine' in line.product_id.categ_id.name
            else:
                line.is_medication = False
```

---

#### File: `models/farm_egg_collection.py`
Handles graded egg entry and the proportional MO splitting engine:

```python
from datetime import datetime
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class FarmEggCollection(models.Model):
    _name = 'farm.egg.collection'
    _description = 'Daily Graded Egg Collection & MO Engine'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Collection Ref', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    date = fields.Date(string='Collection Date', required=True, default=fields.Date.context_today, tracking=True)
    batch_location_id = fields.Many2one(
        'stock.location', string='Flock Batch', required=True,
        domain="[('farm_hierarchy_level', '=', 'batch')]", tracking=True
    )
    cage_location_id = fields.Many2one(
        'stock.location', string='Cage Location', required=True,
        domain="[('farm_hierarchy_level', '=', 'cage'), ('parent_batch_location_id', '=', batch_location_id)]",
        tracking=True
    )
    destination_location_id = fields.Many2one(
        'stock.location', string='Egg Warehouse Location', required=True,
        help="Warehouse cold-room destination for graded eggs."
    )

    product_medium_id = fields.Many2one('product.product', string='Medium Egg Product', required=True)
    product_large_id = fields.Many2one('product.product', string='Large Egg Product', required=True)
    product_jumbo_id = fields.Many2one('product.product', string='Jumbo Egg Product', required=True)
    product_damage_id = fields.Many2one('product.product', string='Damaged / Cracked Product', required=True)

    qty_medium = fields.Integer(string='Medium Eggs (qty)', default=0, tracking=True)
    qty_large = fields.Integer(string='Large Eggs (qty)', default=0, tracking=True)
    qty_jumbo = fields.Integer(string='Jumbo Eggs (qty)', default=0, tracking=True)
    qty_damage = fields.Integer(string='Damaged Eggs (qty)', default=0, tracking=True)
    total_egg_qty = fields.Integer(string='Total Eggs Collected', compute='_compute_total_eggs', store=True)

    confirmed_live_bird_count = fields.Integer(
        string='Live Birds Snapshot', readonly=True, copy=False,
        help="Permanent snapshot of live birds at collection time to ensure historical Hen-Day accuracy."
    )
    hen_day_rate = fields.Float(
        string='Hen-Day Rate (%)', compute='_compute_kpis', store=True, digits=(16, 2),
        help="(Total Eggs / Live Birds) * 100"
    )
    feed_log_id = fields.Many2one('farm.feed.log', string='Linked Staged Feed Log', domain="[('state', '=', 'confirmed')]")
    feed_consumed_qty = fields.Float(string='Feed Consumed (kg)', compute='_compute_feed_consumed', store=True)
    fcr = fields.Float(
        string='FCR (kg/dozen)', compute='_compute_kpis', store=True, digits=(16, 3),
        help="kg of feed consumed per dozen eggs produced."
    )

    production_ids = fields.One2many('mrp.production', 'farm_collection_id', string='Manufacturing Orders', readonly=True)
    mo_count = fields.Integer(string='MO Count', compute='_compute_mo_count')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done / Produced'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('farm.egg.collection') or _('New')
        return super().create(vals_list)

    @api.depends('qty_medium', 'qty_large', 'qty_jumbo', 'qty_damage')
    def _compute_total_eggs(self):
        for rec in self:
            rec.total_egg_qty = rec.qty_medium + rec.qty_large + rec.qty_jumbo + rec.qty_damage

    @api.depends('feed_log_id', 'feed_log_id.total_feed_qty')
    def _compute_feed_consumed(self):
        for rec in self:
            rec.feed_consumed_qty = rec.feed_log_id.total_feed_qty if rec.feed_log_id else 0.0

    @api.depends('total_egg_qty', 'confirmed_live_bird_count', 'feed_consumed_qty')
    def _compute_kpis(self):
        for rec in self:
            if rec.confirmed_live_bird_count > 0:
                rec.hen_day_rate = (rec.total_egg_qty / rec.confirmed_live_bird_count) * 100.0
            else:
                rec.hen_day_rate = 0.0

            dozen_eggs = rec.total_egg_qty / 12.0
            if dozen_eggs > 0:
                rec.fcr = round(rec.feed_consumed_qty / dozen_eggs, 3)
            else:
                rec.fcr = 0.0

    @api.depends('production_ids')
    def _compute_mo_count(self):
        for rec in self:
            rec.mo_count = len(rec.production_ids)

    def action_generate_split_manufacturing_orders(self):
        self.ensure_one()
        if self.total_egg_qty <= 0:
            raise UserError(_("Cannot generate manufacturing orders for 0 eggs."))
        if not self.feed_log_id or self.feed_consumed_qty <= 0:
            raise UserError(_("Please link a confirmed Daily Feed Log with feed quantity > 0."))

        self.confirmed_live_bird_count = self.cage_location_id.get_live_bird_count()

        grades = []
        if self.qty_large > 0:
            grades.append({'product': self.product_large_id, 'qty': self.qty_large, 'grade': 'large'})
        if self.qty_medium > 0:
            grades.append({'product': self.product_medium_id, 'qty': self.qty_medium, 'grade': 'medium'})
        if self.qty_jumbo > 0:
            grades.append({'product': self.product_jumbo_id, 'qty': self.qty_jumbo, 'grade': 'jumbo'})
        if self.qty_damage > 0:
            grades.append({'product': self.product_damage_id, 'qty': self.qty_damage, 'grade': 'damage'})

        grades = sorted(grades, key=lambda g: g['qty'], reverse=True)

        total_feed = self.feed_consumed_qty
        feed_component_line = self.feed_log_id.line_ids.filtered(lambda l: not l.is_medication)[0]
        feed_product = feed_component_line.product_id
        feed_silo_loc = feed_component_line.source_location_id

        allocated_feed_sum = 0.0
        for item in grades:
            prop_qty = round(total_feed * (item['qty'] / self.total_egg_qty), 4)
            item['feed_qty'] = prop_qty
            allocated_feed_sum += prop_qty

        rounding_diff = round(total_feed - allocated_feed_sum, 4)
        if rounding_diff != 0.0 and grades:
            grades[0]['feed_qty'] = round(grades[0]['feed_qty'] + rounding_diff, 4)

        date_str = self.date.strftime('%Y%m%d')
        batch_code = self.batch_location_id.name.replace(' ', '-').replace('/', '-')
        lot_name = f"LOT-EGG-{batch_code}-{date_str}"

        created_mos = self.env['mrp.production']
        for item in grades:
            egg_product = item['product']
            lot = self.env['stock.lot'].search([
                ('product_id', '=', egg_product.id),
                ('name', '=', lot_name),
                ('company_id', '=', self.env.company.id)
            ], limit=1)
            if not lot:
                lot = self.env['stock.lot'].create({
                    'product_id': egg_product.id,
                    'name': lot_name,
                    'company_id': self.env.company.id,
                })

            mo = self.env['mrp.production'].create({
                'product_id': egg_product.id,
                'product_qty': item['qty'],
                'product_uom_id': egg_product.uom_id.id,
                'lot_producing_id': lot.id,
                'location_src_id': feed_silo_loc.id,
                'location_dest_id': self.destination_location_id.id,
                'farm_collection_id': self.id,
                'move_raw_ids': [(0, 0, {
                    'name': f"Feed for {egg_product.name}",
                    'product_id': feed_product.id,
                    'product_uom': feed_product.uom_id.id,
                    'product_uom_qty': item['feed_qty'],
                    'location_id': feed_silo_loc.id,
                    'location_dest_id': egg_product.property_stock_production.id,
                })],
            })
            mo.action_confirm()
            for raw_move in mo.move_raw_ids:
                raw_move.quantity = raw_move.product_uom_qty
            mo.qty_producing = item['qty']
            mo.button_mark_done()
            created_mos |= mo

        self.state = 'done'
        self.feed_log_id.state = 'reconciled'
        self.feed_log_id.egg_collection_id = self.id
        self.message_post(body=_(
            "Successfully generated and completed %s graded Manufacturing Orders. Total feed consumed: %s kg.",
            len(created_mos), total_feed
        ))
        return True

    def action_view_mos(self):
        self.ensure_one()
        action = self.env.ref('mrp.mrp_production_action').read()[0]
        action['domain'] = [('farm_collection_id', '=', self.id)]
        return action
```

---

#### File: `models/mrp_production.py`
Extends `mrp.production`:

```python
from odoo import fields, models

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    farm_collection_id = fields.Many2one(
        'farm.egg.collection',
        string='Source Farm Egg Collection',
        readonly=True,
        index=True,
        help="Links manufacturing order back to the daily poultry egg collection."
    )
```

---

## 4. UI Views & Menus

* **Feed Log Form View:** Statusbar (`draft`, `confirmed`, `reconciled`), line items for Feed/Medication, source silo selection, and Confirm button.
* **Egg Collection Form View:** Simple grading buckets (`qty_medium`, `qty_large`, `qty_jumbo`, `qty_damage`), smart button for MOs, and biological KPI display (Hen-Day % and FCR kg/dozen).
* **Menus:**
  * Root: **Top Farm $\rightarrow$ Farm Operations**
    * Submenu 1: **Daily Feed & Medication**
    * Submenu 2: **Daily Egg Collections**

---

## 5. Developer Acceptance Checklist for Module 2

- [ ] **Test 1 (Pre-Laying Feed Picking):** Log 50 kg feed in `pre_laying`. Confirm system immediately generates a validated stock picking from Silo to `Feed Consumption` and debits GL `600000`.
- [ ] **Test 2 (Laying Feed Staging):** Log 100 kg feed in `laying`. Confirm stock is **NOT** deducted and state is `confirmed`.
- [ ] **Test 3 (Proportional Split Calculation):** Enter 500 Large, 300 Medium, 100 Jumbo, 100 Damage. Verify 4 MOs are created with 50 kg, 30 kg, 10 kg, and 10 kg feed.
- [ ] **Test 4 (Zero-Loss Rounding):** Test with odd quantities (e.g., 333, 333, 334 eggs on 100 kg feed). Verify the sum of feed in all MOs is **exactly 100.0000 kg**.
- [ ] **Test 5 (Egg Lot Generation):** Verify graded eggs received in `WH/Stock/Eggs/Batch-C01` carry lot `LOT-EGG-C01-YYYYMMDD`.
- [ ] **Test 6 (Live Bird Snapshot):** Confirm `confirmed_live_bird_count` on the collection is stored permanently and does not change when birds die later.
- [ ] **Test 7 (Nightly Cron):** Create a laying feed log with no egg harvest; trigger cron manually; confirm feed is expensed to GL `600000` with chatter notice.
